"""Um contato para o produto escolhido ou o carrossel para os dois setores."""

import os
import re
from urllib.parse import quote, urlsplit

from pywa.types import ImageCarouselCard, URLButton

from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO
from core.integrations.whatsapp.messages.encaminhamento_pos_venda import (
    MENSAGEM_ENCAMINHAMENTO, MENSAGEM_POR_SETOR, ROTULO_ESTOFADOS, ROTULO_MOVEIS,
    montar_resumo_encaminhamento,
)
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot
from core.validacoes.encaminhamento_pos_venda import setores_encaminhamento
from .texto_pos_venda import enviar_texto_pos_venda


def _botao_contato(contexto, setor):
    numero = contexto["central"].get(f"telefone_{setor}")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", str(numero or "")):
        raise ValueError("Telefone de pós-venda inválido.")
    resumo = montar_resumo_encaminhamento(
        contexto.get("cadastro") or {}, contexto.get("produto"), contexto.get("assunto"),
    )
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
    return [
        ImageCarouselCard(
            image=f"{base}/{arquivo}.png", body=rotulo,
            buttons=_botao_contato(contexto, setor),
        )
        for arquivo, rotulo, setor in (
            ("estofados", ROTULO_ESTOFADOS, "sofas"),
            ("moveis", ROTULO_MOVEIS, "moveis"),
        )
    ]


def enviar_encaminhamento(contexto, evento):
    mensagem = contexto["mensagem_cliente_atual"]
    phone = mensagem["id_phone_unidade"]
    telefone = mensagem["cliente_telefone"]
    setores = setores_encaminhamento(contexto.get("produto"))
    if len(setores) == 1:
        setor = setores[0]
        envio = enviar_texto_pos_venda(
            telefone, phone, MENSAGEM_POR_SETOR[setor], ETAPA_ENCAMINHAMENTO,
            botoes=_botao_contato(contexto, setor),
        )
        envio["tipo_tratamento"] = evento
        envio[f"encaminhado_{setor}"] = contexto["central"][f"telefone_{setor}"]
        return envio
    cartoes = montar_cartoes(contexto)
    try:
        resposta = conta_wa(phone).send_carousel(to=telefone, body=MENSAGEM_ENCAMINHAMENTO, cards=cartoes)
        wamid = extrair_id_hash_msg_bot(resposta)
    except Exception as exc:
        raise ErroEnvioMeta(
            "Falha ao enviar contatos do pós-venda", id_etapa=ETAPA_ENCAMINHAMENTO,
            cliente_telefone=telefone, phone_id_unidade=phone,
        ) from exc
    return {
        "enviou": True, "resposta_ja_existia": False, "id_hash_msg_bot": wamid,
        "mensagem_bot": MENSAGEM_ENCAMINHAMENTO, "tipo_mensagem": "interactive",
        "interativo": {"type": "carousel", "body": {"text": MENSAGEM_ENCAMINHAMENTO},
                       "action": {"cards": [card.to_dict(i) for i, card in enumerate(cartoes)]}},
        "id_etapa_resultante": ETAPA_ENCAMINHAMENTO, "tipo_tratamento": evento,
        "encaminhado_sofas": contexto["central"]["telefone_sofas"],
        "encaminhado_moveis": contexto["central"]["telefone_moveis"],
    }
