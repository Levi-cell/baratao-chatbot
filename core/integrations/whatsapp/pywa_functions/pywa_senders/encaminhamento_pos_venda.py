"""Um contato para o produto escolhido ou o carrossel para os dois setores."""

import os
import re
from urllib.parse import quote, urlsplit

from pywa.types import ImageCarouselCard, URLButton

from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO, EVENTO_SITUACAO_INFORMADA
from core.integrations.whatsapp.messages.encaminhamento_pos_venda import (
    MENSAGEM_AMBOS_PRODUTOS, MENSAGEM_PRODUTO_NAO_INFORMADO, MENSAGEM_POR_SETOR,
    MENSAGEM_FINAL, ROTULO_ESTOFADOS, ROTULO_MOVEIS, mensagem_de_contato, montar_resumo_encaminhamento,
)
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot
from core.validacoes.encaminhamento_pos_venda import setores_encaminhamento
from .texto_pos_venda import enviar_texto_pos_venda


def _resumo_do_atendimento(contexto):
    return montar_resumo_encaminhamento(
        contexto.get("cadastro") or {}, contexto.get("produto"), contexto.get("assunto"),
        pedidos_com_filial=contexto.get("pedidos_com_filial", ()), perdeu_nota=contexto.get("perdeu_nota"),
        detalhes=contexto.get("detalhes"),
    )


def _botao_contato(central, setor, resumo):
    numero = central.get(f"telefone_{setor}")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", str(numero or "")):
        raise ValueError("Telefone de pós-venda inválido.")
    return URLButton(
        title=ROTULO_ESTOFADOS if setor == "sofas" else ROTULO_MOVEIS,
        url=f"https://wa.me/{numero}?text={quote(resumo, safe='')}",
    )


def montar_cartoes(contexto):
    central = contexto["central"]
    base = os.getenv("WHATSAPP_MIDIAS_BASE_URL", "").strip().rstrip("/")
    url = urlsplit(base)
    if url.scheme != "https" or not url.netloc or url.query or url.fragment or url.username:
        raise ValueError("Configure WHATSAPP_MIDIAS_BASE_URL com a URL HTTPS pública das imagens.")
    if central.get("telefone_sofas") == central.get("telefone_moveis"):
        raise ValueError("A central precisa dos dois contatos distintos de pós-venda.")
    resumo = _resumo_do_atendimento(contexto)
    return [
        ImageCarouselCard(
            image=f"{base}/{arquivo}.png",
            buttons=_botao_contato(central, setor, resumo),
        )
        for arquivo, setor in (("estofados", "sofas"), ("moveis", "moveis"))
    ]


def enviar_encaminhamento(contexto, evento):
    mensagem = contexto["mensagem_cliente_atual"]
    phone = mensagem["id_phone_unidade"]
    telefone = contexto.get("destinatario_envio", mensagem.get("cliente_telefone"))
    setores = setores_encaminhamento(contexto.get("produto"))
    conclusao = evento == EVENTO_SITUACAO_INFORMADA
    if len(setores) == 1:
        setor = setores[0]
        texto = MENSAGEM_FINAL if conclusao else MENSAGEM_POR_SETOR[setor]
        envio = enviar_texto_pos_venda(
            telefone, phone, mensagem_de_contato(texto, contexto.get("assunto")),
            ETAPA_ENCAMINHAMENTO, botoes=_botao_contato(contexto["central"], setor, _resumo_do_atendimento(contexto)),
        )
        if not conclusao:
            envio["tipo_tratamento"] = evento
        envio[f"encaminhado_{setor}"] = contexto["central"][f"telefone_{setor}"]
        return envio

    texto = MENSAGEM_AMBOS_PRODUTOS if contexto.get("produto") == "ambos" else MENSAGEM_PRODUTO_NAO_INFORMADO
    texto = mensagem_de_contato(texto, contexto.get("assunto"))
    cartoes = montar_cartoes(contexto)
    try:
        resposta = conta_wa(phone).send_carousel(to=telefone, body=texto, cards=cartoes)
        wamid = extrair_id_hash_msg_bot(resposta)
    except Exception as exc:
        raise ErroEnvioMeta(
            "Falha ao enviar contatos do pós-venda", id_etapa=ETAPA_ENCAMINHAMENTO,
            cliente_telefone=telefone, phone_id_unidade=phone,
        ) from exc
    envio = {
        "enviou": True, "resposta_ja_existia": False, "id_hash_msg_bot": wamid,
        "mensagem_bot": texto, "tipo_mensagem": "interactive",
        "interativo": {"type": "carousel", "body": {"text": texto},
                       "action": {"cards": [card.to_dict(i) for i, card in enumerate(cartoes)]}},
        "id_etapa_resultante": ETAPA_ENCAMINHAMENTO,
        "encaminhado_sofas": contexto["central"]["telefone_sofas"],
        "encaminhado_moveis": contexto["central"]["telefone_moveis"],
    }
    if not conclusao:
        envio["tipo_tratamento"] = evento
    return envio
