import logging

from core.database.connection_aws import get_conn
from core.repositories.infraestrutura.conexao import consultar_versao_postgresql


logger = logging.getLogger("db.connection_test")


def connection_teste_psql():
    conn = None

    try:
        conn = get_conn(application_name="script_chatbot")
        cursor = conn.cursor()

        version = consultar_versao_postgresql(cursor)

        logger.info(
            "banco_conexao_ok | acao=healthcheck versao=%s",
            version[0] if version else "-",
        )

    except Exception as erro:
        logger.exception("banco_conexao_erro | acao=healthcheck erro=%s", erro)
        raise

    finally:
        if conn:
            conn.close()

