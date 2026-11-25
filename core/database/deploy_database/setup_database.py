"""Carga inicial da Baratão em um schema chatbot já preparado pelo Django."""

import logging
from pathlib import Path

from core.database.deploy_database.transacao_deploy import transacao_deploy


logger = logging.getLogger("db.deploy_database")
PASTA = Path(__file__).resolve().parent


def setup_database_aws():
    with transacao_deploy("instalar_baratao", logger) as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(81024, 1)")
        cursor.execute("""
            SELECT to_regclass('chatbot.auth_user'),
                   to_regclass('chatbot.unidade'),
                   to_regclass('chatbot.central_pos_venda')
        """)
        usuarios, legado, central = cursor.fetchone()
        if not usuarios:
            raise RuntimeError("Prepare o auth_user do Django no schema chatbot antes do setup.")
        if legado:
            raise RuntimeError("Banco do Supera. Use a migração 20261116_baratao_pos_venda.sql.")
        if central:
            raise RuntimeError("A central já existe. Este setup é exclusivo para a instalação inicial.")

        for arquivo in ("schema.sql", "catalogo.sql"):
            cursor.execute((PASTA / arquivo).read_text(encoding="utf-8"))
    logger.info("banco_baratao_instalado")


if __name__ == "__main__":
    setup_database_aws()

