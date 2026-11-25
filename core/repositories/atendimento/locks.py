"""Fencing reaproveitado do worker: lock versionado e renovação antes do envio."""

class LockConversaPerdido(RuntimeError):
    pass


def proteger_conversa(id_conversa, lock_version, cursor, *, renovar=False):
    cursor.execute("""
        SELECT id_conversa FROM chatbot.conversa
        WHERE id_conversa = %s AND processing IS TRUE AND lock_version = %s
          AND processing_started_at > clock_timestamp() - INTERVAL '110 seconds'
        FOR UPDATE;
    """, (id_conversa, lock_version))
    if cursor.fetchone() is None:
        raise LockConversaPerdido(f"Lock perdido: conversa={id_conversa}, versao={lock_version}")
    if renovar:
        cursor.execute("""
            UPDATE chatbot.conversa SET processing_started_at = clock_timestamp()
            WHERE id_conversa = %s AND lock_version = %s AND processing IS TRUE;
        """, (id_conversa, lock_version))


def reler_conversa(contexto_banco, lock_version, cursor):
    anterior = contexto_banco["conversa"]
    proteger_conversa(anterior["id_conversa"], lock_version, cursor)
    cursor.execute("""
        SELECT c.id_etapa_atual, c.status_ativa, c.last_message_from,
               c.finalizou_em, c.turnos_sem_avanco
        FROM chatbot.conversa c JOIN chatbot.chat ch ON ch.id_chat = c.id_chat
        WHERE c.id_conversa = %s AND ch.id_cliente = %s AND c.id_central = %s;
    """, (anterior["id_conversa"], contexto_banco["id_cliente"], contexto_banco["id_unidade"]))
    row = cursor.fetchone()
    if row is None or row[1] is not True or row[3] is not None:
        raise LockConversaPerdido("Conversa deixou de estar ativa para este cliente/central.")
    campos = ("id_etapa_atual", "status_ativa", "last_message_from", "finalizou_em", "turnos_sem_avanco")
    return dict(contexto_banco, conversa=dict(anterior, **dict(zip(campos, row)), lock_version=lock_version))
