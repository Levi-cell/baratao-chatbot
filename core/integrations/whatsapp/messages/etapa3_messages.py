"""Pergunta de produto para a primeira compra informada ou uma nova conversa."""

MENSAGEM_PRODUTO = "Sobre qual tipo de produto você quer falar?"
MENSAGEM_PRODUTO_INVALIDO = "Não entendi, sobre qual tipo de produto você quer falar?"
RODAPE_PRODUTO = "Selecione apenas uma opção abaixo."
BOTOES_PRODUTO = (
    ("Apenas Estofados", "produto:estofados"),
    ("Apenas Móveis", "produto:moveis"),
    ("Estofados e Móveis", "produto:ambos"),
)


from core.integrations.whatsapp.messages.compartilhamento_contato import primeiro_nome
from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario


def montar_mensagem_etapa3(nome_titular=None):
    if nome_titular:
        return f"{obter_saudacao_por_horario()}, {primeiro_nome(nome_titular)}! {MENSAGEM_PRODUTO}"
    return MENSAGEM_PRODUTO
