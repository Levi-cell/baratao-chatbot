"""Operações SQL isoladas; conexão e transação pertencem ao chamador.

Extração organizacional: preserva os nomes do esquema usados pelo consumidor.
"""


def consultar_versao_postgresql(cursor):
    cursor.execute("SELECT version();")
    return cursor.fetchone()
