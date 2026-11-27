import logging

from django.http import JsonResponse

from core.cache.runtime.cache_flood_redis import avaliar_flood_redis
from core.cache.cache_flood_memoria import avaliar_flood_memoria
from core.database.connection_aws import get_conn
from core.integrations.whatsapp.tools.usuarios import (
    bloquear_usuario_meta,
)
from core.integrations.whatsapp.identidade_cliente import identificador_entrada
from core.logging_config import short_value
from core.repositories.seguranca.bloqueio_meta import (
    buscar_central_para_bloqueio,
    contar_eventos_flood_banco,
    limpar_eventos_flood_antigos,
    registrar_cliente_bloqueado_meta_banco,
    registrar_evento_flood_banco,
)
from .alerta_flood_memoria import registrar_alerta_flood_memoria


logger = logging.getLogger("webhook.flood_guard")

REGRAS_FLOOD = (
    {
        "nome": "rajada_curta",
        "limite": 15,
        "janela_segundos": 5,
    },
)


def responder_se_flood(data, *, chave_flood=None):
    phone_id_unidade = _extrair_phone_number_id(data)
    wa_id_cliente = _extrair_cliente_telefone(data)
    id_hash_msg = _extrair_id_hash_msg(data)

    flood = bloquear_cliente_se_flood(
        wa_id_cliente,
        phone_id_unidade,
        id_hash_msg,
        chave_flood=chave_flood,
    )

    if not flood["bloqueado"]:
        return None

    logger.warning(
        "mensagem_ignorada | motivo=%s regra=%s "
        "acao=bloqueio_local_nao_enfileirar cliente=%s phone_number_id=%s "
        "total=%s persistencia_ok=%s meta_ok=%s",
        flood["motivo"],
        flood.get("regra"),
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        flood["total"],
        flood.get("persistencia_ok"),
        flood.get("meta_ok"),
    )

    if flood.get("reentregar"):
        return JsonResponse(
            {
                "status": "unavailable",
                "reason": flood["motivo"],
            },
            status=503,
        )

    return JsonResponse({
        "status": "ignored",
        "reason": flood["motivo"],
    })


def bloquear_cliente_se_flood(
    wa_id_cliente,
    phone_id_unidade,
    id_hash_msg,
    nome_cliente=None,
    *, chave_flood=None,
):
    if not wa_id_cliente or not phone_id_unidade or not id_hash_msg:
        return {
            "bloqueado": False,
            "motivo": "dados_invalidos",
            "total": 0,
            "regra": None,
            "meta_ok": None,
        }

    rate_redis = avaliar_flood_redis(
        chave_flood or wa_id_cliente,
        phone_id_unidade,
        id_hash_msg,
        regras=REGRAS_FLOOD,
    )

    if rate_redis["redis_ok"]:
        if rate_redis["flood"]:
            return _bloquear_e_registrar(
                wa_id_cliente,
                phone_id_unidade,
                origem="redis",
                total=rate_redis["total"],
                regra=rate_redis["regra"],
            )

        return {
            "bloqueado": False,
            "motivo": "abaixo_limite_redis",
            "total": rate_redis["total"],
            "regra": None,
            "meta_ok": None,
        }

    rate_banco = _avaliar_flood_banco(
        chave_flood or wa_id_cliente,
        phone_id_unidade,
        id_hash_msg,
    )

    if rate_banco["flood"]:
        return _bloquear_e_registrar(
            wa_id_cliente,
            phone_id_unidade,
            origem="banco",
            total=rate_banco["total"],
            regra=rate_banco["regra"],
        )

    if not rate_banco["banco_ok"]:
        rate_memoria = avaliar_flood_memoria(
            chave_flood or wa_id_cliente,
            phone_id_unidade,
            id_hash_msg,
            regras=REGRAS_FLOOD,
        )

        if rate_memoria["flood"]:
            return _bloquear_via_memoria_e_alertar(
                wa_id_cliente,
                phone_id_unidade,
                total=rate_memoria["total"],
                regra=rate_memoria["regra"],
                id_hash_msg=id_hash_msg,
            )

        return {
            "bloqueado": False,
            "motivo": rate_memoria["motivo"],
            "total": rate_memoria["total"],
            "regra": None,
            "meta_ok": None,
        }

    return {
        "bloqueado": False,
        "motivo": rate_banco["motivo"],
        "total": rate_banco["total"],
        "regra": None,
        "meta_ok": None,
    }


def _avaliar_flood_banco(wa_id_cliente, phone_id_unidade, id_hash_msg):
    conn = None

    try:
        conn = get_conn(application_name="webhook_chatbot")
        cursor = conn.cursor()

        registrar_evento_flood_banco(
            wa_id_cliente,
            phone_id_unidade,
            id_hash_msg,
            cursor,
        )
        maior_total = 0
        total = 0
        regra_estourada = None

        for regra in REGRAS_FLOOD:
            total = contar_eventos_flood_banco(
                wa_id_cliente,
                phone_id_unidade,
                cursor,
                janela_segundos=regra["janela_segundos"],
            )

            maior_total = max(maior_total, total)

            if total >= regra["limite"]:
                regra_estourada = regra
                break

        limpar_eventos_flood_antigos(cursor)

        conn.commit()

        return {
            "banco_ok": True,
            "flood": regra_estourada is not None,
            "total": total if regra_estourada else maior_total,
            "motivo": "banco",
            "regra": regra_estourada["nome"] if regra_estourada else None,
        }

    except Exception as exc:
        if conn:
            conn.rollback()

        logger.warning(
            "rate_limit_banco_falhou | acao=seguir_fluxo wa_id_cliente=%s phone_id_unidade=%s erro=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
            exc,
        )
        return {
            "banco_ok": False,
            "flood": False,
            "total": 0,
            "motivo": "banco_indisponivel",
            "regra": None,
        }

    finally:
        if conn:
            conn.close()


def _bloquear_via_memoria_e_alertar(
    wa_id_cliente,
    phone_id_unidade,
    total,
    regra,
    id_hash_msg,
):
    resultado = _bloquear_e_registrar(
        wa_id_cliente,
        phone_id_unidade,
        origem="memoria",
        total=total,
        regra=regra,
    )

    registrar_alerta_flood_memoria(
        wa_id_cliente=wa_id_cliente,
        phone_id_unidade=phone_id_unidade,
        origem="memoria",
        regra=regra,
        total=total,
        meta_ok=resultado.get("meta_ok"),
        motivo=resultado["motivo"],
        id_hash_msg=id_hash_msg,
        erro_meta=resultado.get("erro_meta"),
    )

    logger.warning(
        "flood_bloqueado_memoria | acao=alertar regra=%s "
        "wa_id_cliente=%s phone_id_unidade=%s total=%s "
        "persistencia_ok=%s meta_ok=%s reentregar=%s",
        regra,
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        total,
        resultado.get("persistencia_ok"),
        resultado.get("meta_ok"),
        resultado.get("reentregar"),
    )
    return resultado


def _bloquear_e_registrar(wa_id_cliente, phone_id_unidade, origem, total, regra):
    resultado = {
        "bloqueado": True,
        "motivo": f"flood_{origem}",
        "total": total,
        "regra": regra,
        "persistencia_ok": False,
        "meta_ok": None,
        "erro_meta": None,
        "reentregar": False,
    }
    central = None
    try:
        with get_conn(application_name="webhook_chatbot") as conn, conn.cursor() as cursor:
            central = buscar_central_para_bloqueio(phone_id_unidade, cursor)
            if central is None:
                resultado["motivo"] += "_unidade_nao_cadastrada"
                return resultado
            registrar_cliente_bloqueado_meta_banco(wa_id_cliente, central["id_central"], cursor)
    except Exception:
        logger.exception("flood_persistencia_falhou | phone_id_unidade=%s", short_value(phone_id_unidade))
        resultado["motivo"] += "_persistencia_local_falhou" if central else "_banco_indisponivel"
        resultado["reentregar"] = True
        return resultado

    # O contexto da conexão psycopg já confirmou a denylist antes do HTTP.
    resultado["persistencia_ok"] = True
    try:
        bloquear_usuario_meta(wa_id_cliente, phone_id_unidade, central=central)
        resultado["meta_ok"] = True
    except Exception as exc:
        resultado["meta_ok"] = False
        resultado["erro_meta"] = str(exc)
        resultado["motivo"] += "_meta_falhou"
        logger.warning(
            "flood_bloqueio_meta_falhou | acao=repetir_em_nova_mensagem id_central=%s erro=%s",
            central["id_central"], type(exc).__name__,
        )
    return resultado


def _extrair_phone_number_id(data):
    value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    metadata = value.get("metadata", {})
    return metadata.get("phone_number_id")


def _extrair_cliente_telefone(data):
    value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    return identificador_entrada(value)


def _extrair_id_hash_msg(data):
    value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    messages = value.get("messages", [{}])
    return messages[0].get("id") if messages else None
