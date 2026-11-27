"""Repete a pergunta com o mesmo controle interativo oferecido pela etapa."""
from core.etapas_pos_venda import ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS
from core.integrations.whatsapp.messages.tratamentos.midia import PERGUNTAS_POR_TEXTO, avisar_sobre_midia
from .etapa3 import enviar_etapa3
from .etapa4 import enviar_etapa4
from .etapa5_pedidos import enviar_etapa5_pedidos
from .texto_pos_venda import enviar_texto_pos_venda

_INTERATIVOS = {
    ETAPA_PRODUTO: enviar_etapa3,
    ETAPA_ASSUNTO: enviar_etapa4,
    ETAPA_PEDIDOS: enviar_etapa5_pedidos,
}


def enviar_repeticao_midia(destinatario, remetente, etapa):
    if etapa in _INTERATIVOS:
        envio = _INTERATIVOS[etapa](destinatario, remetente, midia=True)
    else:
        texto = avisar_sobre_midia(PERGUNTAS_POR_TEXTO[etapa])
        envio = enviar_texto_pos_venda(destinatario, remetente, texto, etapa)
    return dict(envio, tratamento=True, tipo_tratamento="midia_na_etapa")
