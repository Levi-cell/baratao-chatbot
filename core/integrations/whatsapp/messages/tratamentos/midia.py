"""Orientação de formato para entradas não suportadas no pós-venda."""
from core.etapas_pos_venda import ETAPA_NOME, ETAPA_CPF, ETAPA_DETALHES

AVISO_MIDIA = "Olha, só consigo entender mensagens de texto."

PERGUNTAS_POR_TEXTO = {
    ETAPA_NOME: "Me informe novamente o nome completo do titular da compra.",
    ETAPA_CPF: "Em uma única mensagem, me informe o CPF do titular da compra.",
    ETAPA_DETALHES: "Descreva em texto a sua situação e o que você precisa.",
}


def avisar_sobre_midia(pergunta):
    return f"{AVISO_MIDIA}\n\n{pergunta}"
