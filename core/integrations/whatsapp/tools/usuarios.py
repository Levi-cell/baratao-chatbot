import logging

from core.database.connection_aws import get_conn
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.remetente import usar_remetente_central
from core.logging_config import short_value
from core.repositories.seguranca.bloqueio_meta import buscar_central_para_bloqueio


logger = logging.getLogger("whatsapp.block")


def cliente_de_bloqueio(phone_id_unidade, central=None):
    phone_id = str(phone_id_unidade).strip()
    if central is None:
        # Chamadores sem contexto de turno (inclusive o desbloqueio administrativo).
        with get_conn(application_name="whatsapp_bloqueio") as conn, conn.cursor() as cursor:
            central = buscar_central_para_bloqueio(phone_id, cursor)
        if central is None:
            raise ValueError("Phone Number ID sem central cadastrada para bloqueio.")

    with usar_remetente_central(central, phone_id):
        return conta_wa(phone_id)


def bloquear_usuario_meta(wa_id_cliente, phone_id_unidade, *, central=None):
    cliente_wa = cliente_de_bloqueio(phone_id_unidade, central)
    resultado = cliente_wa.block_users(users=[str(wa_id_cliente)])

    if resultado.errors or resultado.failed_users or not resultado.added_users:
        raise RuntimeError("A Meta não confirmou o bloqueio do contato.")

    logger.warning(
        "whatsapp_usuario_bloqueado | acao=bloquear wa_id_cliente=%s phone_id_unidade=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
    )

    return resultado


def desbloquear_usuario_meta(wa_id_cliente, phone_id_unidade):
    cliente_wa = cliente_de_bloqueio(phone_id_unidade, central=None)
    resultado = cliente_wa.unblock_users(users=[str(wa_id_cliente)])

    if not resultado.removed_users:
        raise RuntimeError("A Meta não confirmou o desbloqueio do contato.")

    logger.warning(
        "whatsapp_usuario_desbloqueado | acao=desbloquear wa_id_cliente=%s phone_id_unidade=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
    )

    return resultado
