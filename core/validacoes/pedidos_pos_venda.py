"""Números impressos na nota. O sufixo de dois dígitos identifica a filial."""
import re

from core.etapas_pos_venda import (
    ETAPA_VISITA_LOJA, ETAPA_DETALHES, EVENTO_PEDIDOS_ASSISTENCIA, EVENTO_PEDIDOS_DEMAIS_ASSUNTOS,
    EVENTO_NOTA_PERDIDA_ASSISTENCIA, EVENTO_NOTA_PERDIDA_DEMAIS_ASSUNTOS,
)
from core.validacoes.assunto_pos_venda import ASSUNTOS

FORMATO_PEDIDO = re.compile(r"[0-9]+\.[0-9]{2}")
_ROTULO = re.compile(r"\b(?:pedidos?|notas?|n[uú]meros?):(?=\S)", re.IGNORECASE)
_ENVOLTORIOS = {"(": ")", "[": "]", '"': '"', "“": "”", "'": "'"}
_ROTULOS_PEDIDO = {"nota", "notas", "pedido", "pedidos", "numero", "número", "numeros", "números"}
_LIGACOES_LISTA = {"e", "ou", ",", ";"}
_FECHOS_DE_FRASE = {"por", "obrigado", "obrigada"}
_PALAVRAS_DE_CONTEXTO = _ROTULOS_PEDIDO | _LIGACOES_LISTA | _FECHOS_DE_FRASE | {"é", "são", "fiscal"}
TIPOS_INTERATIVOS_PEDIDO = frozenset({"interactive", "interactive_button", "button"})


def _palavras_da_resposta(texto):
    palavras = []
    for trecho in _ROTULO.sub(r"\g<0> ", texto).split():
        # "234,01" é uma tentativa com separador incorreto. Em "234.01,345.1"
        # a vírgula separa duas notas e precisamos verificar as duas.
        separador_final = trecho.endswith((",", ";"))
        trecho = trecho.rstrip("!?,;").removesuffix(".")
        # Um par pode envolver a lista inteira, ou cada número ter o seu par.
        if (len(trecho) > 2 and _ENVOLTORIOS.get(trecho[0]) == trecho[-1]
                and trecho[-1] not in trecho[1:-1]):
            trecho = trecho[1:-1]
        partes = [trecho] if re.fullmatch(r"[0-9]+,[0-9]{1,2}", trecho) else re.split("([,;])", trecho)
        for parte in partes:
            if len(parte) > 2 and _ENVOLTORIOS.get(parte[0]) == parte[-1]:
                parte = parte[1:-1]
            if parte:
                palavras.append(parte)
        if separador_final:
            palavras.append(",")
    return palavras


def _indice_rotulo_anterior(palavras, indice):
    if indice and palavras[indice - 1].casefold() in {"é", "são"}:
        indice -= 1
    if indice > 0 and palavras[indice - 1].rstrip(":").casefold() in _ROTULOS_PEDIDO:
        return indice - 1
    return None


def _itens_de_nota(palavras):
    """Inclui códigos sem algarismos quando apresentados como itens de uma lista."""
    com_digito = [any(c.isdecimal() for c in p) for p in palavras]
    itens = com_digito.copy()
    for i, palavra in enumerate(palavras):
        if com_digito[i]:
            # Um inteiro seguido de dois-pontos pode anunciar a quantidade.
            # Um identificador como AB345.09: ainda precisa passar pela validação.
            if i + 1 < len(palavras) and com_digito[i + 1] and re.fullmatch(r"[0-9]+:", palavra):
                itens[i] = False
            continue
        termo = palavra.casefold().rstrip(":")
        if termo in _PALAVRAS_DE_CONTEXTO:
            continue
        parece_codigo = palavra.isupper() or all(not c.isalnum() for c in palavra)
        antes_de_nota = i + 2 < len(palavras) and palavras[i + 1].casefold() in _LIGACOES_LISTA and com_digito[i + 2]
        depois_de_nota = i >= 2 and palavras[i - 1].casefold() in _LIGACOES_LISTA and com_digito[i - 2]
        fim_de_item = i + 1 == len(palavras) or palavras[i + 1].casefold() in _LIGACOES_LISTA
        rotulo = _indice_rotulo_anterior(palavras, i)
        if rotulo is not None:
            anterior = palavras[rotulo - 1].casefold() if rotulo else ""
            declarado = palavras[rotulo].endswith(":") or anterior in (_LIGACOES_LISTA | {"outra", "outro"})
            itens[i] = parece_codigo or (declarado and fim_de_item)
        elif parece_codigo:
            itens[i] = antes_de_nota or (depois_de_nota and fim_de_item)
    return itens


def identificar_candidatos_pedido(texto):
    """Conta as tentativas antes de validar formato, filial ou duplicidade."""
    if not isinstance(texto, str):
        return []
    palavras = _palavras_da_resposta(texto)
    itens = _itens_de_nota(palavras)
    candidatos = []
    i = 0
    while i < len(palavras):
        if not itens[i]:
            i += 1
            continue
        inicio = i
        grupo = [palavras[i]]
        i += 1
        while i < len(palavras):
            if palavras[i].casefold() in _LIGACOES_LISTA and i + 1 < len(palavras) and itens[i + 1]:
                i += 1
            if not itens[i]:
                break
            grupo.append(palavras[i])
            i += 1

        rotulado = _indice_rotulo_anterior(palavras, inicio) is not None
        encerra_lista = i == len(palavras) or palavras[i].casefold() in (_FECHOS_DE_FRASE | {",", ";"})
        tem_ponto = any("." in item for item in grupo)
        if not (rotulado or tem_ponto or (encerra_lista and (inicio == 0 or len(grupo) > 1))):
            continue
        # Só um inteiro isolado pode ser quantidade em "nota 234.01 e 2 cadeiras".
        # Em "234.01 e AB345 aqui", o último código também precisa ser validado.
        for posicao, item in enumerate(grupo):
            if not item.isdecimal() or posicao < len(grupo) - 1 or encerra_lista or (rotulado and posicao == 0):
                candidatos.append(item)
    return candidatos


def extrair_pedidos(texto):
    """Retorna números distintos apenas quando todos os candidatos têm formato válido."""
    candidatos = identificar_candidatos_pedido(texto)
    if all(FORMATO_PEDIDO.fullmatch(numero) for numero in candidatos):
        return list(dict.fromkeys(candidatos))
    return []


def pedidos_de_filiais_cadastradas(numeros, codigos_filiais):
    if not codigos_filiais:
        raise ValueError("O catálogo de filiais precisa estar disponível para validar pedidos.")
    return all(
        isinstance(numero, str) and FORMATO_PEDIDO.fullmatch(numero) and numero[-2:] in codigos_filiais
        for numero in numeros
    )


def transicao_dos_pedidos(assunto, *, perdeu_nota):
    if assunto not in ASSUNTOS:
        raise ValueError("Falta um assunto válido no atendimento para encaminhar o pedido.")
    if assunto == "assistencia":
        evento = EVENTO_NOTA_PERDIDA_ASSISTENCIA if perdeu_nota else EVENTO_PEDIDOS_ASSISTENCIA
        return evento, ETAPA_VISITA_LOJA
    evento = EVENTO_NOTA_PERDIDA_DEMAIS_ASSUNTOS if perdeu_nota else EVENTO_PEDIDOS_DEMAIS_ASSUNTOS
    return evento, ETAPA_DETALHES
