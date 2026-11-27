"""Mensagens da etapa 1 do pós-venda Baratão."""

from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario


MENSAGEM_PADRAO_ETAPA1 = (
    "{saudacao}, eu sou o Theo, assistente do pós-venda do Baratão e Atacadão! 😁\n\n"
    "Olha antes de começarmos peço que envie somente mensagens de texto!  "
    "Caso você não seja o titular da compra, recomendamos que direcione esse atendimento "
    "para o titular, caso foi você que fez a compra ignore este aviso.\n\n"
    "Antes de te encaminhar para um atendimento humano, preciso coletar algumas informações "
    "suas tá ? vai levar apenas alguns minutos, para começar, me informe o nome completo "
    "do titular da compra."
)
MENSAGEM_NOME_INVALIDO = (
    "Desculpa, não consegui entender, em uma única mensagem me informe "
    "apenas seu nome completo"
)


def montar_mensagem_etapa1(agora=None):
    return MENSAGEM_PADRAO_ETAPA1.format(saudacao=obter_saudacao_por_horario(agora))
