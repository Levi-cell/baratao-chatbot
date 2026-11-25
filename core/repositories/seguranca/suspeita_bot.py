"""Contador de repetição do fluxo; não promove bloqueios na Meta."""
from core.validacoes.encaminhamento_pos_venda import LIMITE_TURNOS_SEM_AVANCO


def incrementar_turnos_sem_avanco(id_conversa, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa SET turnos_sem_avanco = LEAST(turnos_sem_avanco + 1, %s)
        WHERE id_conversa = %s AND status_ativa RETURNING turnos_sem_avanco;
    """, (LIMITE_TURNOS_SEM_AVANCO, id_conversa))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Conversa ausente ao incrementar turnos.")
    return row[0]


def resetar_turnos_sem_avanco(id_conversa, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa SET turnos_sem_avanco = 0
        WHERE id_conversa = %s AND status_ativa RETURNING turnos_sem_avanco;
    """, (id_conversa,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Conversa ausente ao zerar turnos.")
    return row[0]
