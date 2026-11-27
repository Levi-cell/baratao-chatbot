"""Reassociação comprovada de uma conversa provisória, na transação do webhook."""


def localizar_conversa_provisoria(central, provisoria, uid, cursor):
    """Só uma ficha sem telefone nem outros atendimentos pode ser absorvida."""
    cursor.execute("""
        SELECT c.id_conversa, ch.id_chat FROM chatbot.cliente cl
        JOIN chatbot.chat ch USING (id_cliente)
        JOIN chatbot.conversa c USING (id_chat)
        JOIN chatbot.solicitacao_contato s USING (id_conversa)
        JOIN chatbot.identidade_bsuid a ON a.id_cliente=cl.id_cliente AND a.id_central=ch.id_central
        WHERE cl.id_cliente=%s AND cl.waid_telefone IS NULL AND ch.id_central=%s
          AND c.status_ativa AND s.motivo='cadastro' AND s.bsuid_destino=%s
          AND a.user_id=s.bsuid_destino AND a.vigente AND NOT a.suspender_telefone
          AND NOT EXISTS (SELECT FROM chatbot.identidade_bsuid b WHERE b.id_cliente=cl.id_cliente
                          AND (b.id_central,b.user_id)<>(a.id_central,a.user_id))
          AND NOT EXISTS (SELECT FROM chatbot.chat outro WHERE outro.id_cliente=cl.id_cliente
                          AND outro.id_chat<>ch.id_chat)
          AND NOT EXISTS (SELECT FROM chatbot.conversa outra WHERE outra.id_chat=ch.id_chat
                          AND outra.id_conversa<>c.id_conversa)
        FOR UPDATE OF cl, ch, c, s, a
    """, (provisoria, central, uid))
    return cursor.fetchone()


def tem_conversa_ativa(id_chat, cursor):
    cursor.execute("SELECT EXISTS (SELECT FROM chatbot.conversa WHERE id_chat=%s AND status_ativa)", (id_chat,))
    return cursor.fetchone()[0]


def obter_chat_canonico(cliente, central, cursor):
    cursor.execute("""
        INSERT INTO chatbot.chat (id_cliente,id_central) VALUES (%s,%s)
        ON CONFLICT (id_cliente,id_central) DO UPDATE SET id_cliente=EXCLUDED.id_cliente
        RETURNING id_chat
    """, (cliente, central))
    return cursor.fetchone()[0]


def mover_conversa(conversa, chat, cursor):
    cursor.execute("UPDATE chatbot.conversa SET id_chat=%s WHERE id_conversa=%s", (chat, conversa))


def mover_alias(provisoria, canonica, central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET id_cliente=%s
        WHERE id_cliente=%s AND id_central=%s AND user_id=%s AND vigente
    """, (canonica, provisoria, central, uid))


def mover_fila(provisoria, canonica, cursor):
    cursor.execute("UPDATE chatbot.fila_mensagens SET id_cliente=%s WHERE id_cliente=%s", (canonica, provisoria))


def atualizar_cadastro_pela_conversa(conversa, provisoria, canonica, cursor):
    # Nome é o confirmado nesta compra. O novo CPF será confirmado no turno seguinte.
    cursor.execute("""
        UPDATE chatbot.cliente cl SET nome_titular=a.nome_titular,
            username=CASE WHEN p.username_observado_em IS NOT NULL AND
                (cl.username_observado_em IS NULL OR p.username_observado_em>cl.username_observado_em)
                THEN p.username ELSE cl.username END,
            username_observado_em=greatest(cl.username_observado_em,p.username_observado_em)
        FROM chatbot.atendimento_pos_venda a, chatbot.cliente p
        WHERE cl.id_cliente=%s AND a.id_conversa=%s AND p.id_cliente=%s
    """, (canonica, conversa, provisoria))


def excluir_chat_provisorio(chat, cliente, cursor):
    cursor.execute("DELETE FROM chatbot.chat WHERE id_chat=%s AND id_cliente=%s", (chat, cliente))


def excluir_cliente_provisorio(cliente, cursor):
    cursor.execute("DELETE FROM chatbot.cliente WHERE id_cliente=%s AND waid_telefone IS NULL", (cliente,))
    if cursor.rowcount != 1:
        raise ValueError("O cadastro provisório mudou durante a conciliação.")
