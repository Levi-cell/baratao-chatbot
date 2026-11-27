"""Operações SQL isoladas; conexão e transação pertencem ao chamador.

Extração organizacional: preserva os nomes do esquema usados pelo consumidor.
"""


def iniciar_leitura_consistente(cursor):
    cursor.execute(
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;"
    )


def listar_unidades_para_comparacao(cursor):
    cursor.execute(
        """
        SELECT id_central, nome, waba_id, phone_number_id
        FROM chatbot.central_pos_venda
        WHERE waba_id IS NOT NULL
          AND BTRIM(waba_id) <> ''
          AND phone_number_id IS NOT NULL
          AND BTRIM(phone_number_id) <> ''
        ORDER BY id_central;
        """
    )
    return cursor.fetchall()


def listar_bloqueios_para_comparacao(cursor):
    cursor.execute(
        """
        SELECT m.wa_id_cliente, u.id_central, u.nome, u.waba_id, u.phone_number_id,
               COALESCE(telefone.id_cliente, alias.id_cliente),
               COALESCE(telefone.nome_titular, privado.nome_titular)
        FROM chatbot.cliente_bloqueado_meta m
        JOIN chatbot.central_pos_venda u USING (id_central)
        LEFT JOIN chatbot.cliente telefone ON telefone.waid_telefone=m.wa_id_cliente
        LEFT JOIN chatbot.identidade_bsuid alias
          ON alias.id_central=m.id_central AND alias.user_id=m.wa_id_cliente
        LEFT JOIN chatbot.cliente privado ON privado.id_cliente=alias.id_cliente
        ORDER BY u.id_central, m.wa_id_cliente;
        """
    )
    return cursor.fetchall()
