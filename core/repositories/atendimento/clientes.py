import logging

from core.logging_config import short_value


logger = logging.getLogger("db.atendimento.clientes")


def inserindo_em_cliente_caso_seja_novo(waid_telefone, cursor):
    cursor.execute("""
        INSERT INTO chatbot.cliente (waid_telefone)
        VALUES (%s)
        ON CONFLICT (waid_telefone) DO NOTHING;
    """, (waid_telefone,))

    inserido = cursor.rowcount == 1

    cursor.execute("""
        SELECT id_cliente
        FROM chatbot.cliente
        WHERE waid_telefone = %s;
    """, (waid_telefone,))
    resultado = cursor.fetchone()

    if resultado:
        logger.debug(
            "cliente_insert_resultado | acao=obter_cliente telefone=%s id_cliente=%s inserido=%s",
            short_value(waid_telefone),
            resultado[0],
            inserido,
        )
        return resultado[0], inserido

    raise ValueError(
        "Anomalia Crítica: Cliente do telefone "
        f"{waid_telefone} desapareceu da base durante a verificação!"
    )


def atualizar_nome_titular(id_cliente, nome_titular, cursor):
    """Confirma o nome global usando a transação do worker."""
    cursor.execute(
        "UPDATE chatbot.cliente SET nome_titular = %s WHERE id_cliente = %s",
        (nome_titular, id_cliente),
    )
    if cursor.rowcount != 1:
        raise ValueError("Cliente não encontrado ao confirmar nome.")


def atualizar_cpf_titular(id_cliente, cpf_titular, cursor):
    """Confirma o CPF global usando a transação do worker."""
    cursor.execute(
        "UPDATE chatbot.cliente SET cpf_titular = %s WHERE id_cliente = %s",
        (cpf_titular, id_cliente),
    )
    if cursor.rowcount != 1:
        raise ValueError("Cliente não encontrado ao confirmar CPF.")


