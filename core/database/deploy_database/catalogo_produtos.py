"""Carga inicial dos produtos do ERP na instalação e na migração da V0.5.0."""

import logging
from pathlib import Path

from core.database.deploy_database.transacao_deploy import transacao_deploy


RAIZ = Path(__file__).resolve().parents[3]
ARQUIVO_PRODUTOS = RAIZ / "catalogo_produtos.txt"
MIGRACAO = RAIZ / "deploy/migrations/20261127_catalogo_produtos.sql"
CABECALHO = "codigo_produto\tnome_produto\tcategoria"


def ler_produtos():
    """Lê o TXT tabulado preservando a grafia e os espaços dos nomes do ERP."""
    produtos = []
    with ARQUIVO_PRODUTOS.open(encoding="utf-8") as arquivo:
        if arquivo.readline().rstrip("\n") != CABECALHO:
            raise ValueError("Cabeçalho inválido no catálogo de produtos.")
        for numero_linha, linha in enumerate(arquivo, start=2):
            try:
                codigo, nome, categoria = linha.rstrip("\n").split("\t")
                produtos.append((int(codigo), nome, categoria))
            except ValueError as erro:
                raise ValueError(f"Produto inválido na linha {numero_linha}.") from erro
    if not produtos:
        raise ValueError("O arquivo de produtos está vazio.")
    return sorted(produtos)


def carregar_catalogo_produtos(cursor):
    produtos = ler_produtos()
    cursor.execute("LOCK TABLE chatbot.catalogo IN SHARE ROW EXCLUSIVE MODE")
    cursor.execute("SELECT EXISTS (SELECT FROM chatbot.catalogo)")
    if not cursor.fetchone()[0]:
        with cursor.copy(
            "COPY chatbot.catalogo (codigo_produto, nome_produto, categoria) FROM STDIN"
        ) as carga:
            for produto in produtos:
                carga.write_row(produto)

    # Uma reexecução aceita a mesma carga e preserva alterações de outra origem.
    cursor.execute("""
        SELECT codigo_produto, nome_produto, categoria
        FROM chatbot.catalogo ORDER BY codigo_produto
    """)
    if cursor.fetchall() != produtos:
        raise ValueError("O catálogo no banco diverge do TXT. Carga interrompida.")
    return len(produtos)


def migrar_catalogo_produtos():
    logger = logging.getLogger("db.deploy_database")
    with transacao_deploy("migrar_catalogo_produtos", logger) as cursor:
        cursor.execute("SET LOCAL lock_timeout = '8s'")
        cursor.execute("SELECT pg_advisory_xact_lock(81024, 1)")
        cursor.execute(MIGRACAO.read_text(encoding="utf-8"))
        total = carregar_catalogo_produtos(cursor)
    print(f"Catálogo conferido e transação confirmada: {total} produtos.")


if __name__ == "__main__":
    migrar_catalogo_produtos()
