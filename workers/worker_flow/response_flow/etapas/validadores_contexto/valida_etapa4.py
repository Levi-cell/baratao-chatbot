"""Valida a resposta da lista de assuntos ou um pedido escrito pelo cliente."""
from core.etapas_pos_venda import EVENTO_ASSUNTO_ESCOLHIDO
from core.validacoes.assunto_pos_venda import TIPOS_INTERATIVOS_ASSUNTO, assunto_da_lista, extrair_assunto


def validar_contexto_etapa4(contexto):
    mensagem = contexto["mensagem_cliente_atual"]
    tipo, texto = mensagem.get("tipo_mensagem"), mensagem.get("conteudo_texto")
    if tipo in TIPOS_INTERATIVOS_ASSUNTO:
        assunto = assunto_da_lista(texto)
    elif tipo == "text":
        assunto = extrair_assunto(texto)
    else:
        return None
    return {"evento": EVENTO_ASSUNTO_ESCOLHIDO, "assunto": assunto} if assunto else None
