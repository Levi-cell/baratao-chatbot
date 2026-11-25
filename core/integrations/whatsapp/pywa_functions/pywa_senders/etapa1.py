"""Envios da abertura e da coleta do nome; não altera banco nem cache."""

from core.etapas_pos_venda import ETAPA_NOME
from core.integrations.whatsapp.messages.etapa1_messages import (
    MENSAGEM_NOME_INVALIDO, montar_mensagem_etapa1,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa1(cliente_telefone, phone_id_unidade):
    return enviar_texto_pos_venda(cliente_telefone, phone_id_unidade, montar_mensagem_etapa1(), ETAPA_NOME)


def enviar_nome_invalido(cliente_telefone, phone_id_unidade):
    resultado = enviar_texto_pos_venda(cliente_telefone, phone_id_unidade, MENSAGEM_NOME_INVALIDO, ETAPA_NOME)
    return dict(resultado, tratamento=True, tipo_tratamento="nome_invalido")
