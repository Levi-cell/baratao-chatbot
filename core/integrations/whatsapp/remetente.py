"""Identidade empresarial usada pela Messages API durante um turno do pós-venda."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pywa import WhatsApp
from pywa.api import GraphAPI


from core.database.connection_aws import get_conn
from core.repositories.unidades.consultas import buscar_id_registro_meta


def recurso_registro_meta(phone_number_id):
    with get_conn(application_name="registro_numero_meta") as conn, conn.cursor() as cursor:
        return buscar_id_registro_meta(str(phone_number_id), cursor)


@dataclass(frozen=True)
class RemetenteCentral:
    phone_number_id: str
    messaging_account_id: str
    waac_id: str | None

    @property
    def id_envio(self):
        return self.waac_id or self.phone_number_id


_REMETENTE_DO_TURNO = ContextVar("remetente_do_turno", default=None)


@contextmanager
def usar_remetente_central(central, phone_id_entrada):
    remetente = RemetenteCentral(
        phone_number_id=central["phone_number_id"],
        messaging_account_id=central["messaging_account_id"],
        waac_id=central["waac_id"],
    )
    if remetente.phone_number_id != phone_id_entrada or not remetente.messaging_account_id:
        raise ValueError("Identidade Meta da central incompatível com a entrada da fila.")
    token = _REMETENTE_DO_TURNO.set(remetente)
    try:
        yield
    finally:
        _REMETENTE_DO_TURNO.reset(token)


class _GraphAPICentral(GraphAPI):
    # PyWa 4.5 constrói texto e interativos no mesmo ponto, mas ainda não expõe
    # messaging_account_id. Preserva a serialização, o parsing de erros e os WAMIDs do SDK.
    remetente: RemetenteCentral | None = None

    def _request(self, method, endpoint, **kwargs):
        remetente = self.remetente
        corpo = kwargs.get("json") or {}
        if (remetente and method == "POST" and endpoint.endswith("/messages")
                and ("to" in corpo or "recipient" in corpo)):
            if endpoint != f"/{remetente.id_envio}/messages":
                raise ValueError("O destinatário deve ser atendido pelo remetente da central.")
            kwargs["json"] = {**corpo, "messaging_account_id": remetente.messaging_account_id}
        return super()._request(method, endpoint, **kwargs)


class WhatsAppCentral(WhatsApp):
    _api_cls = _GraphAPICentral

    def __init__(self, *, phone_id, **opcoes):
        remetente = _REMETENTE_DO_TURNO.get()
        if remetente and remetente.phone_number_id != phone_id:
            raise ValueError("O número de envio difere da central do turno.")
        super().__init__(phone_id=remetente.id_envio if remetente else phone_id, **opcoes)
        if remetente:
            self.api.remetente = remetente
