from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot
from core.integrations.whatsapp.exceptions import ErroEnvioMeta

def enviar_solicitacao(bsuid, phone_id, texto, etapa):
    try:
        resposta = conta_wa(phone_id).request_contact_info(to=bsuid, text=texto)
        wamid = extrair_id_hash_msg_bot(resposta)
    except Exception as exc:
        raise ErroEnvioMeta("Falha ao solicitar contato", id_etapa=etapa,
                            cliente_telefone=None, phone_id_unidade=phone_id) from exc
    return {"enviou": True, "resposta_ja_existia": False, "id_hash_msg_bot": wamid,
            "id_etapa_resultante": etapa, "tipo_mensagem": "interactive",
            "mensagem_bot": texto, "interativo": {"type": "request_contact_info",
                "body": {"text": texto}, "action": {"name": "request_contact_info"}},
            "canal": "meta_whatsapp", "atualizar_conversa": True, "atualizar_last_from_bot": True,
            "tipo_destinatario": "bsuid", "valor_destinatario": bsuid}
