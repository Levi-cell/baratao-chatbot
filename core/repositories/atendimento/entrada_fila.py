"""Grava a entrada deduplicada para a central e o canal de origem."""
from psycopg.types.json import Jsonb


def entrada_ja_registrada(wamid, cursor):
    cursor.execute("SELECT 1 FROM chatbot.fila_mensagens WHERE id_hash_msg=%s", (wamid,))
    return cursor.fetchone() is not None


def inserir_entrada_fila(dados, cursor):
    cursor.execute("""
        INSERT INTO chatbot.fila_mensagens (id_central,id_cliente,cliente_telefone,
            user_id_origem,username_origem,id_hash_msg,received_data_hora,tipo_mensagem,
            conteudo_texto,interativo,status,retry_count,next_attempt_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id_hash_msg) DO NOTHING
    """,(dados["id_central"],dados["id_cliente"],dados["cliente_telefone"],
         dados.get("user_id_origem"),dados.get("username_origem"),dados["id_hash_msg"],
         dados["received_data_hora"],dados["tipo_mensagem"],dados["conteudo_texto"],
         Jsonb(dados["interativo"]) if dados.get("interativo") else None,
         dados["status"],dados["retry_count"],dados["next_attempt_at"]))
    return cursor.rowcount
