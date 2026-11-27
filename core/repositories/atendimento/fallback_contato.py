def reservar_reconfirmacao(id_conversa, id_fila, wamid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.fallback_contato
            (id_conversa, id_mensagem_fila, wamid_original, estado)
        VALUES (%s,%s,%s,'reservado')
        ON CONFLICT DO NOTHING RETURNING id_conversa
    """, (id_conversa, id_fila, wamid))
    return cursor.fetchone() is not None


def concluir_reservas(conversa, cursor):
    cursor.execute("""
        UPDATE chatbot.fallback_contato SET estado='aceito', atualizado_em=now()
        WHERE id_conversa=%s AND estado='reservado'
    """,(conversa,))
