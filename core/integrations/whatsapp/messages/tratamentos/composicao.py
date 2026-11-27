"""Composição pura, sem decisão de fluxo, envio ou acesso a dados."""

import re


_ABERTURA_REDUNDANTE = re.compile(
    r"^(?:(?:Maravilha|Prazer), [^\n!]+![^\w\n]*\n\n[ ]*"
    r"|Que bom ver você aqui novamente, [^\n!]+!\n\n"
    r"|Perfeito![^\w\n]*\n\n)"
)


def aplicar_prefixo_retorno(texto, prefixo):
    """Aplica o mesmo prefixo uma vez ao envio e ao histórico."""
    if not prefixo or not isinstance(texto, str):
        return texto
    prefixo = prefixo.strip()
    if not prefixo:
        return texto
    corpo = texto.strip()
    if corpo == prefixo or corpo.startswith(prefixo + "\n\n"):
        return corpo
    corpo = _ABERTURA_REDUNDANTE.sub("", corpo, count=1).strip()
    return f"{prefixo}\n\n{corpo}" if corpo else prefixo
