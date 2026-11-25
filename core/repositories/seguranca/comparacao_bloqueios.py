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
        SELECT id_unidade, nome_unidade, waba_id, phone_number_id
        FROM chatbot.unidade
        WHERE waba_id IS NOT NULL
          AND BTRIM(waba_id) <> ''
          AND phone_number_id IS NOT NULL
          AND BTRIM(phone_number_id) <> ''
        ORDER BY id_unidade;
        """
    )
    return cursor.fetchall()


def listar_bloqueios_para_comparacao(cursor):
    cursor.execute(
        """
        SELECT
            cbm.id_bloqueio,
            cbm.id_cliente,
            cbm.nome,
            cbm.wa_id_cliente,
            cbm.id_unidade,
            cbm.phone_id_unidade,
            u.nome_unidade,
            u.waba_id,
            u.phone_number_id,
            c.nome
        FROM chatbot.cliente_bloqueado_meta AS cbm
        JOIN chatbot.unidade AS u
          ON u.id_unidade = cbm.id_unidade
        LEFT JOIN chatbot.cliente AS c
          ON c.id_cliente = cbm.id_cliente
        ORDER BY cbm.id_unidade, cbm.wa_id_cliente;
        """
    )
    return cursor.fetchall()
