"""Validação de formato do nome completo; não consulta listas de nomes."""

import unicodedata


def normalizar_nome_titular(texto):
    """Retorna o nome aceito sem ponto final, ou None para entrada inválida."""
    if not isinstance(texto, str):
        return None
    nome = unicodedata.normalize("NFC", texto).strip()
    if nome.endswith("."):
        nome = nome[:-1]
    if not nome or nome != nome.strip():
        return None
    for indice, caractere in enumerate(nome):
        if caractere.isalpha() or caractere.isspace():
            continue
        if (caractere == "-" and 0 < indice < len(nome) - 1
                and nome[indice - 1].isalpha() and nome[indice + 1].isalpha()):
            continue
        return None
    partes = nome.split()
    if len(partes) < 2:
        return None
    return " ".join(partes)
