"""Extrator determinístico de produto; palavras inteiras e negação contextual.

"Não recebi meus móveis" relata um problema; "não quero falar de móveis"
exclui um setor. Contradição ou dúvida pede correção, sem adivinhar.
"""
import re

from core.validacoes.texto_pos_venda import normalizar_texto

PRODUTOS = frozenset({"estofados", "moveis", "ambos"})
TIPOS_INTERATIVOS_PRODUTO = frozenset({"interactive", "interactive_button", "button"})
_SETORES = frozenset({"estofados", "moveis"})
_MENCAO = re.compile(
    r"\b(?:estofados?|moveis|movel|sofas?|ambos|ambas|(?:os|dos|nos) dois|(?:as|das) duas)\b"
)
_NEGATIVA = re.compile(
    r"\b(?:nao|nem|sem|exceto|menos|tirando)"
    r"(?:\s+(?:quero|queria|gostaria|desejo|preciso|vou|e|eh|falar|tratar|conversar|"
    r"sobre|de|do|da|dos|das|com|o|os|a|as|meu|minha|meus|minhas|"
    r"setor|assunto|produto|produtos|atendimento|nenhum|nenhuma))*\s*$"
)
_LIGACAO = re.compile(r"\s*(?:(?:e|ou|nem|o|os|a|as|de|do|da|dos|das)\s+)*$")


def produto_do_botao(texto):
    """Só valores do menu; inclui o rótulo anterior da mesma opção Ambos."""
    return {
        "produto:estofados": "estofados", "apenas estofados": "estofados",
        "produto:moveis": "moveis", "apenas moveis": "moveis",
        "produto:ambos": "ambos", "estofados e moveis": "ambos",
        "moveis e estofados": "ambos",
    }.get(normalizar_texto(texto))


def extrair_produto(texto):
    texto = normalizar_texto(texto)
    if not texto or re.search(r"\b(?:nenhum|nenhuma|talvez|nao sei|nao tenho certeza)\b", texto):
        return None
    # "Não só móveis, mas também estofados" afirma ambos os produtos.
    texto = re.sub(r"\bnao (?:so|apenas|somente)\b", "", texto)
    positivos, negativos = set(), set()
    fim_anterior, negativa_anterior = 0, False
    for mencao in _MENCAO.finditer(texto):
        prefixo = texto[fim_anterior:mencao.start()]
        # Propagar uma exclusão apenas na enumeração: "não quero móveis nem estofados".
        # Uma nova oração ou verbo de problema não herda essa rejeição do setor.
        negativa = bool(_NEGATIVA.search(prefixo)) or (
            negativa_anterior and bool(_LIGACAO.fullmatch(prefixo))
        )
        if re.match(r"\s+nao\s*(?:[,;.!?]|$)", texto[mencao.end():]):
            negativa = True
        palavra = mencao.group()
        if palavra in {"moveis", "movel"}:
            setores = {"moveis"}
        elif palavra.startswith(("estofado", "sofa")):
            setores = {"estofados"}
        else:
            setores = _SETORES
        (negativos if negativa else positivos).update(setores)
        fim_anterior, negativa_anterior = mencao.end(), negativa
    if positivos & negativos:
        return None
    # Rejeitar apenas uma das duas categorias permite escolher a restante.
    # Rejeitar ambas deixa o conjunto vazio e exige uma nova resposta.
    escolhidos = positivos or (_SETORES - negativos if negativos else set())
    if escolhidos == _SETORES:
        return "ambos"
    return next(iter(escolhidos)) if len(escolhidos) == 1 else None
