"""Pergunta e correção do CPF do titular na etapa 2."""

MENSAGEM_PADRAO_ETAPA2 = "Certo agora em uma única mensagem me informe seu CPF."

MENSAGEM_CPF_INVALIDO = (
    "Olha você esqueceu de digitar algum digito ou colocou um digito a mais "
    "no CPF, por favor em uma única mensagem informe seu CPF novamente"
)


def montar_mensagem_etapa2(nome_titular=None):
    if nome_titular:
        return f"Olá, {nome_titular}! Em uma única mensagem me informe seu CPF."
    return MENSAGEM_PADRAO_ETAPA2
