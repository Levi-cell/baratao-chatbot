"""Dados do atendimento por conversa; o worker controla commit e rollback."""


def atualizar_produto_do_atendimento(id_conversa, produto, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET produto = %s WHERE id_conversa = %s;
    """, (produto, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar produto.")


def atualizar_assunto_do_atendimento(id_conversa, assunto, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET assunto = %s::chatbot.assunto WHERE id_conversa = %s;
    """, (assunto, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar assunto.")


def atualizar_nome_do_atendimento(id_conversa, nome_titular, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET nome_titular = %s WHERE id_conversa = %s;
    """, (nome_titular, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar nome.")


def atualizar_cpf_do_atendimento(id_conversa, cpf_titular, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET cpf_titular = %s WHERE id_conversa = %s;
    """, (cpf_titular, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar CPF.")


def registrar_contatos_encaminhados(id_conversa, telefone_moveis, telefone_sofas, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET encaminhado_moveis = %s, encaminhado_sofas = %s
        WHERE id_conversa = %s;
    """, (telefone_moveis, telefone_sofas, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar contatos.")
