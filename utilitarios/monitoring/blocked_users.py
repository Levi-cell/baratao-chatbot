"""Comparação de bloqueios do WhatsApp e do banco, somente para leitura.

O escopo é deliberadamente limitado às unidades e WABAs cadastradas no
banco. A ferramenta não altera a Meta nem o PostgreSQL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utilitarios.bootstrap import configurar_ambiente_local
from core.repositories.seguranca.comparacao_bloqueios import (
    iniciar_leitura_consistente,
    listar_unidades_para_comparacao,
    listar_bloqueios_para_comparacao,
)


def carregar_estado_banco(*, connection_factory=None):
    """Carrega unidades e bloqueios locais em uma única fotografia read-only."""
    if connection_factory is None:
        configurar_ambiente_local()
        from core.database.connection_aws import get_conn

        connection_factory = get_conn

    conn = connection_factory(
        application_name="utilitarios_blocked_users_readonly",
    )
    try:
        cursor = conn.cursor()
        iniciar_leitura_consistente(cursor)
        linhas_unidades = listar_unidades_para_comparacao(cursor)
        unidades = [
            {
                "id_unidade": linha[0],
                "nome_unidade": linha[1],
                "waba_id": _normalizar_id(linha[2]),
                "phone_id_unidade": _normalizar_id(linha[3]),
            }
            for linha in linhas_unidades
        ]

        linhas_bloqueios = listar_bloqueios_para_comparacao(cursor)
        bloqueios = [
            {
                "wa_id_cliente": _normalizar_id(linha[0]),
                "id_unidade": linha[1],
                "nome_unidade": linha[2],
                "waba_id": _normalizar_id(linha[3]),
                "phone_id_unidade": _normalizar_id(linha[4]),
                "phone_id_registrado": _normalizar_id(linha[4]),
                "id_cliente": linha[5],
                "nome_cliente": linha[6],
            }
            for linha in linhas_bloqueios
        ]
        return unidades, bloqueios
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def listar_usuarios_bloqueados_meta(phone_id_unidade):
    """Lista todos os bloqueados de um phone ID usando paginação do PyWa."""
    configurar_ambiente_local()
    from core.integrations.whatsapp.tools.usuarios import cliente_de_bloqueio

    cliente_wa = cliente_de_bloqueio(phone_id_unidade)
    return cliente_wa.get_blocked_users().all(sleep=0.2)


def coletar_bloqueios_meta(unidades, *, list_factory=None):
    """Coleta cada unidade isoladamente; uma falha não apaga as demais."""
    list_factory = list_factory or listar_usuarios_bloqueados_meta
    resultado = []

    for unidade in unidades:
        item = {
            **unidade,
            "status_meta": "ok",
            "erro_meta": None,
            "wa_ids_bloqueados": [],
        }
        try:
            bloqueados = list_factory(unidade["phone_id_unidade"])
            item["wa_ids_bloqueados"] = sorted({
                wa_id
                for wa_id in (
                    _extrair_wa_id_bloqueado(usuario)
                    for usuario in bloqueados
                )
                if wa_id
            })
        except Exception as exc:
            item["status_meta"] = "erro"
            item["erro_meta"] = f"{type(exc).__name__}: {exc}"

        resultado.append(item)

    return resultado


def comparar_bloqueios(bloqueios_meta, bloqueios_banco):
    """Compara bloqueios por WABA, phone ID e WA ID do cliente."""
    meta_por_chave = {}
    banco_por_chave = {}
    escopos_ok = set()
    escopos_com_erro = set()
    falhas_meta = []
    vinculos_unidade_divergentes = []

    for unidade in bloqueios_meta:
        escopo = _escopo(unidade)
        if unidade["status_meta"] != "ok":
            escopos_com_erro.add(escopo)
            falhas_meta.append({
                "id_unidade": unidade["id_unidade"],
                "nome_unidade": unidade["nome_unidade"],
                "waba_id": unidade["waba_id"],
                "phone_id_unidade": unidade["phone_id_unidade"],
                "erro_meta": unidade["erro_meta"],
            })
            continue

        escopos_ok.add(escopo)
        for wa_id_cliente in unidade["wa_ids_bloqueados"]:
            chave = (*escopo, _normalizar_id(wa_id_cliente))
            meta_por_chave[chave] = {
                "wa_id_cliente": chave[2],
                "id_unidade": unidade["id_unidade"],
                "nome_unidade": unidade["nome_unidade"],
                "waba_id": chave[0],
                "phone_id_unidade": chave[1],
                "origem": "meta",
            }

    for bloqueio in bloqueios_banco:
        phone_atual = _normalizar_id(bloqueio["phone_id_unidade"])
        phone_registrado = _normalizar_id(
            bloqueio.get("phone_id_registrado", phone_atual)
        )
        if phone_registrado != phone_atual:
            vinculos_unidade_divergentes.append(dict(bloqueio))
            continue

        chave = (
            _normalizar_id(bloqueio["waba_id"]),
            phone_atual,
            _normalizar_id(bloqueio["wa_id_cliente"]),
        )
        banco_por_chave[chave] = dict(bloqueio)

    chaves_meta = set(meta_por_chave)
    chaves_banco = set(banco_por_chave)
    chaves_sincronizadas = chaves_meta & chaves_banco
    chaves_somente_meta = chaves_meta - chaves_banco
    chaves_somente_banco = {
        chave
        for chave in chaves_banco - chaves_meta
        if chave[:2] in escopos_ok
    }
    chaves_nao_comparadas = {
        chave
        for chave in chaves_banco - chaves_meta
        if chave[:2] not in escopos_ok
    }

    sincronizados = [
        {
            **banco_por_chave[chave],
            "origens": ("banco", "meta"),
        }
        for chave in _ordenar_chaves(chaves_sincronizadas)
    ]
    somente_meta = [
        meta_por_chave[chave]
        for chave in _ordenar_chaves(chaves_somente_meta)
    ]
    somente_banco = [
        banco_por_chave[chave]
        for chave in _ordenar_chaves(chaves_somente_banco)
    ]
    nao_comparados_banco = [
        banco_por_chave[chave]
        for chave in _ordenar_chaves(chaves_nao_comparadas)
    ]

    return {
        "sincronizados": sincronizados,
        "somente_meta": somente_meta,
        "somente_banco": somente_banco,
        "nao_comparados_banco": nao_comparados_banco,
        "vinculos_unidade_divergentes": sorted(
            vinculos_unidade_divergentes,
            key=_ordem_registro,
        ),
        "falhas_meta": sorted(falhas_meta, key=_ordem_unidade),
        "escopos_meta_ok": sorted(escopos_ok),
        "escopos_meta_com_erro": sorted(escopos_com_erro),
    }


def reconciliar_bloqueios_meta_banco(
    *,
    imprimir=True,
    mostrar_wa_id=False,
    connection_factory=None,
    meta_list_factory=None,
):
    """Executa e opcionalmente imprime a reconciliação Meta × banco."""
    unidades, bloqueios_banco = carregar_estado_banco(
        connection_factory=connection_factory,
    )
    bloqueios_meta = coletar_bloqueios_meta(
        unidades,
        list_factory=meta_list_factory,
    )
    resultado = comparar_bloqueios(bloqueios_meta, bloqueios_banco)
    resultado["unidades_consultadas"] = bloqueios_meta

    if imprimir:
        imprimir_reconciliacao_bloqueios(
            resultado,
            mostrar_wa_id=mostrar_wa_id,
        )

    return resultado


def listar_bloqueados_de_cada_unidade(
    *,
    imprimir=True,
    mostrar_wa_id=False,
    connection_factory=None,
    meta_list_factory=None,
):
    """Lista o estado Meta por unidade sem compará-lo ao banco."""
    unidades, _ = carregar_estado_banco(
        connection_factory=connection_factory,
    )
    resultado = coletar_bloqueios_meta(
        unidades,
        list_factory=meta_list_factory,
    )

    if imprimir:
        print("===== BLOQUEADOS NA META POR UNIDADE =====")
        for unidade in resultado:
            print(_descricao_unidade(unidade))
            if unidade["status_meta"] != "ok":
                print(f"   ERRO META: {unidade['erro_meta']}")
                continue
            if not unidade["wa_ids_bloqueados"]:
                print("   - nenhum número bloqueado")
            for wa_id in unidade["wa_ids_bloqueados"]:
                print(
                    "   - "
                    + _formatar_wa_id(wa_id, mostrar=mostrar_wa_id)
                )

    return resultado


def imprimir_reconciliacao_bloqueios(resultado, *, mostrar_wa_id=False):
    print("===== RECONCILIAÇÃO DE BLOQUEIOS META × BANCO =====")
    print(
        "Escopo: somente WABAs e unidades atualmente cadastradas no banco."
    )
    print(f"sincronizados: {len(resultado['sincronizados'])}")
    print(f"somente_na_meta: {len(resultado['somente_meta'])}")
    print(f"somente_no_banco: {len(resultado['somente_banco'])}")
    print(
        "não_comparados_por_falha_meta: "
        f"{len(resultado['nao_comparados_banco'])}"
    )
    print(
        "vínculos_de_unidade_divergentes: "
        f"{len(resultado['vinculos_unidade_divergentes'])}"
    )
    print(f"falhas_meta: {len(resultado['falhas_meta'])}")

    _imprimir_grupo(
        "SINCRONIZADOS NO BANCO E NA META",
        resultado["sincronizados"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "SOMENTE NA META",
        resultado["somente_meta"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "SOMENTE NO BANCO / PENDENTES NA META",
        resultado["somente_banco"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "NÃO COMPARADOS POR FALHA DA META",
        resultado["nao_comparados_banco"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "VÍNCULO LOCAL DE UNIDADE DIVERGENTE",
        resultado["vinculos_unidade_divergentes"],
        mostrar_wa_id,
    )

    if resultado["falhas_meta"]:
        print("\nFALHAS DE COLETA META:")
        for falha in resultado["falhas_meta"]:
            print(
                f"   - {_descricao_unidade(falha)} | "
                f"erro={falha['erro_meta']}"
            )

    if _bloqueios_sincronizados(resultado):
        print("\nOK: banco e Meta estão sincronizados no escopo consultado.")


def criar_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Compara clientes bloqueados na Meta e no banco por unidade."
        ),
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)
    bloqueios = subparsers.add_parser(
        "blocked-users",
        help="compara bloqueados na Meta e em cliente_bloqueado_meta",
    )
    bloqueios.add_argument(
        "--show-wa-id",
        action="store_true",
        help="exibe o WA ID completo; por padrão mostra somente os 4 finais",
    )
    return parser


def executar_monitoramento_bloqueios():
    """Atalho local: executar o arquivo no PyCharm já gera o relatório."""
    configurar_ambiente_local()
    return reconciliar_bloqueios_meta_banco(
        imprimir=True,
        mostrar_wa_id=True,
    )


def main(argv=None):
    argumentos = sys.argv[1:] if argv is None else list(argv)
    if not argumentos:
        argumentos = ["blocked-users", "--show-wa-id"]

    args = criar_parser().parse_args(argumentos)
    try:
        resultado = reconciliar_bloqueios_meta_banco(
            mostrar_wa_id=args.show_wa_id,
        )
    except Exception as exc:
        print(
            f"RECONCILIACAO_FALHOU: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    if resultado["falhas_meta"]:
        return 2
    if not _bloqueios_sincronizados(resultado):
        return 1
    return 0


def _bloqueios_sincronizados(resultado):
    return not any((
        resultado["somente_meta"],
        resultado["somente_banco"],
        resultado["nao_comparados_banco"],
        resultado["vinculos_unidade_divergentes"],
        resultado["falhas_meta"],
    ))


def _imprimir_grupo(titulo, itens, mostrar_wa_id):
    if not itens:
        return
    print(f"\n{titulo}:")
    for item in itens:
        wa_id = _formatar_wa_id(
            item.get("wa_id_cliente"),
            mostrar=mostrar_wa_id,
        )
        nome = item.get("nome_cliente") or "nome não disponível"
        print(
            f"   - wa_id={wa_id} | nome={nome} | "
            f"{_descricao_unidade(item)}"
        )


def _descricao_unidade(item):
    return (
        f"unidade {item.get('id_unidade')} "
        f"{item.get('nome_unidade')} | "
        f"WABA ({item.get('waba_id')}) | "
        f"phone_id ({item.get('phone_id_unidade')})"
    )


def _extrair_wa_id_bloqueado(usuario):
    if isinstance(usuario, dict):
        wa_id = usuario.get("wa_id") or usuario.get("user_id") or usuario.get("id")
    else:
        wa_id = getattr(usuario, "wa_id", None) or getattr(usuario, "bsuid", None) or (usuario if isinstance(usuario, str) else None)
    return _normalizar_id(wa_id)


def _normalizar_id(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _escopo(item):
    return (
        _normalizar_id(item["waba_id"]),
        _normalizar_id(item["phone_id_unidade"]),
    )


def _ordenar_chaves(chaves):
    return sorted(chaves, key=lambda item: tuple(valor or "" for valor in item))


def _ordem_registro(item):
    return (
        item.get("id_unidade") or 0,
        item.get("wa_id_cliente") or "",
    )


def _ordem_unidade(item):
    return (
        item.get("id_unidade") or 0,
        item.get("waba_id") or "",
    )


def _formatar_wa_id(valor, *, mostrar):
    texto = _normalizar_id(valor) or "-"
    if mostrar or len(texto) <= 4:
        return texto
    return "*" * (len(texto) - 4) + texto[-4:]


if __name__ == "__main__":
    if len(sys.argv) == 1:
        executar_monitoramento_bloqueios()
    else:
        raise SystemExit(main())
