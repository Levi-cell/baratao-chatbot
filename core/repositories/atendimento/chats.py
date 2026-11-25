"""Operações sobre o vínculo cliente × central, na transação do chamador."""


def garantir_chat_para_atendimento(id_cliente, id_central, cursor):
    """Serializa abrir/retomar pela linha do chat, antes do lock da conversa."""
    cursor.execute("""
        INSERT INTO chatbot.chat (id_cliente, id_central) VALUES (%s, %s)
        ON CONFLICT (id_cliente, id_central)
        DO UPDATE SET id_cliente = EXCLUDED.id_cliente;
    """, (id_cliente, id_central))
