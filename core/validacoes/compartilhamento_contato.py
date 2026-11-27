import re

def telefone_compartilhado(mensagem, bsuid_esperado, wamids_pendentes):
    if not isinstance(mensagem, dict) or not bsuid_esperado or mensagem.get("from_user_id") != bsuid_esperado:
        return None
    if mensagem.get("type") != "contacts":
        return None
    contexto = mensagem.get("context") or {}
    if not isinstance(contexto, dict):
        return None
    resposta_a = contexto.get("id")
    if resposta_a and resposta_a not in wamids_pendentes:
        return None
    cartoes = mensagem.get("contacts") or []
    if not isinstance(cartoes, list) or len(cartoes) != 1 or not isinstance(cartoes[0], dict):
        return None
    if cartoes[0].get("origin") != "contact_request":
        return None
    telefones = cartoes[0].get("phones") or []
    if not isinstance(telefones, list) or len(telefones) != 1 or not isinstance(telefones[0], dict):
        return None
    wa_id = telefones[0].get("wa_id")
    return wa_id if isinstance(wa_id, str) and re.fullmatch(r"[1-9][0-9]{0,14}", wa_id) else None
