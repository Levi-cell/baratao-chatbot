"""Leituras limitadas à central autenticada; nunca consultam a Meta."""

from .painel import _linha, _linhas


def buscar_central(cursor, id_central):
    cursor.execute("""
        SELECT u.id_central, u.nome AS nome_central, u.nome_fuso,
               c.ultimo_erro AS erro_conta, c.ultima_tentativa_em AS tentativa_conta
          FROM chatbot.central_pos_venda u
          LEFT JOIN chatbot.consumo_meta_coletas c
            ON c.id_central = u.id_central AND c.periodo = 'conta'
         WHERE u.id_central = %s
    """, (id_central,))
    return _linha(cursor)


def listar_meses(cursor, id_central):
    # Uma única leitura monta cartões, histórico e PDFs com os mesmos totais.
    cursor.execute("""
        SELECT m.*, c.ultimo_erro, c.ultima_tentativa_em
          FROM chatbot.consumo_mensal_meta m
          LEFT JOIN chatbot.consumo_meta_coletas c
            ON c.id_central = m.id_central AND c.periodo = TO_CHAR(m.mes_referencia, 'YYYY-MM')
         WHERE m.id_central = %s ORDER BY m.mes_referencia DESC
    """, (id_central,))
    return _linhas(cursor)


def buscar_falha_periodo(cursor, id_central, periodo):
    cursor.execute("""
        SELECT ultimo_erro, ultima_tentativa_em FROM chatbot.consumo_meta_coletas
         WHERE id_central = %s AND periodo = %s
    """, (id_central, periodo))
    return _linha(cursor)
