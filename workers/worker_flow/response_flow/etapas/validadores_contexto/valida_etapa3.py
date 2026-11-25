"""Escolha do produto: validação contextual, sem I/O nem persistência."""
from core.etapas_pos_venda import EVENTO_PRODUTO_ESCOLHIDO
from core.validacoes.produto_pos_venda import (
    TIPOS_INTERATIVOS_PRODUTO, extrair_produto, produto_do_botao,
)


def validar_contexto_etapa3(contexto):
    mensagem = contexto["mensagem_cliente_atual"]
    tipo, texto = mensagem.get("tipo_mensagem"), mensagem.get("conteudo_texto")
    if tipo in TIPOS_INTERATIVOS_PRODUTO:
        produto = produto_do_botao(texto)
    elif tipo == "text":
        produto = extrair_produto(texto)
    else:
        return None
    return {"evento": EVENTO_PRODUTO_ESCOLHIDO, "produto": produto} if produto else None
