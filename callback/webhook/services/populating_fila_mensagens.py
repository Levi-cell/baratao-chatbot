from core.repositories.atendimento.solicitacao_contato import pendencia_ativa
from core.repositories.atendimento.identidade_cliente import buscar_alias, serializar_chave, cliente_telefone
from core.validacoes.compartilhamento_contato import telefone_compartilhado
from core.integrations.whatsapp.identidade_cliente import extrair_identidade
from core.identidade_atendimento import IdentidadeDivergente, resolver_cliente, rotacionar_bsuid
from core.repositories.atendimento.conciliacao_cliente import telefone_em_conferencia
from core.repositories.atendimento.identidade_cliente import buscar_central, dados_telefone, impedimento
import logging
from datetime import datetime, timezone

from core.logging_config import short_value
from core.repositories.atendimento.entrada_fila import entrada_ja_registrada, inserir_entrada_fila
from core.repositories.seguranca.turno_cliente import (
    avaliar_turno_cliente_para_fila,
)


logger = logging.getLogger("webhook.fila")


def inserir_dados_na_tabela_fila(dados, cursor):
    if not dados or dados.get("erro"):
        logger.warning("fila_insert_ignorado | motivo=dados_invalidos acao=nao_inserir")
        return {
            "status": "ignored",
            "reason": "dados_invalidos",
        }

    linha = buscar_central(dados["id_phone_unidade"], dados.get("conta_origem"), cursor,
                          incluir_suspensa=dados["tipo_mensagem"] == "system")
    if not linha:
        return {"status": "ignored", "reason": "central_incompativel"}
    central = dados["id_central"] = linha[0]
    if dados["tipo_mensagem"] == "system":
        sistema = dados["sistema"]
        if sistema.get("type") in {"user_changed_user_id", "user_changed_number"}:
            rotacionar_bsuid(central, sistema, dados["id_hash_msg"], cursor)
        return {"status": "ignored", "reason": "evento_tecnico"}
    if entrada_ja_registrada(dados["id_hash_msg"], cursor):
        return {"status": "ignored", "reason": "conflito_unico"}
    uid = dados.get("user_id_origem")
    if uid:
        serializar_chave(f"bs:{central}:{uid}", cursor)
    contato, motivo = _prova_solicitada(dados, uid, cursor)
    telefone_da_conversa = telefone_em_conferencia(central, uid, cursor) if uid else None
    telefone_envelope = dados.get("cliente_telefone")
    if (contato or telefone_da_conversa) and not dados.get("assinatura_verificada"):
        return {"status": "ignored", "reason": "contato_exige_assinatura"}
    # Um cartão oficial e as respostas posteriores podem trazer também o WA ID.
    # A conversa continua pelo BSUID até ser possível decidir sobre o cadastro.
    if telefone_da_conversa and telefone_envelope and telefone_envelope != telefone_da_conversa:
        raise IdentidadeDivergente("O telefone mudou durante a conferência do cadastro.")
    segue_por_bsuid = bool(contato or telefone_da_conversa)
    origem = {**dados, "cliente_telefone": None} if segue_por_bsuid else dados
    cliente = dados["id_cliente"] = resolver_cliente(origem, central, cursor)
    ids = [v for v in (dados_telefone(cliente, cursor), uid, contato, telefone_da_conversa) if v]
    if impedimento(central, cliente, ids, cursor):
        return {"status": "ignored", "reason": "cliente_impedido"}

    if contato:
        serializar_chave(f"wa:{contato}", cursor)
        canonica = cliente_telefone(contato, cursor)
        if canonica and canonica != cliente and impedimento(central, canonica, ids, cursor):
            return {"status": "ignored", "reason": "cliente_impedido"}
        dados["interativo"]["_telefone_verificado"] = contato
        if canonica and canonica != cliente:
            if motivo != "cadastro":
                return {"status": "ignored", "reason": "contato_exige_conciliacao"}
            dados["interativo"]["_telefone_em_outro_cadastro"] = True
            dados["cliente_telefone"] = None
    elif segue_por_bsuid:
        # Evita publicar no cache do telefone ou bloquear o outro dono ao encerrar.
        dados["cliente_telefone"] = None

    turno = avaliar_turno_cliente_para_fila(
        cursor=cursor,
        id_cliente=cliente,
        id_phone_unidade=dados["id_phone_unidade"],
        received_data_hora=dados["received_data_hora"],
        usar_lock=True,
    )

    if not turno["pode_enfileirar"]:
        if turno["motivo"] == "fila_aberta_sem_resposta_bot":
            logger.info(
                "mensagem_ignorada | motivo=fila_aberta_pending_processing acao=nao_enfileirar cliente=%s phone_number_id=%s detalhe=ja_existe_mensagem_pending_ou_processing",
                short_value(dados["cliente_telefone"]),
                short_value(dados["id_phone_unidade"]),
            )
        elif turno["motivo"] == "mensagem_reentregue_fora_de_ordem":
            logger.info(
                "mensagem_ignorada | motivo=mensagem_reentregue_fora_de_ordem acao=nao_enfileirar cliente=%s phone_number_id=%s received_data_hora=%s",
                short_value(dados["cliente_telefone"]),
                short_value(dados["id_phone_unidade"]),
                dados["received_data_hora"],
            )
        else:
            logger.info(
                "fila_insert_ignorado | motivo=%s acao=nao_inserir_turno cliente=%s phone_number_id=%s",
                turno["motivo"],
                short_value(dados["cliente_telefone"]),
                short_value(dados["id_phone_unidade"]),
            )

        return {
            "status": "ignored",
            "reason": turno["motivo"],
        }

    id_mensagem = inserir_entrada_fila(dados, cursor)

    if id_mensagem is None:
        logger.info(
            "fila_insert_ignorado | motivo=conflito_unico acao=nao_inserir id_msg=%s cliente=%s phone_number_id=%s",
            short_value(dados["id_hash_msg"]),
            short_value(dados["cliente_telefone"]),
            short_value(dados["id_phone_unidade"]),
        )
        return {
            "status": "ignored",
            "reason": "conflito_unico",
        }

    return {
        "status": "inserted",
        "reason": None,
        "id_mensagem": id_mensagem,
    }


def _prova_solicitada(dados, uid, cursor):
    if not uid or dados["tipo_mensagem"] != "contacts":
        return None, None
    central = dados["id_central"]
    alias = buscar_alias(central, uid, cursor)
    if not alias or not alias[1]:
        return None, None
    pendencia = pendencia_ativa(central, alias[0], uid, cursor)
    if not pendencia:
        return None, None
    prova = telefone_compartilhado(dados["interativo"] or {}, uid, pendencia[0])
    if prova and dados.get("cliente_telefone") not in (None, prova):
        raise IdentidadeDivergente("O telefone do envelope diverge do cartão solicitado.")
    return prova, pendencia[1]


def extrair_dados_whatsapp(data):
    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        if not value.get("messages"):
            return {
                "erro": "evento_sem_mensagem",
                "raw": data,
            }

        metadata = value.get("metadata", {})
        unidade_telefone = metadata.get("display_phone_number")
        id_phone_unidade = metadata.get("phone_number_id")

        message = value.get("messages", [{}])[0]
        identidade = extrair_identidade(value, message)
        cliente_telefone = identidade.wa_id
        message_id = message.get("id")
        timestamp = message.get("timestamp")
        tipo = message.get("type")
        conteudo_texto = extrair_conteudo_texto_mensagem(message, tipo)

        # O timestamp da Meta representa um instante Unix em UTC. Mantemos o
        # fuso explícito para o PostgreSQL não reinterpretar um datetime
        # ingênuo conforme o timezone configurado na role da aplicação.
        received_data_hora = datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc,
        )

        if not all([
            cliente_telefone or identidade.user_id,
            message_id,
            id_phone_unidade,
            unidade_telefone,
            tipo,
        ]):
            return {
                "erro": "dados_incompletos",
                "raw": data,
            }

        return {
            "user_id_origem": identidade.user_id, "username_origem": identidade.username,
            "conta_origem": entry.get("id"), "sistema": message.get("system", {}),
            "interativo": ({k: message[k] for k in ("type","from_user_id","context","contacts") if k in message}
                           if tipo == "contacts" else message.get("interactive")),
            "status": "pending",
            "retry_count": 0,
            "next_attempt_at": received_data_hora,
            "processing_started_at": None,
            "received_data_hora": received_data_hora,
            "cliente_telefone": cliente_telefone,
            "conteudo_texto": conteudo_texto,
            "tipo_mensagem": tipo,
            "id_hash_msg": message_id,
            "id_phone_unidade": id_phone_unidade,
            "unidade_telefone": unidade_telefone,
        }

    except (IndexError, KeyError, TypeError, ValueError) as erro:
        return {
            "erro": "exception",
            "detalhe": str(erro),
            "raw": data,
        }


def extrair_conteudo_texto_mensagem(message, tipo):
    if tipo == "text":
        return message.get("text", {}).get("body")

    if tipo in {"interactive", "interactive_button"}:
        # A Meta envia interactive; aceitamos também o alias interactive_button.
        # O worker recebe apenas a resposta selecionada, nunca o texto citado
        # da mensagem anterior (que pode mencionar os três turnos).
        interactive = message.get("interactive") or message.get("interactive_button", {})
        return extrair_conteudo_interactive(interactive)

    if tipo == "button":
        return extrair_conteudo_button(message.get("button", {}))

    return None


def extrair_conteudo_interactive(interactive):
    if not isinstance(interactive, dict):
        return None
    tipo_interactive = interactive.get("type")

    if tipo_interactive == "button_reply":
        button_reply = interactive.get("button_reply", {})
        return _extrair_texto_opcao(button_reply, "title", "id")

    if tipo_interactive == "list_reply":
        list_reply = interactive.get("list_reply", {})
        return _extrair_texto_opcao(list_reply, "title", "id")

    return None


def extrair_conteudo_button(button):
    return _extrair_texto_opcao(button, "text", "payload")


def _extrair_texto_opcao(opcao, campo_texto, campo_identificador):
    """Prioriza o rótulo; sem ele, aceita o callback textual já usado pelo bot."""
    if not isinstance(opcao, dict):
        return None
    for campo in (campo_texto, campo_identificador):
        valor = opcao.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


def preparar_dados_fila(data):
    dados = extrair_dados_whatsapp(data)

    if dados.get("erro"):
        logger.warning(
            "fila_extracao_falhou | motivo=%s acao=nao_enfileirar",
            dados.get("erro"),
        )
        return {
            "status": "ignored",
            "reason": dados.get("erro"),
            "dados": None,
        }

    logger.info(
        "fila_recebida | acao=preparar_insert id_msg=%s cliente=%s phone_number_id=%s tipo=%s",
        short_value(dados["id_hash_msg"]),
        short_value(dados["cliente_telefone"]),
        short_value(dados["id_phone_unidade"]),
        dados["tipo_mensagem"],
    )
    return {
        "status": "ready",
        "reason": None,
        "dados": dados,
    }


def povoando_fila(dados, cursor):
    return inserir_dados_na_tabela_fila(dados, cursor)
