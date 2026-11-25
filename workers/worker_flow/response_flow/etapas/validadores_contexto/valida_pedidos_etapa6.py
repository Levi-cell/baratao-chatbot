"""Uma resposta válida contém pedidos cadastráveis ou a escolha explícita de nota perdida."""
from core.validacoes.pedidos_pos_venda import (
    TIPOS_INTERATIVOS_PEDIDO, identificar_candidatos_pedido, pedidos_de_filiais_cadastradas,
)
from core.validacoes.texto_pos_venda import normalizar_texto


def validar_contexto_pedidos(contexto):
    """Retorna (pedidos, quantidade informada). None pede correção, [] indica nota perdida."""
    mensagem = contexto["mensagem_cliente_atual"]
    tipo, texto = mensagem["tipo_mensagem"], mensagem.get("conteudo_texto")
    if tipo in TIPOS_INTERATIVOS_PEDIDO:
        perdeu_nota = normalizar_texto(texto) in {"perdi a nota", "pedidos:nota_perdida"}
        return ([] if perdeu_nota else None), 0
    if tipo != "text":
        return None, 0
    if normalizar_texto(texto) == "perdi a nota":
        return [], 0
    candidatos = identificar_candidatos_pedido(texto)
    if candidatos and pedidos_de_filiais_cadastradas(candidatos, contexto["codigos_filiais"]):
        return list(dict.fromkeys(candidatos)), len(candidatos)
    return None, len(candidatos)
