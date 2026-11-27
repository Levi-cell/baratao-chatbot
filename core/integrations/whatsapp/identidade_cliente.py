from dataclasses import dataclass
import re

BSUID = re.compile(r"[A-Z]{2}\.[A-Za-z0-9]{1,128}")
TELEFONE = re.compile(r"[1-9][0-9]{0,14}")


def _validar_endereco(valor, padrao):
    if valor is not None and (not isinstance(valor, str) or not padrao.fullmatch(valor)):
        raise ValueError("Identificador de origem inválido")


@dataclass(frozen=True)
class IdentidadeEntrada:
    wa_id: str | None
    user_id: str | None
    username: str | None


def _objetos(valor):
    if isinstance(valor, list):
        yield from (item for item in valor if isinstance(item, dict))


def extrair_identidade(value, mensagem):
    wa, uid = mensagem.get("from"), mensagem.get("from_user_id")
    sistema = mensagem.get("system") or {}
    if mensagem.get("type") == "system":
        if not isinstance(sistema, dict):
            raise ValueError("Evento de identidade inválido")
        uid = uid or sistema.get("user_id") or sistema.get("previous_user_id")
        _validar_endereco(sistema.get("previous_user_id"), BSUID)
        _validar_endereco(sistema.get("user_id"), BSUID)
    _validar_endereco(wa, TELEFONE)
    _validar_endereco(uid, BSUID)
    if not (wa or uid):
        raise ValueError("Mensagem sem identificador de remetente")
    candidatos = []
    for contato in _objetos(value.get("contacts")):
        cw, cu = contato.get("wa_id"), contato.get("user_id")
        if not ((wa and wa == cw) or (uid and uid == cu)):
            continue
        if (wa and cw and wa != cw) or (uid and cu and uid != cu):
            raise ValueError("Identidades divergentes no envelope")
        candidatos.append(contato)
    if len(candidatos) > 1:
        raise ValueError("Contato ambíguo")
    contato = candidatos[0] if candidatos else {}
    wa, uid = wa or contato.get("wa_id"), uid or contato.get("user_id")
    _validar_endereco(wa, TELEFONE)
    _validar_endereco(uid, BSUID)
    perfil = contato.get("profile")
    username = perfil.get("username") if isinstance(perfil, dict) else None
    return IdentidadeEntrada(wa, uid, username if isinstance(username, str) else None)


def eventos_individuais(data):
    """Preserva conta e metadados de cada change e isola o contato do remetente."""
    if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
        return
    for entry in _objetos(data.get("entry")):
        for change in _objetos(entry.get("changes")):
            if change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            for chave in ("messages", "statuses"):
                for item in _objetos(value.get(chave)):
                    valor = {k: v for k, v in value.items() if k not in {"messages", "statuses"}}
                    valor[chave] = [item]
                    yield {"object": data["object"], "entry": [
                        {**entry, "changes": [{**change, "value": valor}]}
                    ]}


def identificador_entrada(value):
    mensagens=value.get("messages") or []
    if not mensagens:
        return None
    dados=extrair_identidade(value,mensagens[0])
    return dados.wa_id or dados.user_id
