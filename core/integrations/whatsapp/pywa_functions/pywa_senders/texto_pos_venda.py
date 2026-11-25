"""Transporte compartilhado das perguntas do pós-venda, sem efeitos no banco."""

from pywa.types import SectionList, URLButton
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot


def enviar_texto_pos_venda(cliente_telefone, phone_id_unidade, texto, etapa, *, botoes=None, rodape=None):
    opcoes = {"buttons": botoes} if botoes else {}
    if rodape:
        opcoes["footer"] = rodape
    try:
        resposta = conta_wa(phone_id_unidade).send_message(
            to=cliente_telefone, text=texto, **opcoes,
        )
        wamid = extrair_id_hash_msg_bot(resposta)
    except Exception as exc:
        raise ErroEnvioMeta(
            "Falha ao enviar mensagem de pós-venda",
            id_etapa=etapa, cliente_telefone=cliente_telefone,
            phone_id_unidade=phone_id_unidade,
        ) from exc
    resultado = {
        "enviou": True, "resposta_ja_existia": False,
        "mensagem_bot": texto, "id_hash_msg_bot": wamid,
        "id_etapa_resultante": etapa, "tipo_mensagem": "interactive" if botoes else "text",
        "canal": "meta_whatsapp", "atualizar_conversa": True,
        "atualizar_last_from_bot": True,
    }
    if botoes:
        if isinstance(botoes, SectionList):
            tipo, acao = "list", botoes.to_dict()
        elif isinstance(botoes, URLButton):
            tipo, acao = "cta_url", botoes.to_dict()
        else:
            tipo, acao = "button", {"buttons": [botao.to_dict() for botao in botoes]}
        resultado["interativo"] = {
            "type": tipo, "body": {"text": texto}, "action": acao,
        }
        if rodape:
            resultado["interativo"]["footer"] = {"text": rodape}
    return resultado
