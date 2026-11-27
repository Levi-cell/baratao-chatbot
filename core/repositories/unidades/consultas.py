import logging


logger = logging.getLogger("db.unidades.consultas")


class UnidadeDesativada(Exception):
    """Suspensão administrativa; não é falha nem motivo para apagar a fila."""


def unidade_habilitada(id_unidade, cursor):
    """Leitura atual para lotes já carregados antes de uma desativação."""
    cursor.execute(
        "SELECT ativa IS TRUE FROM chatbot.central_pos_venda WHERE id_central = %s",
        (id_unidade,),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def exigir_unidade_habilitada_por_phone_id(phone_number_id, cursor):
    """Retorna o ID ativo, None para ausente e sinaliza a suspensão ao worker."""
    cursor.execute(
        "SELECT id_central, ativa FROM chatbot.central_pos_venda WHERE phone_number_id = %s",
        (phone_number_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if not row[1]:
        raise UnidadeDesativada("Central de pós-venda desativada")
    return row[0]


def pegar_unidades(cursor):
    cursor.execute("""
        SELECT phone_number_id, id_central
        FROM chatbot.central_pos_venda
        WHERE ativa = TRUE
    """)

    resultado = {row[0]: row[1] for row in cursor.fetchall()}

    logger.debug("unidades_consultadas | total=%s", len(resultado))

    return resultado


def buscar_id_unidade_por_phone_id(phone_number_id, cursor):
    cursor.execute("""
        SELECT id_central
        FROM chatbot.central_pos_venda
        WHERE phone_number_id = %s
          AND ativa = TRUE
    """, (phone_number_id,))

    resultado = cursor.fetchone()
    logger.debug(
        "unidade_consulta | acao=buscar_por_phone phone_number_id=%s encontrada=%s",
        phone_number_id,
        bool(resultado),
    )
    return resultado[0] if resultado else None


def buscar_id_registro_meta(phone_number_id, cursor):
    """Seleciona o recurso para registrar ou desregistrar o número comercial."""
    cursor.execute("""
        SELECT COALESCE(waac_id, phone_number_id)
        FROM chatbot.central_pos_venda WHERE phone_number_id=%s
    """, (phone_number_id,))
    linha = cursor.fetchone()
    return linha[0] if linha else phone_number_id
