"""Resolução do cliente sob o lock de cada identificador apresentado pela Meta."""
from dataclasses import dataclass

from core.repositories.atendimento import conciliacao_cliente as conciliacao
from core.repositories.atendimento import identidade_cliente as repo
from core.repositories.seguranca.turno_cliente import avaliar_turno_cliente_para_fila


class IdentidadeDivergente(ValueError):
    pass


def resolver_cliente(dados, central, cursor):
    telefone, uid = dados.get("cliente_telefone"), dados.get("user_id_origem")
    chaves = ([f"wa:{telefone}"] if telefone else []) + ([f"bs:{central}:{uid}"] if uid else [])
    if not chaves:
        raise IdentidadeDivergente("Entrada sem identidade")
    for chave in sorted(chaves):
        repo.serializar_chave(chave,cursor)
    dono = repo.cliente_telefone(telefone,cursor) if telefone else None
    alias = repo.buscar_alias(central,uid,cursor) if uid else None
    if alias and (not alias[1] or (dono and alias[0] != dono)):
        raise IdentidadeDivergente("Identificadores conflitantes ou alias inativo")
    cliente = dono or (alias[0] if alias else None)
    if cliente is None:
        cliente = repo.criar_cliente(telefone,cursor)
    if uid and not alias:
        if repo.alias_vigente_do_cliente(central, cliente, cursor):
            raise IdentidadeDivergente("Cliente já possui outro BSUID vigente nesta central")
        repo.inserir_alias(central,uid,cliente,dados["id_hash_msg"],cursor)
        repo.conferir_alias(central,uid,cliente,cursor)
    if telefone and alias and not alias[2]:
        anterior = repo.dados_telefone(cliente,cursor)
        if anterior and anterior != telefone:
            raise IdentidadeDivergente("Mudança de telefone sem prova de continuidade")
        if anterior is None:
            repo.definir_telefone(cliente,telefone,cursor)
    repo.atualizar_username(cliente,dados.get("username_origem"),dados["received_data_hora"],cursor)
    return cliente


def rotacionar_bsuid(central, sistema, wamid, cursor):
    anterior, novo = sistema.get("previous_user_id"), sistema.get("user_id")
    if not anterior or not novo or anterior == novo:
        return False
    for uid in sorted((anterior,novo)):
        repo.serializar_chave(f"bs:{central}:{uid}",cursor)
    alias = repo.buscar_alias(central,anterior,cursor)
    if not alias or not alias[1]:
        return False
    if repo.buscar_alias(central,novo,cursor):
        raise IdentidadeDivergente("Novo identificador já vinculado")
    # Um telefone abandonado pode ser reatribuído a outra pessoa. A continuação
    # deste cadastro exige o identificador vinculado e um novo contato oficial.
    repo.preservar_bloqueio_na_rotacao(central, alias[0], novo, cursor)
    repo.definir_telefone(alias[0], None, cursor)
    repo.aposentadoria_alias(central,anterior,cursor)
    repo.inserir_alias(central,novo,alias[0],wamid,cursor)
    repo.suspender_alias(central,novo,cursor)
    repo.trocar_bsuid_pendente(central,anterior,novo,cursor)
    return True


@dataclass(frozen=True)
class ResultadoConciliacao:
    # Sem ID global, o CPF é guardado somente no atendimento deste turno.
    cadastro_para_cpf: int | None
    cache: dict | None = None


def escolher_cadastro_vencedor(candidatos, origem, cpf, telefone):
    """Compara dados anteriores à etapa 2. O maior ID desempata cada grupo."""
    prioridades = []
    for cliente, cpf_anterior, wa, tem_historico in candidatos:
        if cliente == origem and cpf_anterior is None and not tem_historico:
            continue  # O provisório não disputa o desempate com as fichas antigas.
        mesmo_cpf = cpf_anterior == cpf
        mesmo_telefone = wa == telefone
        if mesmo_cpf or mesmo_telefone:
            prioridades.append((mesmo_cpf, mesmo_telefone, cliente))
    return max(prioridades)[2] if prioridades else origem


def conciliar_apos_cpf(contexto, cpf, cursor):
    """Decide antes de gravar o CPF novo. Os efeitos usam a transação do worker."""
    origem = contexto["id_cliente"]
    telefone = contexto.get("telefone_compartilhado") or contexto.get("wa_id_confirmado")
    if not telefone:
        return ResultadoConciliacao(origem)

    central = contexto["id_central"]
    conversa = contexto["id_conversa"]
    uid = contexto.get("bsuid_vigente")
    if uid:
        repo.serializar_chave(f"bs:{central}:{uid}", cursor)
    repo.serializar_chave(f"cpf:{cpf}", cursor)
    repo.serializar_chave(f"wa:{telefone}", cursor)
    candidatos = conciliacao.candidatos_para_cpf(origem, cpf, telefone, conversa, cursor)
    vencedor = escolher_cadastro_vencedor(candidatos, origem, cpf, telefone)
    telefones = {cliente: wa for cliente, _, wa, _ in candidatos}
    perdedores = [cliente for cliente in telefones if cliente != vencedor]
    if not perdedores:
        return ResultadoConciliacao(vencedor)

    clientes = list(telefones)
    conciliacao.bloquear_chats(clientes, cursor)
    aliases = conciliacao.bloquear_aliases(clientes, cursor)
    if uid and (central, uid, origem, True, False) not in aliases:
        return ResultadoConciliacao(None)
    if contexto.get("telefone_compartilhado"):
        if conciliacao.telefone_em_conferencia(central, uid, cursor) != telefone:
            return ResultadoConciliacao(None)
    elif telefones.get(origem) != telefone:
        return ResultadoConciliacao(None)

    entrada = contexto["mensagem_cliente_atual"]
    numeros_envolvidos = sorted({wa for wa in telefones.values() if wa} | {telefone})
    if (conciliacao.identificador_bloqueado(numeros_envolvidos, clientes, cursor)
            or conciliacao.ha_bloqueio_temporario(clientes, cursor)
            or conciliacao.ha_trabalho_em_andamento(clientes, numeros_envolvidos, conversa,
                                                   entrada["id_mensagem_fila"], cursor)):
        return ResultadoConciliacao(None)
    for cliente in clientes:
        if cliente != origem:
            turno = avaliar_turno_cliente_para_fila(cursor, cliente, contexto["id_phone_unidade"],
                                                   entrada["received_data_hora"], usar_lock=True)
            if not turno["pode_enfileirar"]:
                return ResultadoConciliacao(None)

    # Um BSUID histórico não pode encaminhar outro remetente ao telefone novo.
    # Conserve vínculos vigentes do vencedor em outras centrais se CPF e telefone coincidem.
    mesmo_titular_e_numero = any(cliente == vencedor and anterior == cpf and wa == telefone
                                 for cliente, anterior, wa, _ in candidatos)
    aposentados = []
    for c, u, dono, ativo, _ in aliases:
        rota_atual = (c, u, dono) == (central, uid, origem)
        outra_central_preservada = c != central and dono == vencedor and mesmo_titular_e_numero
        if ativo and not (rota_atual or outra_central_preservada):
            repo.aposentadoria_alias(c, u, cursor)
            aposentados.append((c, u))

    conciliacao.garantir_chats_do_vencedor(vencedor, perdedores, cursor)
    conciliacao.mover_fila(perdedores, vencedor, cursor)
    conciliacao.mover_conversas(perdedores, vencedor, cursor)
    conciliacao.mover_aliases(perdedores, vencedor, cursor)
    conciliacao.liberar_telefone(perdedores, telefone, cursor)
    conciliacao.atualizar_cadastro_pela_conversa(conversa, vencedor, telefone, cursor)
    conciliacao.guardar_telefone_compartilhado(conversa, None, cursor)
    conciliacao.excluir_chats_vazios(perdedores, cursor)
    conciliacao.excluir_cadastros_redundantes(perdedores, cursor)
    return ResultadoConciliacao(vencedor, {
        "cliente": vencedor, "telefone": telefone, "central": central, "uid": uid,
        "telefones_antigos": [wa for wa in telefones.values() if wa and wa != telefone],
        "aliases_antigos": aposentados,
    })
