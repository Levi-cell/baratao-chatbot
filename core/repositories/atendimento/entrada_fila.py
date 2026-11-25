"""Operações SQL isoladas; conexão e transação pertencem ao chamador.

Extração organizacional: preserva os nomes do esquema usados pelo consumidor.
"""


def inserir_entrada_fila(dados, cursor):
    cursor.execute("""
        INSERT INTO chatbot.fila_mensagens (
            status,
            retry_count,
            next_attempt_at,
            processing_started_at,
            received_data_hora,
            cliente_telefone,
            conteudo_texto,
            tipo_mensagem,
            id_hash_msg,
            id_phone_unidade,
            unidade_telefone
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT DO NOTHING
    """, (
        dados["status"],
        dados["retry_count"],
        dados["next_attempt_at"],
        dados["processing_started_at"],
        dados["received_data_hora"],
        dados["cliente_telefone"],
        dados["conteudo_texto"],
        dados["tipo_mensagem"],
        dados["id_hash_msg"],
        dados["id_phone_unidade"],
        dados["unidade_telefone"],
    ))
    return cursor.rowcount
