"""Apresenta a pergunta aberta sobre a situação."""
from core.etapas_pos_venda import ETAPA_DETALHES
from core.integrations.whatsapp.messages.etapa9_detalhes_messages import MENSAGEM_DETALHES
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa9_detalhes(cliente_telefone, phone_id_unidade):
    return enviar_texto_pos_venda(cliente_telefone, phone_id_unidade, MENSAGEM_DETALHES, ETAPA_DETALHES)
