"""Validação e provisionamento do remetente no cadastro de centrais."""

import logging
import re

from django import forms
from requests.exceptions import RequestException

from core.cache.cache_unidade import CacheUnidadesIndisponivel, validar_cache_unidades_disponivel_ou_erro
from core.integrations.whatsapp.tools.ativando_numero import registrar_numero_whatsapp
from core.integrations.whatsapp.tools.ativando_waba_id import ativar_waba_id
from core.integrations.whatsapp.tools.validando_phone_waba import validar_phone_number_id_da_waba
from .models import CentralPosVenda


logger = logging.getLogger("admin.central")


def _meta_confirmou(resultado):
    status, resposta = resultado
    return 200 <= status < 300 and isinstance(resposta, dict) and resposta.get("success") is True


class CentralPosVendaForm(forms.ModelForm):
    class Meta:
        model = CentralPosVenda
        fields = "__all__"

    def clean_telefone(self):
        valor = self.cleaned_data["telefone"]
        digitos = re.sub(r"[+ ().-]", "", valor)
        if not re.fullmatch(r"[1-9][0-9]{7,14}", digitos):
            raise forms.ValidationError("Informe o telefone da central com o código do país e DDD.")
        return digitos

    def _post_clean(self):
        super()._post_clean()
        # A validação do modelo e a de unicidade já terminaram. Edições de
        # atendimento (inclusive suspender a central) dispensam provisionamento.
        mudou_remetente = {"waba_id", "phone_number_id", "waac_id"}.intersection(self.changed_data)
        provisionar = self.instance._state.adding or bool(mudou_remetente)
        if self.errors or not (provisionar or "telefone" in self.changed_data):
            return

        central = self.instance
        try:
            validar_cache_unidades_disponivel_ou_erro()
        except CacheUnidadesIndisponivel:
            self.add_error(None, "O Redis está indisponível. Tente cadastrar o remetente novamente.")
            return

        try:
            vinculo = validar_phone_number_id_da_waba(
                central.waba_id, central.phone_number_id, waac_id=central.waac_id, telefone=central.telefone,
            )
            if not _meta_confirmou(vinculo):
                self.add_error(None, "A Meta não confirmou o telefone e os identificadores do remetente desta central.")
                return
            if not provisionar:
                return
            if not _meta_confirmou(ativar_waba_id(central.waba_id)):
                self.add_error("waba_id", "A Meta não confirmou a assinatura da conta para receber webhooks.")
                return
            registro = registrar_numero_whatsapp(
                central.phone_number_id, id_registro=central.waac_id or central.phone_number_id,
            )
            if not _meta_confirmou(registro):
                self.add_error("phone_number_id", "A conta foi assinada, mas a Meta não confirmou o registro do número.")
        except (RequestException, RuntimeError, ValueError):
            logger.exception("provisionamento_central_sem_confirmacao")
            self.add_error(None, "Não foi possível confirmar o cadastro completo na Meta. Confira o registro e tente novamente.")
