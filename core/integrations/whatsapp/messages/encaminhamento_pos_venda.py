"""Textos compartilhados do encaminhamento humano, fora das etapas de coleta."""

from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario

ROTULOS_POS_VENDA = {
    "atacadao": "Pós-venda Atacadão",
    "baratao": "Pós-venda Baratão",
}
MENSAGEM_POR_GRUPO = {
    "atacadao": "Sua compra é do Atacadão. Toque no botão abaixo para falar com o pós-venda do Atacadão.",
    "baratao": "Sua compra é do Baratão. Toque no botão abaixo para falar com o pós-venda do Baratão.",
}
MENSAGEM_SEM_NOTA = (
    "Vou te passar os contatos do pós-venda do Atacadão e do Baratão. "
    "Deslize para o lado e toque no botão da rede onde você fez a compra."
)
MENSAGEM_NOTA_PERDIDA = (
    "Tudo bem se você perdeu a nota. Deslize para o lado para ver os dois contatos "
    "e toque no pós-venda da rede onde você fez a compra: Atacadão ou Baratão."
)
MENSAGEM_DUAS_REDES = (
    "Suas notas são de compras no Atacadão e no Baratão. "
    "Deslize para o lado e escolha o pós-venda da rede com que deseja falar primeiro."
)
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
