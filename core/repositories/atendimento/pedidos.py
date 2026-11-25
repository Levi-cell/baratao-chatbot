"""Registro da resposta sobre a nota no atendimento atual. O worker controla a transação."""


def registrar_situacao_nota(id_conversa, perdeu_nota, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda SET perdeu_nota = %s WHERE id_conversa = %s;
    """, (perdeu_nota, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao registrar a nota.")


def inserir_pedidos_da_conversa(id_conversa, numeros, cursor):
    # A coluna gerada e a FK no banco vinculam o sufixo à filial em cada linha.
    cursor.executemany("""
        INSERT INTO chatbot.pedido_conversa (id_conversa, numero) VALUES (%s, %s)
        ON CONFLICT (id_conversa, numero) DO NOTHING;
    """, [(id_conversa, numero) for numero in numeros])
