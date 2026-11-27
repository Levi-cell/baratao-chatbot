def abrir_solicitacao(id_conversa, motivo, etapa, bsuid, wamid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.solicitacao_contato
            (id_conversa, motivo, id_etapa_retomada, bsuid_destino, wamid_solicitacao, wamids_aceitos)
        VALUES (%s,%s,%s,%s,%s,ARRAY[%s]::text[])
    """, (id_conversa, motivo, etapa, bsuid, wamid, wamid))

def ler_solicitacao_para_confirmar(id_conversa, bsuid, cursor):
    cursor.execute("""
        SELECT id_etapa_retomada, motivo, wamid_solicitacao FROM chatbot.solicitacao_contato
        WHERE id_conversa=%s AND bsuid_destino=%s FOR UPDATE
    """, (id_conversa, bsuid))
    return cursor.fetchone()

def encerrar_solicitacao(id_conversa, cursor):
    cursor.execute("DELETE FROM chatbot.solicitacao_contato WHERE id_conversa=%s", (id_conversa,))


def repetir_solicitacao(conversa, uid, wamid, cursor):
    cursor.execute("""
        UPDATE chatbot.solicitacao_contato SET erros_cliente=least(3,erros_cliente+1),
            wamids_aceitos=array_append(wamids_aceitos,%s)
        WHERE id_conversa=%s AND bsuid_destino=%s AND NOT (%s=ANY(wamids_aceitos))
    """, (wamid,conversa,uid,wamid))


def pendencia_ativa(central,cliente,uid,cursor):
    cursor.execute("""
        SELECT s.wamids_aceitos, s.motivo FROM chatbot.solicitacao_contato s
        JOIN chatbot.conversa c USING(id_conversa) JOIN chatbot.chat ch USING(id_chat)
        WHERE c.status_ativa AND c.id_central=%s AND ch.id_cliente=%s AND s.bsuid_destino=%s
        FOR UPDATE OF s
    """,(central,cliente,uid))
    return cursor.fetchone()
