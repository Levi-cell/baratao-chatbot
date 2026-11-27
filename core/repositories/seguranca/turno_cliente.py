import logging

from core.logging_config import short_value


logger = logging.getLogger("db.turno_cliente")


def avaliar_turno_cliente_para_fila(
    cursor,
    id_cliente,
    id_phone_unidade,
    received_data_hora=None,
    usar_lock=False,
):
    if not id_cliente or not id_phone_unidade:
        logger.warning(
            "turno_cliente_invalido | motivo=dados_invalidos acao=bloquear_turno cliente=%s phone_number_id=%s",
            short_value(id_cliente),
            short_value(id_phone_unidade),
        )
        return {
            "pode_enfileirar": False,
            "motivo": "dados_invalidos",
        }

    if usar_lock:
        adquirir_lock_turno_cliente(cursor, id_cliente, id_phone_unidade)

    if received_data_hora is not None:
        interacao_posterior = buscar_interacao_posterior_a_mensagem(
            cursor,
            id_cliente,
            id_phone_unidade,
            received_data_hora,
        )

        if interacao_posterior is not None:
            logger.info(
                "turno_cliente_bloqueado | motivo=mensagem_reentregue_fora_de_ordem acao=nao_enfileirar cliente=%s phone_number_id=%s mensagem_em=%s ultima_interacao=%s",
                short_value(id_cliente),
                short_value(id_phone_unidade),
                received_data_hora,
                interacao_posterior,
            )
            return {
                "pode_enfileirar": False,
                "motivo": "mensagem_reentregue_fora_de_ordem",
            }

    turno = avaliar_filas_abertas_turno(
        cursor,
        id_cliente,
        id_phone_unidade,
    )

    if not turno["existe_fila_aberta"]:
        logger.debug(
            "turno_cliente_liberado | motivo=sem_fila_aberta acao=enfileirar cliente=%s phone_number_id=%s",
            short_value(id_cliente),
            short_value(id_phone_unidade),
        )
        return {
            "pode_enfileirar": True,
            "motivo": "sem_fila_aberta",
        }

    if turno["todas_abertas_respondidas"]:
        logger.info(
            "turno_cliente_liberado | motivo=fila_aberta_respondida_bot acao=enfileirar_recuperacao cliente=%s phone_number_id=%s total_abertas=%s",
            short_value(id_cliente),
            short_value(id_phone_unidade),
            turno["total_abertas"],
        )
        return {
            "pode_enfileirar": True,
            "motivo": "fila_aberta_respondida_bot",
        }

    logger.info(
        "turno_cliente_bloqueado | motivo=fila_aberta_sem_resposta_bot acao=nao_enfileirar cliente=%s phone_number_id=%s total_abertas=%s id_mensagem_bloqueadora=%s",
        short_value(id_cliente),
        short_value(id_phone_unidade),
        turno["total_abertas"],
        turno["id_mensagem_bloqueadora"],
    )
    return {
        "pode_enfileirar": False,
        "motivo": "fila_aberta_sem_resposta_bot",
    }


def adquirir_lock_turno_cliente(cursor, id_cliente, id_phone_unidade):
    cursor.execute("""
        SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s));
    """, (str(id_phone_unidade), str(id_cliente)))

    logger.debug(
        "turno_cliente_lock | acao=advisory_xact_lock cliente=%s phone_number_id=%s",
        short_value(id_cliente),
        short_value(id_phone_unidade),
    )


def buscar_interacao_posterior_a_mensagem(
    cursor,
    id_cliente,
    id_phone_unidade,
    received_data_hora,
):
    cursor.execute("""
        SELECT c.last_interaction_at
        FROM chatbot.conversa c
        INNER JOIN chatbot.chat ch ON ch.id_chat=c.id_chat
        INNER JOIN chatbot.central_pos_venda u ON u.id_central=c.id_central
        WHERE ch.id_cliente = %s
          AND u.phone_number_id = %s
          AND c.last_interaction_at IS NOT NULL
          -- A Meta informa segundos inteiros; o histórico local tem microssegundos.
          -- O WAMID e a regra de fila aberta ainda se aplicam dentro do mesmo segundo.
          AND %s < date_trunc('second', c.last_interaction_at)
        ORDER BY c.last_interaction_at DESC, c.id_conversa DESC
        LIMIT 1;
    """, (
        id_cliente,
        id_phone_unidade,
        received_data_hora,
    ))

    resultado = cursor.fetchone()
    return resultado[0] if resultado else None


def avaliar_filas_abertas_turno(cursor, id_cliente, id_phone_unidade):
    cursor.execute("""
        WITH filas_abertas AS (
            SELECT
                f.id_mensagem,
                f.id_conversa,
                f.id_hash_msg,
                f.status,
                f.received_data_hora
            FROM chatbot.fila_mensagens f
            JOIN chatbot.central_pos_venda b ON b.id_central=f.id_central
            WHERE f.id_cliente = %s
              AND b.phone_number_id = %s
              AND f.status IN ('pending', 'processing')
        ),
        filas_sem_resposta_bot AS (
            SELECT
                f.id_mensagem
            FROM filas_abertas f
            LEFT JOIN chatbot.historico_mensagens h
              ON h.id_conversa = f.id_conversa
             AND h.quem_enviou = 'bot'
             AND h.status_envio = 'sent'
             AND h.id_mensagem_fila = f.id_mensagem
             AND h.id_hash_cliente_origem = f.id_hash_msg
            WHERE h.id_mensagem IS NULL
            ORDER BY f.received_data_hora, f.id_mensagem
            LIMIT 1
        )
        SELECT
            EXISTS (SELECT 1 FROM filas_abertas) AS existe_fila_aberta,
            NOT EXISTS (SELECT 1 FROM filas_sem_resposta_bot) AS todas_abertas_respondidas,
            (SELECT COUNT(*) FROM filas_abertas) AS total_abertas,
            (SELECT id_mensagem FROM filas_sem_resposta_bot LIMIT 1) AS id_mensagem_bloqueadora;
    """, (id_cliente, id_phone_unidade))

    resultado = cursor.fetchone()

    existe_fila_aberta = bool(resultado[0]) if resultado else False
    todas_abertas_respondidas = bool(resultado[1]) if resultado else False
    total_abertas = int(resultado[2] or 0) if resultado else 0
    id_mensagem_bloqueadora = resultado[3] if resultado else None

    logger.debug(
        "turno_cliente_fila_consultada | acao=avaliar_abertas cliente=%s phone_number_id=%s existe=%s todas_respondidas=%s total=%s bloqueadora=%s",
        short_value(id_cliente),
        short_value(id_phone_unidade),
        existe_fila_aberta,
        todas_abertas_respondidas,
        total_abertas,
        id_mensagem_bloqueadora,
    )

    return {
        "existe_fila_aberta": existe_fila_aberta,
        "todas_abertas_respondidas": todas_abertas_respondidas,
        "total_abertas": total_abertas,
        "id_mensagem_bloqueadora": id_mensagem_bloqueadora,
    }
