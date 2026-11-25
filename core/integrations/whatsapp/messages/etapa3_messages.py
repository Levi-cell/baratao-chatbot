"""Pergunta de produto para a primeira compra informada ou uma nova conversa."""

MENSAGEM_PRODUTO = "Sobre qual tipo de produto você quer falar?"
MENSAGEM_PRODUTO_INVALIDO = "Não entendi, sobre qual tipo de produto você quer falar?"
RODAPE_PRODUTO = "Selecione apenas uma opção abaixo."
BOTOES_PRODUTO = (
    ("Apenas Estofados", "produto:estofados"),
    ("Apenas Móveis", "produto:moveis"),
    ("Estofados e Móveis", "produto:ambos"),
)


def montar_mensagem_etapa3(nome_titular=None):
    if nome_titular:
        return f"Olá, {nome_titular}! {MENSAGEM_PRODUTO}"
    return MENSAGEM_PRODUTO
