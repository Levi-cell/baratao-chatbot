"""Interpreta a resposta ao nome; a entrada de saudação não passa aqui."""

from core.etapas_pos_venda import EVENTO_NOME_VALIDO_FALTA_CPF
from core.validacoes.nome_titular import normalizar_nome_titular


def validar_contexto_etapa1(contexto):
    nome = normalizar_nome_titular(contexto["mensagem_cliente_atual"].get("conteudo_texto"))
    if nome is None:
        return None
    return {"evento": EVENTO_NOME_VALIDO_FALTA_CPF, "nome_titular": nome}
