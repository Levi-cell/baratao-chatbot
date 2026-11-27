"""Encaminhamento por rede das filiais das notas desta conversa."""

import os
import re
from urllib.parse import quote, urlsplit

from pywa.types import ImageCarouselCard, URLButton

from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO, EVENTO_SITUACAO_INFORMADA
from core.integrations.whatsapp.messages.encaminhamento_pos_venda import (
    MENSAGEM_DUAS_REDES, MENSAGEM_SEM_NOTA, MENSAGEM_NOTA_PERDIDA, MENSAGEM_POR_GRUPO,
    ROTULOS_POS_VENDA, mensagem_de_contato, montar_resumo_encaminhamento,
)
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot
from core.validacoes.encaminhamento_pos_venda import grupos_encaminhamento
from .texto_pos_venda import enviar_texto_pos_venda


def _resumo_do_atendimento(contexto):
    return montar_resumo_encaminhamento(
        contexto.get("cadastro") or {}, contexto.get("produto"), contexto.get("assunto"),
        pedidos_com_filial=contexto.get("pedidos_com_filial", ()), perdeu_nota=contexto.get("perdeu_nota"),
        detalhes=contexto.get("detalhes"),
    )


def _botao_contato(central, grupo, resumo):
    numero = central.get(f"telefone_{grupo}")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", str(numero or "")):
        raise ValueError("Telefone de pós-venda inválido.")
    return URLButton(
        title=ROTULOS_POS_VENDA[grupo],
        url=f"https://wa.me/{numero}?text={quote(resumo, safe='')}",
    )


def montar_cartoes(contexto):
    central = contexto["central"]
    base = os.getenv("WHATSAPP_MIDIAS_BASE_URL", "").strip().rstrip("/")
    url = urlsplit(base)
    if url.scheme != "https" or not url.netloc or url.query or url.fragment or url.username:
        raise ValueError("Configure WHATSAPP_MIDIAS_BASE_URL com a URL HTTPS pública das imagens.")
    if central.get("telefone_atacadao") == central.get("telefone_baratao"):
        raise ValueError("A central precisa dos dois contatos distintos de pós-venda.")
    resumo = _resumo_do_atendimento(contexto)
    return [
        ImageCarouselCard(
            image=f"{base}/{arquivo}.png",
            buttons=_botao_contato(central, grupo, resumo),
        )
        for arquivo, grupo in (("estofados", "atacadao"), ("moveis", "baratao"))
    ]


def enviar_encaminhamento(contexto, evento):
    mensagem = contexto["mensagem_cliente_atual"]
    phone = mensagem["id_phone_unidade"]
    telefone = contexto.get("destinatario_envio", mensagem.get("cliente_telefone"))
    grupos = grupos_encaminhamento(contexto)
    conclusao = evento == EVENTO_SITUACAO_INFORMADA
    if len(grupos) == 1:
        grupo = grupos[0]
        texto = MENSAGEM_POR_GRUPO[grupo]
        envio = enviar_texto_pos_venda(
            telefone, phone, mensagem_de_contato(texto, contexto.get("assunto")),
            ETAPA_ENCAMINHAMENTO, botoes=_botao_contato(contexto["central"], grupo, _resumo_do_atendimento(contexto)),
        )
        if not conclusao:
            envio["tipo_tratamento"] = evento
        envio[f"encaminhado_{grupo}"] = contexto["central"][f"telefone_{grupo}"]
        return envio

    if contexto.get("perdeu_nota"):
        texto = MENSAGEM_NOTA_PERDIDA
    elif contexto.get("grupos_das_notas"):
        texto = MENSAGEM_DUAS_REDES
    else:
        texto = MENSAGEM_SEM_NOTA
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
        "encaminhado_atacadao": contexto["central"]["telefone_atacadao"],
        "encaminhado_baratao": contexto["central"]["telefone_baratao"],
    }
    if not conclusao:
        envio["tipo_tratamento"] = evento
    return envio
