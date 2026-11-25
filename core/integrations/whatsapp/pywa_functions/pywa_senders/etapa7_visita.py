"""Apresenta a pergunta sobre visita à loja."""
from pywa.types import Button

from core.etapas_pos_venda import ETAPA_VISITA_LOJA
from core.integrations.whatsapp.messages.etapa7_visita_messages import MENSAGEM_VISITA, BOTOES_VISITA
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa7_visita(cliente_telefone, phone_id_unidade):
    botoes = [Button(title=titulo, callback_data=valor) for titulo, valor in BOTOES_VISITA]
    return enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, MENSAGEM_VISITA, ETAPA_VISITA_LOJA, botoes=botoes,
    )
