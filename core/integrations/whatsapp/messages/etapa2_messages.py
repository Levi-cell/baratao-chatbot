from core.integrations.whatsapp.messages.compartilhamento_contato import primeiro_nome


"""Pergunta e correção do CPF do titular na etapa 2."""

MENSAGEM_PADRAO_ETAPA2 = "Em uma única mensagem, me informe o CPF do titular da compra."

MENSAGEM_CPF_INVALIDO = (
    "Olha você esqueceu de digitar algum digito ou colocou um digito a mais "
    "no CPF, por favor em uma única mensagem informe seu CPF novamente"
)


def montar_mensagem_etapa2(nome_titular=None, *, contato_confirmado=False,
                          abertura=False, agora=None):
    nome = primeiro_nome(nome_titular)
    if contato_confirmado:
        inicio = f"Obrigado por compartilhar seu contato {nome}!" if nome else "Obrigado por compartilhar seu contato!"
    # A migração de 22/11/2026 podia colocar cadastros com nome e sem CPF
    # diretamente nesta etapa, antes da primeira resposta do Theo. A base
    # começou vazia. Hoje a saudação acontece na etapa 1, ao pedir o nome.
    # elif abertura:
    #     from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario
    #     saudacao = obter_saudacao_por_horario(agora)
    #     inicio = f"{saudacao}, {nome}!" if nome else f"{saudacao}!"
    #     inicio += " Sou o Theo, assistente do pós-venda."
    else:
        inicio = f"Certo {nome}." if nome else "Certo."
    return f"{inicio} {MENSAGEM_PADRAO_ETAPA2}"
