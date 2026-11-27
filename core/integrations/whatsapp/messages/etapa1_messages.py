"""Mensagens da etapa 1 do pós-venda Baratão."""

from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario


MENSAGEM_PADRAO_ETAPA1 = (
    "{saudacao}! Sou o Theo, assistente do pós-venda ☺️. Para começar, me informe o nome "
    "completo do titular da compra. Lembrando que por aqui só consigo entender mensagens "
    "de texto, caso você não seja o titular da compra recomendamos que direcione esse "
    "atendimento para o titular da compra."
)
MENSAGEM_NOME_INVALIDO = (
    "Desculpa, não consegui entender, em uma única mensagem me informe "
    "apenas seu nome completo"
)


def montar_mensagem_etapa1(agora=None):
    return MENSAGEM_PADRAO_ETAPA1.format(saudacao=obter_saudacao_por_horario(agora))
