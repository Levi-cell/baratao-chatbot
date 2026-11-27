"""O relato é livre. O tratamento universal tem prioridade sobre a coleta."""


def validar_contexto_detalhes(contexto):
    entrada = contexto["mensagem_cliente_atual"]
    texto = entrada.get("conteudo_texto")
    if entrada.get("tipo_mensagem") == "text" and isinstance(texto, str):
        return texto.strip() or None
    return None
