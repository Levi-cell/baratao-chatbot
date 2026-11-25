"""Extrai um CPF pelo formato acordado, sem cálculo de dígitos verificadores."""

import re


# Começa em uma palavra que contenha dígitos, preservando letras misturadas.
# Inclui símbolos entre trechos numéricos para não aceitar, por exemplo, os
# primeiros 11 dígitos de "01234567890@1". Rótulos como "CPF:" ficam de fora.
_TOKENS = re.compile(
    r"(?<!\w)\w*[0-9]\w*(?:(?:[./\\+\-]\w+)|(?:[^\w\s]+(?=[0-9])\w+))*"
)
_FORMATO_CPF = re.compile(r"[0-9]+(?:[.\-][0-9]+)*")


def extrair_cpf_titular(texto):
    """Devolve 11 dígitos ASCII ou None se ausente/ambíguo.

    Somente pontos e hífens ASCII podem separar os dígitos; são opcionais.
    Outros símbolos internos invalidam o candidato, sem remoção silenciosa.
    Números separados por espaços não são concatenados; texto ao redor não
    faz parte do documento. Repetir o mesmo CPF na mensagem não cria
    ambiguidade, mas dois CPFs diferentes criam.
    """
    if not isinstance(texto, str):
        return None
    encontrados = set()
    for token in _TOKENS.findall(texto):
        if not _FORMATO_CPF.fullmatch(token):
            continue
        candidato = token.replace(".", "").replace("-", "")
        if len(candidato) == 11:
            encontrados.add(candidato)
    return next(iter(encontrados)) if len(encontrados) == 1 else None
