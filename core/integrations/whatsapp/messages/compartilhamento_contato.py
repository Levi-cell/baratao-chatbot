from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario

def primeiro_nome(nome_titular):
    partes = (nome_titular or "").split(maxsplit=1)
    return partes[0] if partes else ""

def mensagem_contato(nome_titular, *, repeticao=False, reconfirmacao=False,
                     abertura=False, agora=None):
    if repeticao:
        return "Para seguir com o atendimento, toque no botão abaixo e compartilhe seu número de WhatsApp."
    nome = primeiro_nome(nome_titular)
    inicio = f"{nome}, preciso" if nome else "Preciso"
    verbo = "reconfirmar" if reconfirmacao else "confirmar"
    texto = (f"{inicio} {verbo} seu número de WhatsApp para continuar o atendimento. "
             "Toque no botão abaixo para compartilhá-lo comigo.")
    if abertura:
        return f"{obter_saudacao_por_horario(agora)}! Sou o Theo, assistente do pós-venda.\n\n{texto}"
    return texto
