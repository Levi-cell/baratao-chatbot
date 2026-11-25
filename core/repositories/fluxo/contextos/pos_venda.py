"""Cadastro, contatos e apresentação pendente derivados do histórico confirmado."""


def buscar_contexto_pos_venda(id_conversa, cursor):
    cursor.execute("""
        SELECT b.telefone_sofas, b.telefone_moveis, cl.nome_titular,
               cl.cpf_titular, cl.cidade_loja_compra,
               (ultima.id_mensagem IS NULL OR
                (c.id_etapa_atual = 3 AND
                 ultima.interativo->>'_migracao_produto_pendente' = 'true')),
               a.produto, a.assunto::text,
               CASE WHEN c.id_etapa_atual = 6 THEN ARRAY(SELECT codigo FROM chatbot.filial_compra) END
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat = c.id_chat
        JOIN chatbot.cliente cl ON cl.id_cliente = ch.id_cliente
        JOIN chatbot.central_pos_venda b ON b.id_central = c.id_central
        JOIN chatbot.atendimento_pos_venda a ON a.id_conversa = c.id_conversa
        LEFT JOIN LATERAL (
            SELECT h.id_mensagem, h.interativo
            FROM chatbot.historico_mensagens h
            WHERE h.id_conversa = c.id_conversa
              AND h.quem_enviou = 'bot' AND h.status_envio = 'sent'
            ORDER BY h.received_data_hora DESC, h.id_mensagem DESC LIMIT 1
        ) ultima ON true
        WHERE c.id_conversa = %s;
    """, (id_conversa,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Cadastro/central ausente para a conversa.")
    return {
        "central": {"telefone_sofas": row[0], "telefone_moveis": row[1]},
        "cadastro": dict(zip(
            ("nome_titular", "cpf_titular", "cidade_loja_compra"), row[2:5],
        )),
        "apresentacao_pendente": bool(row[5]),
        "produto": row[6],
        "assunto": row[7],
        "codigos_filiais": frozenset(row[8] or ()),
    }
