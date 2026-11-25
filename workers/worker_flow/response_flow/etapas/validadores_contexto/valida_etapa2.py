"""Extrai CPF e produz o evento da etapa, sem I/O ou efeitos no cadastro."""

from core.etapas_pos_venda import EVENTO_CPF_VALIDO
from core.validacoes.cpf_titular import extrair_cpf_titular


def validar_contexto_etapa2(contexto):
    cpf = extrair_cpf_titular(contexto["mensagem_cliente_atual"].get("conteudo_texto"))
    if cpf is None:
        return None
    return {"evento": EVENTO_CPF_VALIDO, "cpf_titular": cpf}
