"""Textos compartilhados do encaminhamento humano, fora das etapas de coleta."""

from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario

MENSAGEM_PRODUTO_NAO_INFORMADO = (
    "Como não consegui identificar se sua compra foi de estofados ou de móveis, "
    "vou te passar o contato de cada setor.\n\n"
    "Deslize para o lado para ver as duas opções, caso tenha comprado tanto móveis e estofados, "
    "selecione a opção para o caso que deseja resolver primeiro."
)
MENSAGEM_AMBOS_PRODUTOS = (
    "Como você comprou tanto estofados quanto móveis, vou te passar os contatos "
    "dos dois setores de pós-venda.\n\n"
    "Deslize para o lado para ver a outra opção, e selecione a opção que quer resolver primeiro."
)
ROTULO_ESTOFADOS = "Pós-venda Estofados"
ROTULO_MOVEIS = "Pós-venda Móveis"
MENSAGEM_POR_SETOR = {
    "sofas": "Para falar sobre seus estofados, toque abaixo.",
    "moveis": "Para falar sobre seus móveis, toque abaixo.",
}


MENSAGEM_FINAL = "Obrigado pelas informações. Use o botão abaixo para falar com o pós-venda."
AVISO_ASSISTENCIA = (
    "Olha, vale lembra que em caso de avarias, o protocolo é tirar fotos e vídeos e ir pessoalmente à loja "
    "em que realizou a compra para abrir um chamado. Lembrando que a garantia é de 90 dias "
    "desde o recebimento do produto.Desconsidere esse aviso caso você já tenha ido à loja pessoalmente e seu "
    "produto esteja dentro da garantia."
)


def mensagem_de_contato(texto, assunto):
    return f"{AVISO_ASSISTENCIA}\n\n{texto}" if assunto in {"assistencia", "misto"} else texto


def montar_resumo_encaminhamento(cadastro, produto=None, assunto=None, *,
                                 pedidos_com_filial=(), perdeu_nota=None, detalhes=None):
    rotulos = {"moveis": "Móveis", "estofados": "Estofados", "ambos": "Móveis e Estofados"}
    campos = [
        ("Titular da compra", cadastro.get("nome_titular")),
        ("CPF do titular", cadastro.get("cpf_titular")),
        ("Produto", rotulos.get(produto)),
        ("Assunto", "Assistência" if assunto == "assistencia" else (assunto or "").capitalize()),
    ]
    linhas = [f"- {campo}: {valor}" for campo, valor in campos if valor]
    notas = ["Perdi a nota"] if perdeu_nota else [
        f"{numero} ({filial})" if filial else numero for numero, filial in pedidos_com_filial
    ]
    if len(notas) == 1:
        linhas.append(f"- Número da nota: {notas[0]}")
    elif notas:
        linhas.append("- Números das notas:")
        linhas.extend(f"  • {nota}" for nota in notas)
    saudacao = obter_saudacao_por_horario().lower()
    abertura = f"Olá, {saudacao}! Fui encaminhado(a) pelo assistente Theo e gostaria de atendimento humano."
    lista = "\n".join(linhas)
    return "\n\n".join(bloco for bloco in (abertura, lista, detalhes) if bloco)
