import logging

from django.http import JsonResponse

from core.database.connection_aws import get_conn
from core.integrations.whatsapp.tools.usuarios import bloquear_usuario_meta
from core.logging_config import short_value
from core.repositories.seguranca.bloqueio_meta import (
    consultar_protecao_remetente,
)


logger = logging.getLogger("webhook.bloqueio_meta_guard")


def verificar_protecao_remetente(
    wa_id_cliente,
    phone_id_unidade,
    identificadores,
    conta_origem,
):
    """
    Intercepta apenas a denylist existente.

    Repetição de etapa é encaminhamento ao pós-venda, decidido pelo worker;
    não promove bloqueio na Meta.

    O banco é confirmado antes da chamada externa à Meta. Se a Meta recusar,
    a mensagem continua sendo ignorada e a próxima mensagem fará nova
    tentativa.
    """
    if not wa_id_cliente or not phone_id_unidade:
        return None, wa_id_cliente

    consulta = _consultar_cliente_marcado_para_bloqueio(
        wa_id_cliente,
        phone_id_unidade,
        identificadores=identificadores,
        conta_origem=conta_origem,
    )

    if not consulta["banco_ok"]:
        return JsonResponse(
            {
                "status": "unavailable",
                "reason": "blocklist_validation_unavailable",
            },
            status=503,
        ), None

    if consulta["protecao"] is None:
        return JsonResponse({"status": "ignored", "reason": "central_incompativel"}), None

    central, chave_flood = consulta["protecao"]
    if central is None:
        return None, chave_flood or wa_id_cliente

    meta_ok = False

    try:
        bloquear_usuario_meta(wa_id_cliente, phone_id_unidade, central=central)
        meta_ok = True
        logger.warning(
            "bloqueio_meta_reconfirmado | acao=bloquear_novamente "
            "wa_id_cliente=%s phone_id_unidade=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
        )

    except Exception as exc:
        logger.warning(
            "bloqueio_meta_retentativa_falhou | "
            "acao=ignorar_e_tentar_na_proxima_mensagem "
            "wa_id_cliente=%s phone_id_unidade=%s erro=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
            exc,
        )

    logger.warning(
        "mensagem_ignorada | motivo=cliente_marcado_bloqueio_meta "
        "acao=nao_enfileirar wa_id_cliente=%s phone_id_unidade=%s meta_ok=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        meta_ok,
    )
    return JsonResponse({
        "status": "ignored",
        "reason": "cliente_marcado_bloqueio_meta",
    }), None


def _consultar_cliente_marcado_para_bloqueio(
    wa_id_cliente,
    phone_id_unidade,
    identificadores,
    conta_origem,
):
    conn = None

    try:
        conn = get_conn(application_name="webhook_chatbot")
        cursor = conn.cursor()

        protecao = consultar_protecao_remetente(
            identificadores,
            phone_id_unidade,
            conta_origem,
            cursor,
        )

        conn.commit()
        return {
            "banco_ok": True,
            "protecao": protecao,
        }

    except Exception as exc:
        if conn:
            conn.rollback()

        logger.exception(
            "bloqueio_meta_consulta_falhou | "
            "acao=retornar_503_para_reentrega "
            "wa_id_cliente=%s phone_id_unidade=%s erro=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
            exc,
        )
        return {
            "banco_ok": False,
            "central": None,
        }

    finally:
        if conn:
            conn.close()
