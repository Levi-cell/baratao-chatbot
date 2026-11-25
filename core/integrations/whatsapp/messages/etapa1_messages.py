"""Mensagens da etapa 1 do pós-venda Baratão."""

MENSAGEM_PADRAO_ETAPA1 = (
    "Olá eu sou o Theo, assistente do pós-venda, antes de te passar para um "
    "consultor humano, vou precisar fazer algumas perguntinhas para entender "
    "melhor como podemos te ajudar, vai levar apenas alguns minutos, para "
    "começar me informe o Nome completo do titular da compra.\n\n"
    "Nota: por aqui consigo entender apenas mensagens de texto."
)
MENSAGEM_NOME_INVALIDO = (
    "Desculpa, não consegui entender, em uma única mensagem me informe "
    "apenas seu nome completo"
)


def montar_mensagem_etapa1():
    return MENSAGEM_PADRAO_ETAPA1
