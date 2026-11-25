"""Textos compartilhados do encaminhamento humano, fora das etapas de coleta."""

MENSAGEM_ENCAMINHAMENTO = (
    "Olha como só consigo entender apenas mensagens de texto vou te enviar "
    "o contato dos nossos consultores humanos para o setor de móveis e de estofados"
)
ROTULO_ESTOFADOS = "Pós-venda Estofados"
ROTULO_MOVEIS = "Pós-venda Móveis"
MENSAGEM_POR_SETOR = {
    "sofas": "Para falar sobre seu estofado, toque abaixo.",
    "moveis": "Para falar sobre seus móveis, toque abaixo.",
}


def montar_resumo_encaminhamento(cadastro, produto=None, assunto=None):
    """Usa somente o cadastro já validado, nunca a entrada bruta do cliente."""
    resumo = "Olá! Fui encaminhado pelo assistente Theo e gostaria de atendimento humano."
    if cadastro.get("nome_titular"):
        resumo += "\nTitular da compra: " + cadastro["nome_titular"]
    if produto:
        if cadastro.get("cpf_titular"):
            resumo += "\nCPF do titular: " + cadastro["cpf_titular"]
        rotulos = {"moveis": "Móveis", "estofados": "Estofados", "ambos": "Estofados e Móveis"}
        resumo += "\nProduto: " + rotulos[produto]
    if assunto:
        resumo += "\nAssunto: " + ("Assistência" if assunto == "assistencia" else assunto.capitalize())
    return resumo
