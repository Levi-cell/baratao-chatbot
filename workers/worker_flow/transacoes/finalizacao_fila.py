import logging

from core.cache.runtime.cache_conversas_bloqueadas import (
    registrar_bloqueio_conversa_cache,
)
from core.cache.runtime.cache_cliente import remover_cliente_cache, salvar_cliente_cache
from core.logging_config import short_value
from core.repositories.atendimento.fila import marcar_mensagem_como_enviada
from workers.worker_flow.transacoes.encerramento_atendimento import (
    aplicar_encerramento_se_necessario,
)


logger = logging.getLogger("worker.support")


def finalizar_mensagem_processada(
    mensagem,
    contexto_banco,
    lock_version,
    cursor,
    contexto_final=None,
):
    contexto_conversa = contexto_banco["conversa"]
    id_conversa = contexto_conversa["id_conversa"]
    contexto_final = contexto_final or {}

    resultado_encerramento = aplicar_encerramento_se_necessario(
        id_conversa,
        contexto_final.get("intencao_encerramento"),
        cursor,
    )

    marcar_mensagem_como_enviada(mensagem["id_mensagem"], cursor)

    conciliacao = (contexto_final.get("efeitos_transicao") or {}).get("cache_conciliacao")
    if conciliacao:
        resultado_encerramento["cache_conciliacao"] = conciliacao
    return resultado_encerramento


def registrar_cache_bloqueio_apos_commit(
    mensagem,
    resultado_encerramento,
):
    """Publica o vínculo reconciliado ou o bloqueio somente depois do commit da fila."""
    if conciliacao := resultado_encerramento.get("cache_conciliacao"):
        for telefone in conciliacao["telefones_antigos"]:
            remover_cliente_cache(telefone)
        for central, uid in conciliacao["aliases_antigos"]:
            remover_cliente_cache(uid, id_central=central, tipo="bsuid")
        salvar_cliente_cache(conciliacao["telefone"], conciliacao["cliente"])
        if conciliacao["uid"]:
            salvar_cliente_cache(conciliacao["uid"], conciliacao["cliente"],
                                 id_central=conciliacao["central"], tipo="bsuid")
    if not resultado_encerramento.get("atendimento_encerrado"):
        return False

    bloqueio_dias = int(
        resultado_encerramento.get("bloqueio_dias") or 0
    )

    if bloqueio_dias <= 0:
        return False

    registrado = False
    for chave in dict.fromkeys((mensagem.get("cliente_telefone"),mensagem.get("user_id_origem"))):
        if chave:
            gravado = registrar_bloqueio_conversa_cache(chave,mensagem["id_phone_unidade"],
                                                         resultado_encerramento["finalizou_em"],bloqueio_dias)
            registrado = registrado or gravado

    logger.info(
        "cache_bloqueio_pos_commit | acao=registrar cliente=%s "
        "phone_number_id=%s bloqueio_dias=%s registrado=%s",
        short_value(mensagem["cliente_telefone"]),
        short_value(mensagem["id_phone_unidade"]),
        bloqueio_dias,
        registrado,
    )
    return registrado
