"""Envio da pergunta ou correção do CPF, sem decidir a próxima etapa."""

from core.etapas_pos_venda import ETAPA_CPF
from core.integrations.whatsapp.messages.etapa2_messages import (
    montar_mensagem_etapa2, MENSAGEM_CPF_INVALIDO,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa2(cliente_telefone, phone_id_unidade, *, nome_titular=None, abertura=False):
    return enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, montar_mensagem_etapa2(nome_titular, abertura=abertura), ETAPA_CPF,
    )


def enviar_cpf_invalido(cliente_telefone, phone_id_unidade):
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, MENSAGEM_CPF_INVALIDO, ETAPA_CPF,
    )
    return dict(envio, tratamento=True, tipo_tratamento="cpf_invalido")
