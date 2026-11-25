"""Envia a pergunta de pedidos após a escolha do assunto."""
from pywa.types import Button

from core.etapas_pos_venda import ETAPA_PEDIDOS
from core.integrations.whatsapp.messages.etapa6_pedidos_messages import (
    BOTAO_NOTA_PERDIDA, MENSAGEM_PEDIDOS, MENSAGEM_PEDIDO_INVALIDO, MENSAGEM_PEDIDOS_INVALIDOS,
)
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa6_pedidos(cliente_telefone, phone_id_unidade, *, quantidade_para_correcao=None):
    mensagem = MENSAGEM_PEDIDOS
    if quantidade_para_correcao is not None:
        mensagem = MENSAGEM_PEDIDOS_INVALIDOS if quantidade_para_correcao >= 2 else MENSAGEM_PEDIDO_INVALIDO
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, mensagem,
        ETAPA_PEDIDOS,
        botoes=[Button(title=BOTAO_NOTA_PERDIDA, callback_data="pedidos:nota_perdida")],
    )
    if quantidade_para_correcao is not None:
        envio.update(tratamento=True, tipo_tratamento="pedido_invalido")
    return envio
