"""Apresentação e repetição da pergunta de produto; sem validar a entrada."""

from pywa.types import Button

from core.etapas_pos_venda import ETAPA_PRODUTO
from core.integrations.whatsapp.messages.etapa3_messages import (
    montar_mensagem_etapa3, BOTOES_PRODUTO, MENSAGEM_PRODUTO_INVALIDO, RODAPE_PRODUTO,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa3(cliente_telefone, phone_id_unidade, *, nome_titular=None, invalido=False):
    botoes = [
        Button(title=titulo, callback_data=identificador)
        for titulo, identificador in BOTOES_PRODUTO
    ]
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade,
        MENSAGEM_PRODUTO_INVALIDO if invalido else montar_mensagem_etapa3(nome_titular),
        ETAPA_PRODUTO, botoes=botoes, rodape=RODAPE_PRODUTO,
    )
    if invalido:
        envio.update(tratamento=True, tipo_tratamento="produto_invalido")
    return envio
