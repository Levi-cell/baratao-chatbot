"""Reconhece no painel os textos de encerramento gravados no histórico do Supera."""

import re


MENSAGEM_CLIENTE_MENOR_18_ETAPA6 = (
    "Como você tem menos de 18 anos, este atendimento precisa ser realizado "
    "por um adulto responsável.\n"
    "Peça a um adulto retornar nosso atendimento. "
    "Um abraço e até logo! 👋☺️"
)

MENSAGEM_DEPENDENTE_MENOR_5_ETAPA6 = (
    "No momento, esta unidade do Supera realiza treinamentos com crianças a "
    "partir de {idade_minima} anos. Quando {nome_dependente} completar {idade_minima} "
    "anos, você poderá entrar em contato "
    "novamente.\n"
    "Um abraço e até logo! 👋☺️"
)

MENSAGEM_SUPORTE_IDOSO_ETAPA6 = (
    "Certo, vou te passar o contato da nossa equipe para dar continuidade a sua experiência supera! 😊\n"
    "Para entrar em contato, basta clicar no botão abaixo."
)

MENSAGEM_IDADE_ACIMA_99_ETAPA6 = (
    "Certo, olha, para idades mais avançadas vamos precisar realizar uma pequena "
    "*anamnese* com um dos nossos consultores.\n"
    "Basta clicar no botão abaixo para falar com nosso time e iniciar a anamnese! 😊"
)

_MENSAGEM_SUPORTE_IDOSO_LEGADA_SEM_FAIXA = (
    "Certo, olha, para idades mais avançadas oferecemos um atendimento "
    "personalizado com o nosso time! 😊\n\n"
    "Para entrar em contato, basta clicar no botão abaixo."
)


def reconhecer_mensagem_suporte_idoso_etapa6(conteudo):
    """Reconhece resposta já persistida; não monta nem envia mensagem ao cliente."""
    texto = str(conteudo or "").strip()
    mensagens = (
        MENSAGEM_SUPORTE_IDOSO_ETAPA6,
        # Recuperação de envios anteriores à revisão de espaçamento; não reenviar.
        MENSAGEM_SUPORTE_IDOSO_ETAPA6.replace("\n", "\n\n"),
        _MENSAGEM_SUPORTE_IDOSO_LEGADA_SEM_FAIXA,
    )
    # O prefixo de retorno pode anteceder o corpo salvo; não interpretar como envio novo.
    return texto.endswith(mensagens)


def reconhecer_encerramento_etapa6(conteudo, tipo_mensagem):
    """Identifica somente corpos conhecidos; espaços e prefixos não mudam a decisão.

    O chamador deve comprovar a conversa, a etapa e o vínculo com a entrada.
    Esta função não consulta configurações nem altera a formatação dos envios.
    """
    texto = " ".join(str(conteudo or "").split())

    def termina_com(corpo):
        return texto.endswith(" ".join(corpo.split()))

    if tipo_mensagem == "interactive_cta_url":
        if any(termina_com(corpo) for corpo in (
            MENSAGEM_SUPORTE_IDOSO_ETAPA6,
            _MENSAGEM_SUPORTE_IDOSO_LEGADA_SEM_FAIXA,
        )):
            return {"categoria": "suporte"}
        universal = MENSAGEM_IDADE_ACIMA_99_ETAPA6 + "\n\n_Nosso time vai orientar os próximos passos. 🧡_"
        if any(termina_com(corpo) for corpo in (
            universal,
            universal.replace(" e iniciar a anamnese", ""),
        )):
            return {"categoria": "universal"}
        return None

    if tipo_mensagem != "text":
        return None
    if termina_com(MENSAGEM_CLIENTE_MENOR_18_ETAPA6):
        return {"categoria": "titular_menor"}

    # O mínimo aparece duas vezes no corpo. A referência exige que sejam iguais.
    modelo = " ".join(MENSAGEM_DEPENDENTE_MENOR_5_ETAPA6.split())
    padrao = re.escape(modelo)
    padrao = padrao.replace(re.escape("{idade_minima}"), r"(?P<minimo>[45])", 1)
    padrao = padrao.replace(re.escape("{idade_minima}"), r"(?P=minimo)")
    padrao = padrao.replace(re.escape("{nome_dependente}"), r"(?P<nome>.+?)")
    encontrado = re.search(padrao + r"$", texto)
    if encontrado:
        return {
            "categoria": "dependente_menor",
            "idade_minima": int(encontrado.group("minimo")),
            "nome_dependente": encontrado.group("nome"),
        }
    return None
