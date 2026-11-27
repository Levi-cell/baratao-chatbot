import logging

from core.logging_config import short_value


logger = logging.getLogger("db.bloqueio_meta")


def registrar_evento_flood_banco(
    wa_id_cliente,
    phone_id_unidade,
    id_hash_msg,
    cursor,
):
    cursor.execute("""
        INSERT INTO chatbot.webhook_flood_evento (
            wa_id_cliente,
            id_central,
            id_hash_msg
        )
        SELECT %s, id_central, %s
        FROM chatbot.central_pos_venda
        WHERE phone_number_id = %s
        ON CONFLICT (id_hash_msg) DO NOTHING;
    """, (wa_id_cliente, id_hash_msg, phone_id_unidade))
    logger.debug(
        "flood_evento_insert | acao=registrar wa_id_cliente=%s phone_id_unidade=%s id_hash_msg=%s linhas=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        short_value(id_hash_msg),
        cursor.rowcount,
    )


def contar_eventos_flood_banco(
    wa_id_cliente,
    phone_id_unidade,
    cursor,
    janela_segundos=60,
):
    cursor.execute("""
        SELECT COUNT(*)
        FROM chatbot.webhook_flood_evento
        JOIN chatbot.central_pos_venda b USING (id_central)
        WHERE wa_id_cliente = %s
          AND b.phone_number_id = %s
          AND received_at >= NOW() - (%s * INTERVAL '1 second');
    """, (wa_id_cliente, phone_id_unidade, janela_segundos))

    resultado = cursor.fetchone()
    total = int(resultado[0]) if resultado else 0
    logger.debug(
        "flood_evento_count | acao=contar wa_id_cliente=%s phone_id_unidade=%s janela=%s total=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        janela_segundos,
        total,
    )
    return total


def limpar_eventos_flood_antigos(cursor, horas=2):
    cursor.execute("""
        DELETE FROM chatbot.webhook_flood_evento
        WHERE received_at < NOW() - (%s * INTERVAL '1 hour');
    """, (horas,))

    logger.debug(
        "flood_evento_limpeza | acao=limpar_antigos horas=%s linhas=%s",
        horas,
        cursor.rowcount,
    )
    return cursor.rowcount


def buscar_central_para_bloqueio(phone_number_id, cursor):
    """Fixa o vínculo com o número até o commit da intenção de bloqueio."""
    cursor.execute("""
        SELECT id_central, phone_number_id, waba_id, waac_id
        FROM chatbot.central_pos_venda
        WHERE phone_number_id = %s
        FOR SHARE;
    """, (phone_number_id,))
    return _central_do_registro(cursor.fetchone())


def consultar_protecao_remetente(identificadores, phone_number_id, conta_origem, cursor):
    """Relaciona o remetente às rotas conhecidas dentro da central antes do flood."""
    cursor.execute("""
        WITH central AS (
            SELECT id_central, phone_number_id, waba_id, waac_id
            FROM chatbot.central_pos_venda WHERE phone_number_id=%s AND waba_id=%s
        ), clientes AS (
            SELECT id_cliente FROM chatbot.cliente WHERE waid_telefone=ANY(%s)
            UNION
            SELECT a.id_cliente FROM chatbot.identidade_bsuid a JOIN central USING(id_central)
            WHERE a.user_id=ANY(%s)
        ), rotas AS (
            SELECT unnest(%s::text[]) AS chave
            UNION SELECT waid_telefone FROM chatbot.cliente JOIN clientes USING(id_cliente)
            UNION SELECT user_id FROM chatbot.identidade_bsuid JOIN central USING(id_central)
                  JOIN clientes USING(id_cliente)
        )
        SELECT b.*, EXISTS (
            SELECT FROM chatbot.cliente_bloqueado_meta m WHERE m.id_central=b.id_central
            AND m.wa_id_cliente IN (SELECT chave FROM rotas)
        ), (
            SELECT coalesce(f.cliente_telefone, f.user_id_origem)
            FROM chatbot.fila_mensagens f JOIN clientes USING(id_cliente)
            WHERE f.id_central=b.id_central ORDER BY f.id_mensagem LIMIT 1
        )
        FROM central b
    """, (phone_number_id, conta_origem, identificadores, identificadores, identificadores))
    row = cursor.fetchone()
    if not row:
        return None
    return _central_do_registro(row) if row[4] else None, row[5]


def _central_do_registro(row):
    if row is None:
        return None
    return {
        "id_central": row[0], "phone_number_id": row[1],
        "messaging_account_id": row[2], "waac_id": row[3],
    }


def registrar_cliente_bloqueado_meta_banco(wa_id_cliente, id_central, cursor):
    cursor.execute("""
        INSERT INTO chatbot.cliente_bloqueado_meta (id_central, wa_id_cliente)
        VALUES (%s, %s)
        ON CONFLICT (id_central, wa_id_cliente) DO NOTHING;
    """, (id_central, wa_id_cliente))
