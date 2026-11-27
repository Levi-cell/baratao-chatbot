"""Prova do telefone por conversa e reassociação do cadastro provisório."""


def guardar_telefone_compartilhado(conversa, telefone, cursor):
    """Um valor nulo encerra a conferência após a fusão."""
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda SET telefone_compartilhado=%s
        WHERE id_conversa=%s
    """, (telefone, conversa))


def telefone_em_conferencia(central, uid, cursor):
    """Prova oficial mantida somente para o atendimento ativo desse BSUID."""
    cursor.execute("""
        SELECT a.telefone_compartilhado FROM chatbot.identidade_bsuid i
        JOIN chatbot.chat ch USING (id_cliente, id_central)
        JOIN chatbot.conversa c USING (id_chat)
        JOIN chatbot.atendimento_pos_venda a USING (id_conversa)
        WHERE i.id_central=%s AND i.user_id=%s AND i.vigente AND NOT i.suspender_telefone
          AND c.status_ativa AND a.telefone_compartilhado IS NOT NULL
    """, (central, uid))
    row = cursor.fetchone()
    return row[0] if row else None


def candidatos_para_cpf(origem, cpf, telefone, conversa, cursor):
    """O ID sequencial desempata fichas com a mesma prioridade."""
    cursor.execute("""
        SELECT cl.id_cliente, cl.cpf_titular, cl.waid_telefone,
               cl.id_cliente=%s AND EXISTS (
                   SELECT FROM chatbot.chat ch JOIN chatbot.conversa c USING (id_chat)
                   WHERE ch.id_cliente=cl.id_cliente AND c.id_conversa<>%s
               ) AS origem_com_historico
        FROM chatbot.cliente cl
        WHERE cl.id_cliente=%s OR cl.cpf_titular=%s OR cl.waid_telefone=%s
        ORDER BY cl.id_cliente FOR UPDATE OF cl
    """, (origem, conversa, origem, cpf, telefone))
    return cursor.fetchall()


def bloquear_chats(clientes, cursor):
    cursor.execute("""
        SELECT id_chat, id_cliente, id_central FROM chatbot.chat
        WHERE id_cliente=ANY(%s) ORDER BY id_chat FOR UPDATE
    """, (clientes,))
    cursor.fetchall()


def bloquear_aliases(clientes, cursor):
    cursor.execute("""
        SELECT id_central, user_id, id_cliente, vigente, suspender_telefone
        FROM chatbot.identidade_bsuid WHERE id_cliente=ANY(%s)
        ORDER BY id_central, user_id FOR UPDATE
    """, (clientes,))
    return cursor.fetchall()


def ha_trabalho_em_andamento(clientes, telefones, conversa, fila, cursor):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM chatbot.conversa c JOIN chatbot.chat ch USING (id_chat)
            WHERE ch.id_cliente=ANY(%s) AND c.id_conversa<>%s AND (c.status_ativa OR c.processing)
        ) OR EXISTS (
            SELECT FROM chatbot.fila_mensagens f
            LEFT JOIN chatbot.conversa c USING (id_conversa)
            LEFT JOIN chatbot.chat ch USING (id_chat)
            WHERE (f.id_cliente=ANY(%s) OR ch.id_cliente=ANY(%s)
                   OR (f.id_cliente IS NULL AND f.cliente_telefone=ANY(%s)))
              AND f.id_mensagem<>%s AND f.status IN ('pending','processing')
        )
    """, (clientes, conversa, clientes, clientes, telefones, fila))
    return cursor.fetchone()[0]


def identificador_bloqueado(telefones, clientes, cursor):
    cursor.execute("""
        SELECT EXISTS (SELECT FROM chatbot.contato_interno WHERE waid_telefone=ANY(%s))
            OR EXISTS (SELECT FROM chatbot.cliente_bloqueado_meta b
                       WHERE b.wa_id_cliente=ANY(%s) OR EXISTS (
                           SELECT FROM chatbot.identidade_bsuid a WHERE a.id_cliente=ANY(%s)
                             AND a.id_central=b.id_central AND a.user_id=b.wa_id_cliente))
    """, (telefones, telefones, clientes))
    return cursor.fetchone()[0]


def ha_bloqueio_temporario(clientes, cursor):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM chatbot.chat ch JOIN chatbot.conversa c USING (id_chat)
            JOIN chatbot.etapa e ON e.id_etapa=c.id_etapa_atual
            WHERE ch.id_cliente=ANY(%s) AND NOT c.status_ativa
              AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente'
              AND e.bloqueio_dias>0 AND c.finalizou_em + e.bloqueio_dias * interval '1 day' > now()
        )
    """, (clientes,))
    return cursor.fetchone()[0]


def garantir_chats_do_vencedor(vencedor, perdedores, cursor):
    cursor.execute("""
        INSERT INTO chatbot.chat (id_cliente, id_central)
        SELECT DISTINCT %s::integer, id_central FROM chatbot.chat WHERE id_cliente=ANY(%s)
        ON CONFLICT (id_cliente,id_central) DO NOTHING
    """, (vencedor, perdedores))


def mover_fila(perdedores, vencedor, cursor):
    cursor.execute("""
        UPDATE chatbot.fila_mensagens f SET id_cliente=%s WHERE f.id_cliente=ANY(%s)
            OR (f.id_cliente IS NULL AND EXISTS (
                SELECT FROM chatbot.conversa c JOIN chatbot.chat ch USING (id_chat)
                WHERE c.id_conversa=f.id_conversa AND ch.id_cliente=ANY(%s)))
    """, (vencedor, perdedores, perdedores))


def mover_conversas(perdedores, vencedor, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa c SET id_chat=destino.id_chat
        FROM chatbot.chat origem JOIN chatbot.chat destino USING (id_central)
        WHERE c.id_chat=origem.id_chat AND origem.id_cliente=ANY(%s) AND destino.id_cliente=%s
    """, (perdedores, vencedor))


def mover_aliases(perdedores, vencedor, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET id_cliente=%s WHERE id_cliente=ANY(%s)
    """, (vencedor, perdedores))


def liberar_telefone(perdedores, telefone, cursor):
    cursor.execute("""
        UPDATE chatbot.cliente SET waid_telefone=NULL WHERE id_cliente=ANY(%s) AND waid_telefone=%s
    """, (perdedores, telefone))


def atualizar_cadastro_pela_conversa(conversa, vencedor, telefone, cursor):
    """Somente um perfil observado nesta conversa pode substituir o do vencedor."""
    cursor.execute("""
        UPDATE chatbot.cliente cl SET nome_titular=a.nome_titular, waid_telefone=%s,
            username=CASE WHEN perfil.observado_em IS NOT NULL AND
                (cl.username_observado_em IS NULL OR perfil.observado_em>=cl.username_observado_em)
                THEN perfil.username ELSE cl.username END,
            username_observado_em=greatest(cl.username_observado_em, perfil.observado_em)
        FROM chatbot.atendimento_pos_venda a LEFT JOIN LATERAL (
            SELECT f.username_origem AS username, f.received_data_hora AS observado_em
            FROM chatbot.fila_mensagens f WHERE f.id_conversa=a.id_conversa
              AND nullif(btrim(f.username_origem),'') IS NOT NULL
            ORDER BY f.received_data_hora DESC, f.id_mensagem DESC LIMIT 1
        ) perfil ON true
        WHERE cl.id_cliente=%s AND a.id_conversa=%s
    """, (telefone, vencedor, conversa))
    if cursor.rowcount != 1:
        raise ValueError("Dados da conversa ausentes ao consolidar o cadastro.")


def excluir_chats_vazios(perdedores, cursor):
    cursor.execute("DELETE FROM chatbot.chat WHERE id_cliente=ANY(%s)", (perdedores,))


def excluir_cadastros_redundantes(perdedores, cursor):
    cursor.execute("DELETE FROM chatbot.cliente WHERE id_cliente=ANY(%s)", (perdedores,))
    if cursor.rowcount != len(perdedores):
        raise ValueError("Um dos cadastros mudou durante a conciliação.")
