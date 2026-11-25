"""Políticas de encerramento e bloqueio temporário por cliente/central."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PoliticaEtapa:
    id_etapa: int
    encerra_automaticamente: bool
    bloqueio_dias: int


@dataclass(frozen=True)
class BloqueioConversa:
    finalizou_em: datetime
    bloqueio_dias: int


def buscar_politica_etapa(id_etapa, cursor):
    cursor.execute("""
        SELECT id_etapa, encerra_automaticamente, bloqueio_dias
        FROM chatbot.etapa WHERE id_etapa = %s;
    """, (id_etapa,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Política da etapa {id_etapa} não encontrada")
    return PoliticaEtapa(*row)


def buscar_bloqueio_conversa_por_id(id_conversa, cursor):
    cursor.execute("""
        SELECT c.finalizou_em, e.bloqueio_dias
        FROM chatbot.conversa c JOIN chatbot.etapa e ON e.id_etapa = c.id_etapa_atual
        WHERE c.id_conversa = %s AND NOT c.status_ativa
          AND c.finalizou_em IS NOT NULL AND e.bloqueio_dias > 0;
    """, (id_conversa,))
    return _montar_bloqueio(cursor.fetchone())


def buscar_bloqueio_ativo_por_cliente_unidade(cliente_telefone, id_phone_unidade, cursor):
    # Nome da função preservado para os pontos de entrada do webhook/cache.
    cursor.execute("""
        SELECT c.finalizou_em, e.bloqueio_dias
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat = c.id_chat
        JOIN chatbot.cliente cl ON cl.id_cliente = ch.id_cliente
        JOIN chatbot.central_pos_venda b ON b.id_central = c.id_central
        JOIN chatbot.etapa e ON e.id_etapa = c.id_etapa_atual
        WHERE cl.waid_telefone = %s AND b.phone_number_id = %s
          AND NOT c.status_ativa AND e.bloqueio_dias > 0
          AND c.finalizou_em > CURRENT_TIMESTAMP - e.bloqueio_dias * INTERVAL '1 day'
        ORDER BY c.finalizou_em DESC LIMIT 1;
    """, (cliente_telefone, id_phone_unidade))
    return _montar_bloqueio(cursor.fetchone())


def _montar_bloqueio(row):
    return BloqueioConversa(*row) if row else None
