"""Cadastro, contatos e apresentação pendente derivados do histórico confirmado."""

from core.etapas_pos_venda import ETAPA_DETALHES, ETAPA_PEDIDOS, ETAPA_PRODUTO


def buscar_contexto_pos_venda(id_conversa, cursor):
    cursor.execute("""
        SELECT b.telefone_atacadao, b.telefone_baratao, a.nome_titular,
               a.cpf_titular, a.cidade_loja_compra,
               (ultima.id_mensagem IS NULL OR
                (c.id_etapa_atual = %s AND
                 ultima.interativo->>'_migracao_produto_pendente' = 'true') OR
                (c.id_etapa_atual = %s AND ultima.interativo->>'_reapresentar_detalhes' = 'true')),
               a.produto, a.assunto::text,
               CASE WHEN c.id_etapa_atual = %s THEN ARRAY(SELECT codigo FROM chatbot.filial_compra) END,
               b.phone_number_id, b.waba_id AS messaging_account_id, b.waac_id,
               ARRAY(SELECT ARRAY[p.numero, f.nome, f.grupo] FROM chatbot.pedido_conversa p
                     LEFT JOIN chatbot.filial_compra f ON f.codigo = p.codigo_filial
                     WHERE p.id_conversa = c.id_conversa ORDER BY p.numero),
               a.perdeu_nota, a.detalhes, a.telefone_compartilhado
        FROM chatbot.conversa c
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
    """, (ETAPA_PRODUTO, ETAPA_DETALHES, ETAPA_PEDIDOS, id_conversa))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Cadastro/central ausente para a conversa.")
    telefone, uid, motivo, etapa, wamids, erros, suspenso = ler_rota_contato(id_conversa,cursor)
    return {
        "wa_id_confirmado": None if suspenso or row[15] else telefone, "bsuid_vigente": uid,
        "reconfirmar_telefone": bool(suspenso),
        "solicitacao_contato": {"motivo": motivo, "etapa": etapa, "wamids": wamids, "erros": erros}
                              if motivo else None,
        "central": {
            "telefone_atacadao": row[0], "telefone_baratao": row[1],
            "phone_number_id": row[9], "messaging_account_id": row[10], "waac_id": row[11],
        },
        "cadastro": dict(zip(
            ("nome_titular", "cpf_titular", "cidade_loja_compra"), row[2:5],
        )),
        "apresentacao_pendente": bool(row[5]),
        "produto": row[6],
        "assunto": row[7],
        "pedidos_com_filial": [(numero, filial) for numero, filial, _ in row[12]],
        "grupos_das_notas": frozenset(grupo for _, _, grupo in row[12]),
        "telefone_compartilhado": row[15],
        "perdeu_nota": row[13],
        "detalhes": row[14],
        "codigos_filiais": frozenset(row[8] or ()),
    }


def ler_rota_contato(id_conversa, cursor):
    cursor.execute("""
        SELECT cl.waid_telefone, a.user_id, s.motivo, s.id_etapa_retomada,
               s.wamids_aceitos, s.erros_cliente, a.suspender_telefone
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat=c.id_chat
        JOIN chatbot.cliente cl ON cl.id_cliente=ch.id_cliente
        LEFT JOIN chatbot.identidade_bsuid a
          ON a.id_cliente=cl.id_cliente AND a.id_central=c.id_central AND a.vigente
        LEFT JOIN chatbot.solicitacao_contato s ON s.id_conversa=c.id_conversa
        WHERE c.id_conversa=%s
    """, (id_conversa,))
    return cursor.fetchone()
