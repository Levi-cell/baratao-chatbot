"""Tratamento universal após a apresentação das regras do canal."""

from core.etapas_pos_venda import (
    ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS,
    EVENTO_MIDIA_RECEBIDA, EVENTO_HUMANO_SOLICITADO,
    EVENTO_LIMITE_SEM_AVANCO,
)
from core.validacoes.produto_pos_venda import TIPOS_INTERATIVOS_PRODUTO
from core.validacoes.assunto_pos_venda import TIPOS_INTERATIVOS_ASSUNTO
from core.validacoes.pedidos_pos_venda import TIPOS_INTERATIVOS_PEDIDO

LIMITE_TURNOS_SEM_AVANCO = 3


def motivo_encaminhamento(contexto):
    if contexto.get("apresentacao_pendente"):
        return None
    mensagem = contexto["mensagem_cliente_atual"]
    tipo = mensagem.get("tipo_mensagem")
    interativos = {
        ETAPA_PRODUTO: TIPOS_INTERATIVOS_PRODUTO,
        ETAPA_ASSUNTO: TIPOS_INTERATIVOS_ASSUNTO,
        ETAPA_PEDIDOS: TIPOS_INTERATIVOS_PEDIDO,
    }
    if tipo != "text" and tipo not in interativos.get(contexto.get("id_etapa_atual"), ()):
        return EVENTO_MIDIA_RECEBIDA
    if tipo == "text" and "humano" in (mensagem.get("conteudo_texto") or "").casefold():
        return EVENTO_HUMANO_SOLICITADO
    if int(contexto.get("turnos_sem_avanco") or 0) >= LIMITE_TURNOS_SEM_AVANCO:
        return EVENTO_LIMITE_SEM_AVANCO
    return None


def setores_encaminhamento(produto):
    if produto == "moveis":
        return ("moveis",)
    if produto == "estofados":
        return ("sofas",)
    return ("sofas", "moveis")
