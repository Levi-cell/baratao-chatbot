def inserir_alias(id_central, user_id, id_cliente, wamid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.identidade_bsuid (id_central, user_id, id_cliente, wamid_origem)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_central, user_id) DO NOTHING
    """, (id_central, user_id, id_cliente, wamid))

def conferir_alias(id_central, user_id, id_cliente, cursor):
    cursor.execute("""
        SELECT id_cliente, vigente FROM chatbot.identidade_bsuid
        WHERE id_central=%s AND user_id=%s FOR UPDATE
    """, (id_central, user_id))
    if cursor.fetchone() != (id_cliente, True):
        raise ValueError("Vínculo de identidade incompatível")

def atualizar_username(id_cliente, username, observado_em, cursor):
    if username:
        cursor.execute("""
            UPDATE chatbot.cliente SET username=%s, username_observado_em=%s
            WHERE id_cliente=%s AND
                  (username_observado_em IS NULL OR username_observado_em < %s)
        """, (username, observado_em, id_cliente, observado_em))


def atualizar_username_por_recibo(central, wamid, uid, telefone, username, observado_em, cursor):
    """Só atualiza um perfil já associado ao destinatário do envio confirmado."""
    cursor.execute("""
        UPDATE chatbot.cliente cl SET username=%s, username_observado_em=%s
        FROM chatbot.historico_mensagens h
        JOIN chatbot.conversa c USING (id_conversa)
        JOIN chatbot.chat ch USING (id_chat)
        WHERE cl.id_cliente=ch.id_cliente AND c.id_central=%s AND h.id_hash_msg=%s
          AND h.quem_enviou='bot' AND h.status_envio='sent'
          AND (cl.username_observado_em IS NULL OR cl.username_observado_em < %s)
          AND ((h.tipo_destinatario='wa_id' AND h.valor_destinatario=%s AND cl.waid_telefone=%s)
              OR (h.tipo_destinatario='bsuid' AND h.valor_destinatario=%s AND EXISTS
                  (SELECT FROM chatbot.identidade_bsuid a WHERE a.id_cliente=cl.id_cliente
                   AND a.id_central=c.id_central AND a.user_id=%s AND a.vigente)))
    """, (username, observado_em, central, wamid, observado_em, telefone, telefone, uid, uid))


def buscar_central(phone_id, conta, cursor, *, incluir_suspensa=False):
    cursor.execute("""
        SELECT id_central FROM chatbot.central_pos_venda
        WHERE phone_number_id=%s AND (ativa OR %s) AND waba_id=%s
    """, (phone_id, incluir_suspensa, conta))
    return cursor.fetchone()


def serializar_chave(chave, cursor):
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (chave,))


def cliente_telefone(wa_id, cursor):
    cursor.execute("SELECT id_cliente FROM chatbot.cliente WHERE waid_telefone=%s FOR UPDATE", (wa_id,))
    linha = cursor.fetchone()
    return linha[0] if linha else None


def buscar_alias(central, uid, cursor):
    cursor.execute("""
        SELECT id_cliente, vigente, suspender_telefone FROM chatbot.identidade_bsuid
        WHERE id_central=%s AND user_id=%s FOR UPDATE
    """, (central, uid))
    return cursor.fetchone()


def alias_vigente_do_cliente(central, cliente, cursor):
    cursor.execute("""
        SELECT user_id FROM chatbot.identidade_bsuid
        WHERE id_central=%s AND id_cliente=%s AND vigente
    """, (central, cliente))
    return cursor.fetchone()


def criar_cliente(telefone, cursor):
    cursor.execute("INSERT INTO chatbot.cliente (waid_telefone) VALUES (%s) RETURNING id_cliente", (telefone,))
    return cursor.fetchone()[0]


def definir_telefone(cliente, telefone, cursor):
    cursor.execute("UPDATE chatbot.cliente SET waid_telefone=%s WHERE id_cliente=%s", (telefone, cliente))


def alias_confirmado(central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET suspender_telefone=false
        WHERE id_central=%s AND user_id=%s AND vigente
    """,(central,uid))


def dados_telefone(cliente, cursor):
    cursor.execute("SELECT waid_telefone FROM chatbot.cliente WHERE id_cliente=%s FOR UPDATE", (cliente,))
    return cursor.fetchone()[0]


def aposentadoria_alias(central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET vigente=false, suspender_telefone=true
        WHERE id_central=%s AND user_id=%s AND vigente
    """, (central,uid))


def preservar_bloqueio_na_rotacao(central, cliente, novo_uid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.cliente_bloqueado_meta (id_central, wa_id_cliente)
        SELECT %s, %s FROM chatbot.cliente cl
        WHERE cl.id_cliente=%s AND EXISTS (
            SELECT FROM chatbot.cliente_bloqueado_meta b WHERE b.id_central=%s
            AND (b.wa_id_cliente=cl.waid_telefone OR b.wa_id_cliente IN (
                SELECT a.user_id FROM chatbot.identidade_bsuid a
                WHERE a.id_cliente=cl.id_cliente AND a.id_central=b.id_central
            )))
        ON CONFLICT DO NOTHING
    """, (central, novo_uid, cliente, central))


def suspender_alias(central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET suspender_telefone=true
        WHERE id_central=%s AND user_id=%s AND vigente
    """, (central,uid))


def trocar_bsuid_pendente(central, anterior, novo, cursor):
    cursor.execute("""
        DELETE FROM chatbot.solicitacao_contato s USING chatbot.conversa c
        WHERE s.id_conversa=c.id_conversa AND c.id_central=%s AND s.bsuid_destino=%s
        AND %s::text <> s.bsuid_destino
    """, (central,anterior,novo))


def impedimento(central, cliente, identificadores, cursor):
    cursor.execute("""
        SELECT EXISTS (SELECT FROM chatbot.contato_interno WHERE waid_telefone=ANY(%s))
            OR EXISTS (SELECT FROM chatbot.cliente_bloqueado_meta
                       WHERE id_central=%s AND (wa_id_cliente=ANY(%s)
                           OR wa_id_cliente IN (SELECT user_id FROM chatbot.identidade_bsuid
                               WHERE id_cliente=%s AND id_central=%s)))
            OR EXISTS (SELECT FROM chatbot.chat ch JOIN chatbot.conversa c USING(id_chat)
                       JOIN chatbot.etapa e ON e.id_etapa=c.id_etapa_atual
                       WHERE ch.id_cliente=%s AND ch.id_central=%s AND NOT c.status_ativa
                         AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente'
                         AND c.finalizou_em + e.bloqueio_dias * interval '1 day' > now())
    """, (identificadores,central,identificadores,cliente,central,cliente,central))
    return cursor.fetchone()[0]


def falha_da_rota_atual(central, wamid, cursor):
    """Ignora recibo sem correlação, conversa encerrada e resposta já ultrapassada."""
    cursor.execute("""
        SELECT c.id_conversa,h.id_mensagem_fila,a.user_id,a.suspender_telefone
        FROM chatbot.historico_mensagens h JOIN chatbot.conversa c USING(id_conversa)
        JOIN chatbot.chat ch USING(id_chat)
        JOIN chatbot.identidade_bsuid a ON a.id_cliente=ch.id_cliente AND a.id_central=c.id_central AND a.vigente
        WHERE c.id_central=%s AND h.id_hash_msg=%s AND c.status_ativa AND h.tipo_destinatario='wa_id'
          AND h.quem_enviou='bot' AND h.status_envio='sent'
          AND NOT EXISTS(SELECT FROM chatbot.historico_mensagens p WHERE p.id_conversa=c.id_conversa
                         AND (p.received_data_hora,p.id_mensagem)>(h.received_data_hora,h.id_mensagem))
        FOR UPDATE OF c
    """,(central,wamid))
    return cursor.fetchone()
