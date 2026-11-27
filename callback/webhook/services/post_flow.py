from core.integrations.whatsapp.identidade_cliente import eventos_individuais, extrair_identidade
from core.identidade_atendimento import IdentidadeDivergente
import json
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.http import JsonResponse

from core.cache.runtime.cache_conversas_bloqueadas import (
    ValidacaoBloqueioConversaIndisponivel,
    conversa_esta_bloqueada_cache,
)
from core.cache.runtime.cache_webhook_erro_inesperado import (
    MAX_RESPOSTAS_503_POR_WAMID,
    registrar_tentativa_erro_inesperado,
)
from core.cache.cache_unidade import (
    ValidacaoUnidadeIndisponivel,
    unidade_esta_ativa,
)
from core.database.connection_aws import get_conn
from core.logging_config import referencia_wamid, short_value
from .bloqueio_meta_guard import (
    verificar_protecao_remetente,
)
from .flood_guard import responder_se_flood
from .meta_signature import validar_assinatura_meta
from .populating_fila_mensagens import preparar_dados_fila, povoando_fila


logger = logging.getLogger("webhook.post_flow")
fila_logger = logging.getLogger("webhook.fila")

TIPO_EVENTO_MENSAGEM = "messages"
TIPO_EVENTO_STATUS = "statuses"
TIPO_EVENTO_DESCONHECIDO = "unknown"


def responder_post_webhook(request):
    if resposta := _validar_content_type(request):
        return resposta

    if resposta := _validar_tamanho_body(request):
        return resposta

    if not validar_assinatura_meta(request):
        logger.warning(
            "mensagem_ignorada | motivo=assinatura_meta_invalida acao=retornar_403 path=%s",
            request.path,
        )
        return JsonResponse({"status": "forbidden"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))

    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "mensagem_ignorada | motivo=json_invalido acao=nao_enfileirar erro=%s",
            exc,
        )
        return JsonResponse({
            "status": "ignored",
            "reason": "invalid_json",
        })

    resposta = None
    for evento in eventos_individuais(data):
        resposta = _processar_evento(request, evento)
        if resposta.status_code >= 400:
            return resposta
    return resposta if resposta is not None else JsonResponse({"status": "ok"})


def _processar_evento(request,data):
    phone_number_id = None
    cliente_telefone = None

    try:
        tipo_evento = _classificar_evento_meta(data)

        if tipo_evento == TIPO_EVENTO_STATUS:
            return _registrar_status_identidade(data)

        if tipo_evento != TIPO_EVENTO_MENSAGEM:
            logger.info(
                "evento_meta_ignorado | motivo=evento_sem_messages_ou_statuses acao=retornar_200",
            )
            return JsonResponse({"status": "ok"})

        phone_number_id = _extrair_phone_number_id(data)
        try:
            valor = _extrair_value(data)
            identidade = extrair_identidade(valor, valor["messages"][0])
            cliente_telefone = identidade.wa_id or identidade.user_id
        except ValueError:
            logger.info("mensagem_ignorada | motivo=identidade_ausente_ou_invalida")
            return JsonResponse({"status": "ignored", "reason": "identidade_ausente_ou_invalida"})
        if _extrair_value(data)["messages"][0].get("type") == "system":
            resultado = preparar_dados_fila(data)
            if resultado["status"]=="ready":
                gravado = _executar_transacao_fila(resultado["dados"])
                if gravado["status"] == "error":
                    return JsonResponse({"status":"unavailable"},status=503)
            return JsonResponse({"status":"ok"})

        resposta_bloqueio, chave_flood = verificar_protecao_remetente(
            cliente_telefone,
            phone_number_id,
            identificadores=[v for v in (identidade.wa_id, identidade.user_id) if v],
            conta_origem=data["entry"][0].get("id"),
        )
        if resposta_bloqueio is not None:
            return resposta_bloqueio

        if resposta_flood := responder_se_flood(data, chave_flood=chave_flood):
            return resposta_flood

        if not unidade_esta_ativa(phone_number_id):
            logger.info(
                "mensagem_ignorada | motivo=unidade_inativa acao=nao_enfileirar cliente=%s phone_number_id=%s",
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )
            return JsonResponse({"status": "ignored"})

        if cliente_telefone and conversa_esta_bloqueada_cache(
            cliente_telefone,
            phone_number_id,
        ):
            logger.info(
                "mensagem_ignorada | motivo=conversa_bloqueada acao=nao_enfileirar cliente=%s phone_number_id=%s",
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )
            return JsonResponse({
                "status": "ignored",
                "reason": "blocked_conversation",
            })

        preparacao_fila = preparar_dados_fila(data)

        if preparacao_fila["status"] == "ready":
            preparacao_fila["dados"]["assinatura_verificada"] = settings.META_WEBHOOK_SIGNATURE_REQUIRED
            resultado_fila = _executar_transacao_fila(preparacao_fila["dados"])

        else:
            resultado_fila = {
                "status": "ignored",
                "reason": preparacao_fila["reason"],
            }

        if resultado_fila["status"] == "ignored":
            logger.info(
                "mensagem_ignorada | motivo=%s acao=nao_enfileirar cliente=%s phone_number_id=%s",
                resultado_fila["reason"],
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )

        elif resultado_fila["status"] != "inserted":
            logger.error(
                "request_indisponivel | motivo=%s acao=retornar_503_para_reentrega cliente=%s phone_number_id=%s",
                resultado_fila["reason"],
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )
            return JsonResponse({
                "status": "unavailable",
                "reason": resultado_fila["reason"],
            }, status=503)

    except ValidacaoUnidadeIndisponivel as exc:
        logger.error(
            "request_indisponivel | motivo=validacao_unidade_indisponivel acao=retornar_503_para_reentrega cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(phone_number_id),
            exc,
        )
        return JsonResponse({
            "status": "unavailable",
            "reason": "unit_validation_unavailable",
        }, status=503)

    except ValidacaoBloqueioConversaIndisponivel as exc:
        logger.error(
            "request_indisponivel | motivo=validacao_bloqueio_conversa_indisponivel acao=retornar_503_para_reentrega cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(phone_number_id),
            exc,
        )
        return JsonResponse({
            "status": "unavailable",
            "reason": "conversation_block_validation_unavailable",
        }, status=503)

    except Exception as exc:
        id_hash_msg = _extrair_id_hash_msg_seguro(data)
        tentativa = registrar_tentativa_erro_inesperado(
            id_hash_msg,
        )

        if tentativa["retornar_503"]:
            logger.exception(
                "request_erro | "
                "acao=retornar_503_para_reentrega "
                "metodo=%s path=%s id_hash_msg=%s "
                "tentativa=%s limite_503=%s",
                request.method,
                request.path,
                short_value(id_hash_msg),
                tentativa["tentativa"],
                MAX_RESPOSTAS_503_POR_WAMID,
            )
            return JsonResponse(
                {
                    "status": "unavailable",
                    "reason": "unexpected_error_retry",
                    "attempt": tentativa["tentativa"],
                },
                status=503,
            )

        logger.error(
            "request_erro | "
            "acao=retornar_200_e_ignorar "
            "metodo=%s path=%s id_hash_msg=%s "
            "tentativa=%s motivo=%s",
            request.method,
            request.path,
            short_value(id_hash_msg),
            tentativa["tentativa"],
            tentativa["motivo"],
            exc_info=(
                type(exc),
                exc,
                exc.__traceback__,
            ),
        )
        reason = (
            "unexpected_error_retry_exhausted"
            if tentativa["motivo"]
            == "limite_503_esgotado"
            else "unexpected_error_retry_unavailable"
        )
        return JsonResponse({
            "status": "ignored",
            "reason": reason,
        })

    return JsonResponse({"status": "ok"})


def _classificar_evento_meta(data):
    value = _extrair_value(data)
    possui_mensagens = bool(value.get("messages"))
    possui_statuses = bool(value.get("statuses"))

    if possui_mensagens and not possui_statuses:
        return TIPO_EVENTO_MENSAGEM

    if possui_statuses and not possui_mensagens:
        return TIPO_EVENTO_STATUS

    return TIPO_EVENTO_DESCONHECIDO


def _registrar_status_identidade(data):
    from core.repositories.atendimento.identidade_cliente import atualizar_username_por_recibo, buscar_central
    valor = _extrair_value(data)
    status = valor["statuses"][0]
    tipo = status.get("status")
    if tipo not in {"delivered", "read", "failed"} or not status.get("id"):
        return JsonResponse({"status":"ok"})
    if tipo == "failed":
        _registrar_falha_entrega(data, status)
        return JsonResponse({"status": "ok"})

    logger.debug("recibo_meta | status=%s ref_envio=%s", tipo, referencia_wamid(status["id"]))
    try:
        identidade = extrair_identidade(valor, {"from": status.get("recipient_id"),
                                                "from_user_id": status.get("recipient_user_id")})
        observado_em = datetime.fromtimestamp(int(status["timestamp"]), timezone.utc)
    except (KeyError, ValueError, TypeError, OverflowError, OSError):
        return JsonResponse({"status": "ignored"})
    if not identidade.username:
        return JsonResponse({"status": "ok"})
    with get_conn(application_name="webhook_status") as conn, conn.cursor() as cursor:
        central = buscar_central(_extrair_phone_number_id(data), data["entry"][0].get("id"), cursor)
        if central:
            atualizar_username_por_recibo(central[0], status["id"], identidade.user_id,
                                          identidade.wa_id, identidade.username, observado_em, cursor)
    return JsonResponse({"status": "ok"})


def _registrar_falha_entrega(data, status):
    from core.repositories.atendimento.identidade_cliente import buscar_central, falha_da_rota_atual
    from core.repositories.atendimento.fallback_contato import reservar_reconfirmacao

    central = tentativa = None
    recuperacao = "verificacao_inconclusiva"
    try:
        with get_conn(application_name="webhook_status") as conn, conn.cursor() as cursor:
            central = buscar_central(_extrair_phone_number_id(data), data["entry"][0].get("id"), cursor)
            tentativa = falha_da_rota_atual(central[0], status["id"], cursor) if central else None
            resultado = "nao_aplicavel"
            # Só a suspensão confirmada da rota autoriza a reconfirmação.
            if tentativa and tentativa[3]:
                nova = reservar_reconfirmacao(tentativa[0], tentativa[1], status["id"], cursor)
                resultado = "reservada" if nova else "ja_reservada"
        recuperacao = resultado  # O contexto da conexão já confirmou a transação.
    finally:
        erros = status.get("errors")
        codigos = []
        if isinstance(erros, list):
            for erro in erros:
                codigo = str(erro.get("code", "")) if isinstance(erro, dict) else ""
                if codigo.isascii() and codigo.isdecimal():
                    codigos.append(codigo)
        logger.warning(
            "entrega_meta_falhou | ref_envio=%s codigos_meta=%s id_central=%s "
            "id_mensagem=%s id_conversa=%s recuperacao=%s",
            referencia_wamid(status["id"]), ",".join(codigos) or "-",
            central[0] if central else "-", tentativa[1] if tentativa else "-",
            tentativa[0] if tentativa else "-", recuperacao,
        )


def _executar_transacao_fila(dados):
    conn_webhook = None

    try:
        conn_webhook = get_conn(application_name="webhook_chatbot")
        cursor_webhook = conn_webhook.cursor()
        resultado = povoando_fila(dados, cursor_webhook)
        conn_webhook.commit()

        if resultado["status"] == "inserted":
            fila_logger.info(
                "fila_insert_ok | status=enfileirado id_mensagem=%s id_central=%s tipo=%s",
                resultado["id_mensagem"], dados["id_central"],
                dados["tipo_mensagem"],
            )

        return resultado

    except IdentidadeDivergente:
        conn_webhook.rollback()
        fila_logger.warning("mensagem_ignorada | motivo=identidade_divergente")
        return {"status": "ignored", "reason": "identidade_divergente"}
    except Exception:
        if conn_webhook:
            conn_webhook.rollback()

        fila_logger.exception(
            "fila_insert_erro | acao=rollback id_msg=%s",
            short_value(dados.get("id_hash_msg") if dados else None),
        )
        return {
            "status": "error",
            "reason": "insert_exception",
        }

    finally:
        if conn_webhook:
            conn_webhook.close()


def _validar_content_type(request):
    content_type = (request.content_type or "").lower()

    if content_type.startswith("application/json"):
        return None

    logger.warning(
        "mensagem_ignorada | motivo=content_type_invalido acao=retornar_415 content_type=%s",
        content_type or None,
    )
    return JsonResponse({"status": "unsupported_media_type"}, status=415)


def _validar_tamanho_body(request):
    limite_bytes = settings.WEBHOOK_MAX_BODY_BYTES
    tamanho_header = request.headers.get("Content-Length")

    if tamanho_header:
        try:
            tamanho_bytes = int(tamanho_header)

        except ValueError:
            logger.warning(
                "mensagem_ignorada | motivo=content_length_invalido acao=retornar_400 content_length=%s",
                tamanho_header,
            )
            return JsonResponse({"status": "bad_request"}, status=400)

        if tamanho_bytes > limite_bytes:
            logger.warning(
                "mensagem_ignorada | motivo=body_muito_grande acao=retornar_413 tamanho_bytes=%s limite_bytes=%s origem=content_length",
                tamanho_bytes,
                limite_bytes,
            )
            return JsonResponse({"status": "payload_too_large"}, status=413)

    tamanho_real = len(request.body)

    if tamanho_real > limite_bytes:
        logger.warning(
            "mensagem_ignorada | motivo=body_muito_grande acao=retornar_413 tamanho_bytes=%s limite_bytes=%s origem=request_body",
            tamanho_real,
            limite_bytes,
        )
        return JsonResponse({"status": "payload_too_large"}, status=413)

    return None


def _extrair_value(data):
    return (
        data.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
    )


def _extrair_phone_number_id(data):
    metadata = _extrair_value(data).get("metadata", {})
    return metadata.get("phone_number_id")





def _extrair_id_hash_msg_seguro(data):
    try:
        value = _extrair_value(data)
        messages = value.get("messages")

        if (
            not isinstance(messages, list)
            or not messages
            or not isinstance(messages[0], dict)
        ):
            return None

        id_hash_msg = messages[0].get("id")

        if id_hash_msg is None:
            return None

        id_hash_msg = str(id_hash_msg).strip()
        return id_hash_msg or None

    except Exception:
        return None
