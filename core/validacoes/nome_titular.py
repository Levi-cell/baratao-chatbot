"""Validação de formato do nome completo; não consulta listas de nomes."""

import re
import unicodedata

from core.validacoes.apresentacao_nome import NAO_NOMES


# A apresentação é opcional. Uma vez reconhecida, só o trecho que sobra
# pode ser o nome. Isso evita gravar "Eu me chamo" quando falta o sobrenome.
_SAUDACAO = re.compile(r"^(?:ol[áa]|oi|bom dia|boa tarde|boa noite)[ ,!.:-]+", re.I)
_APRESENTACAO = re.compile(
    r"^(?:(?:pode me chamar de|(?:o|a) titular(?: da compra)? se chama)|(?:eu\s+)?me\s+chamo|(?:ele|ela)\s+se\s+chama|"
    r"(?:o\s+)?(?:meu\s+nome(?:\s+completo)?|nome(?:\s+completo)?\s+"
    r"(?:dele|dela|d[oa]\s+titular(?:\s+da\s+compra)?))\s+(?:é|e|eh)|"
    r"(?:eu\s+)?sou(?:\s+[oa])?|(?:[oa]\s+)?titular(?:\s+da\s+compra)?\s+(?:é|e)|"
    r"aqui\s+(?:quem\s+fala\s+)?(?:é|e)(?:\s+[oa])?|"
    r"nome(?:\s+completo)?(?=\s*:))(?=\s|:|$)\s*:?\s*", re.I,
)
_CONECTORES = {"da", "de", "do", "das", "dos", "e"}
_TERMOS_DE_FRASE = {"eu", "me", "chamo", "meu", "minha", "nome", "titular", "compra",
                    "sou", "ele", "ela", "dele", "dela", "quero", "preciso", "não",
                    "ajuda", "pedido", "esqueci", "sei", "gostaria", "quem", "é"}


def normalizar_nome_titular(texto):
    """Retorna o nome aceito sem ponto final, ou None para entrada inválida."""
    if not isinstance(texto, str):
        return None
    nome = unicodedata.normalize("NFC", texto).strip()
    nome = _SAUDACAO.sub("", nome)
    apresentacao = _APRESENTACAO.match(nome)
    if apresentacao:
        nome = nome[apresentacao.end():]
        nome = re.sub(r"^[oa]\s+", "", nome, flags=re.I)
        nome = re.split(r"\s+e\s+(?:quero|queria|preciso|gostaria|vim)\b", nome,
                        maxsplit=1, flags=re.I)[0]
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
    palavras = [p.casefold() for p in partes]
    primeiro = "".join(c for c in unicodedata.normalize("NFD", palavras[0])
                       if not unicodedata.combining(c)) if palavras else ""
    if (primeiro in NAO_NOMES or len(partes) < 2 or palavras[0] in _CONECTORES or palavras[-1] in _CONECTORES
            or _TERMOS_DE_FRASE.intersection(palavras)):
        return None
    return " ".join(partes)
