"""Persistência de conversas do pós-venda; transações pertencem ao worker."""

MOTIVOS_ENCERRAMENTO_VALIDOS = {
    "visita_pendente", "encaminhamento", "encaminhamento_midia",
    "encaminhamento_humano", "encaminhamento_sem_avanco",
}


def inserindo_em_conversa_caso_seja_nova(id_cliente, id_unidade, cursor):
    cursor.execute("""
        INSERT INTO chatbot.chat (id_cliente, id_central) VALUES (%s, %s)
        ON CONFLICT (id_cliente, id_central) DO UPDATE SET id_cliente=EXCLUDED.id_cliente
        RETURNING id_chat;
    """, (id_cliente, id_unidade))
    id_chat = cursor.fetchone()[0]
    cursor.execute("""
        INSERT INTO chatbot.conversa (id_chat, id_central, id_etapa_atual)
        VALUES (%s, %s, 1)
        ON CONFLICT (id_chat) WHERE status_ativa DO NOTHING
        RETURNING id_conversa;
    """, (id_chat, id_unidade))
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT id_conversa FROM chatbot.conversa WHERE id_chat = %s AND status_ativa", (id_chat,))
        row = cursor.fetchone()
    if not row:
        raise RuntimeError("Não foi possível criar ou localizar a conversa ativa.")
    cursor.execute("""
        INSERT INTO chatbot.atendimento_pos_venda (id_conversa) VALUES (%s)
        ON CONFLICT (id_conversa) DO NOTHING;
    """, (row[0],))
    return row[0]


def tentar_lock_conversa(id_conversa, cursor):
    cursor.execute("SELECT lock_ok, lock_version_atual FROM chatbot.lock_conversa(%s)", (id_conversa,))
    return cursor.fetchone() or (False, None)


def unlock_conversa(id_conversa, lock_version, cursor):
    if lock_version is None:
        return False
    cursor.execute("SELECT chatbot.unlock_conversa(%s, %s)", (id_conversa, lock_version))
    row = cursor.fetchone()
    return bool(row and row[0])


def buscar_estado_conversa(id_cliente, id_unidade, cursor):
    cursor.execute("""
        SELECT c.id_conversa, c.id_etapa_atual, c.status_ativa, c.finalizou_em,
               CASE WHEN c.status_ativa THEN 'ativa'
                    WHEN e.bloqueio_dias > 0 AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente' AND c.finalizou_em >
                         CURRENT_TIMESTAMP - e.bloqueio_dias * INTERVAL '1 day'
                    THEN 'bloqueada' ELSE 'liberada' END,
               c.last_message_from, c.turnos_sem_avanco
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat = c.id_chat
        JOIN chatbot.etapa e ON e.id_etapa = c.id_etapa_atual
        WHERE ch.id_cliente = %s AND c.id_central = %s
        ORDER BY c.status_ativa DESC, c.iniciou_em DESC, c.id_conversa DESC LIMIT 1;
    """, (id_cliente, id_unidade))
    row = cursor.fetchone()
    return dict(zip(("id_conversa", "id_etapa_atual", "status_ativa", "finalizou_em",
                     "estado", "last_message_from", "turnos_sem_avanco"), row)) if row else None


def atualizar_conversa_mensagem_cliente(id_conversa, data_interacao, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa SET last_interaction_at = %s, last_message_from = 'cliente'
        WHERE id_conversa = %s AND status_ativa;
    """, (data_interacao, id_conversa))


def atualizar_conversa_resposta_bot_sem_avancar(id_conversa, data_interacao, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa SET last_interaction_at = %s, last_message_from = 'bot'
        WHERE id_conversa = %s AND status_ativa;
    """, (data_interacao, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Conversa deixou de estar ativa.")


def atualizar_conversa_por_transicao(id_conversa, origem, evento, destino, data_interacao, cursor, *, permitir_reaplicacao=False):
    cursor.execute("""
        UPDATE chatbot.conversa c SET id_etapa_atual = %s,
            last_interaction_at = %s, last_message_from = 'bot'
        WHERE c.id_conversa = %s AND c.status_ativa
          AND (c.id_etapa_atual = %s OR (%s AND c.id_etapa_atual = %s))
          AND EXISTS (SELECT FROM chatbot.etapa_transicao
                      WHERE id_etapa_origem = %s AND evento = %s AND id_etapa_destino = %s);
    """, (destino, data_interacao, id_conversa, origem, permitir_reaplicacao, destino, origem, evento, destino))
    if cursor.rowcount != 1:
        raise ValueError("Transição recusada pelo estado atual ou mapa de etapas.")


def encerrar_conversa(id_conversa, motivo_encerramento, cursor):
    if motivo_encerramento not in MOTIVOS_ENCERRAMENTO_VALIDOS:
        raise ValueError("Motivo de encerramento inválido.")
    cursor.execute("""
        UPDATE chatbot.conversa SET status_ativa = false,
            finalizou_em = clock_timestamp(), motivo_encerramento = %s
        WHERE id_conversa = %s AND status_ativa RETURNING finalizou_em;
    """, (motivo_encerramento, id_conversa))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("SELECT finalizou_em FROM chatbot.conversa WHERE id_conversa = %s AND NOT status_ativa", (id_conversa,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Conversa ausente ao finalizar.")
    return row[0]
