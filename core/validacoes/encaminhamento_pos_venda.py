"""Classificação da entrada e destino do encaminhamento humano."""
from core.etapas_pos_venda import ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS
from core.validacoes.produto_pos_venda import TIPOS_INTERATIVOS_PRODUTO
from core.validacoes.assunto_pos_venda import TIPOS_INTERATIVOS_ASSUNTO
from core.validacoes.pedidos_pos_venda import TIPOS_INTERATIVOS_PEDIDO

LIMITE_TURNOS_SEM_AVANCO = 3

_INTERATIVOS_POR_ETAPA = {
    ETAPA_PRODUTO: TIPOS_INTERATIVOS_PRODUTO,
    ETAPA_ASSUNTO: TIPOS_INTERATIVOS_ASSUNTO,
    ETAPA_PEDIDOS: TIPOS_INTERATIVOS_PEDIDO,
}


def entrada_nao_suportada(etapa, tipo):
    return tipo != "text" and tipo not in _INTERATIVOS_POR_ETAPA.get(etapa, ())


def pediu_humano(tipo, texto):
    return tipo == "text" and "humano" in (texto or "").casefold()


def setores_encaminhamento(produto):
    if produto == "moveis":
        return ("moveis",)
    if produto == "estofados":
        return ("sofas",)
    return ("sofas", "moveis")
