"""Reconhece a opção da lista ou categorias distintas em uma frase."""
import re

from core.integrations.whatsapp.messages.etapa4_messages import OPCOES_ASSUNTO
from core.validacoes.texto_pos_venda import normalizar_texto

TIPOS_INTERATIVOS_ASSUNTO = frozenset({"interactive", "interactive_list", "interactive_button", "button"})
_OPCOES_DA_LISTA = {
    normalizar_texto(rotulo): valor
    for titulo, valor, descricao in OPCOES_ASSUNTO
    for rotulo in (titulo, descricao, f"assunto:{valor}") if rotulo
}
# Os títulos inequívocos da lista anterior continuam válidos em conversas abertas.
_OPCOES_DA_LISTA.update({"montagem": "montador", "avaria no produto": "assistencia"})
_TERMOS = {
    "entrega": re.compile(r"\b(?:previsao|previsoes|entregas?)\b"),
    "assistencia": re.compile(r"\b(?:avarias?|avariad[oa]s?|assistencia)\b"),
    "montador": re.compile(r"\b(?:montagem|montagens|montador(?:a|es|as)?|montar)\b"),
    "outros": re.compile(r"\b(?:outros|outro assunto|outra coisa|outras coisas)\b"),
}
_MISTO = re.compile(r"\b(?:misto|(?:dois|duas) ou mais (?:opcoes|assuntos)|mais de um assunto)\b")
ASSUNTOS = frozenset(valor for _, valor, _ in OPCOES_ASSUNTO)


def assunto_da_lista(texto):
    return _OPCOES_DA_LISTA.get(normalizar_texto(texto))


def extrair_assunto(texto):
    texto = normalizar_texto(texto)
    categorias = [categoria for categoria, expressao in _TERMOS.items() if expressao.search(texto)]
    if len(categorias) > 1 or _MISTO.search(texto):
        return "misto"
    return categorias[0] if categorias else None
