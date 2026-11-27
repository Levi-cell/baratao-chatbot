from core.repositories.atendimento.conversas import encerrar_conversa
from core.repositories.fluxo.politicas import buscar_politica_etapa

MOTIVOS_EVENTO = {
    "midia_recebida": "encaminhamento_midia",
    "humano_solicitado": "encaminhamento_humano",
    "limite_sem_avanco": "encaminhamento_sem_avanco",
}


def resolver_intencao_encerramento(contexto_historico, contexto_envio, cursor):
    etapa = contexto_envio["id_etapa_resultante"]
    politica = buscar_politica_etapa(etapa, cursor)
    if not politica.encerra_automaticamente:
        return None
    # Pode haver uma resposta terminal confirmada antes da migração e ainda na fila.
    if contexto_envio.get("resposta_ja_existia") and contexto_envio.get("evento_transicao") == "loja_nao_visitada":
        return {"motivo_encerramento": "visita_pendente", "bloqueio_dias": 0}
    motivo = MOTIVOS_EVENTO.get(
        contexto_envio.get("evento_transicao"), "encaminhamento")
    return {"motivo_encerramento": motivo, "bloqueio_dias": politica.bloqueio_dias}


def aplicar_encerramento_se_necessario(id_conversa, intencao, cursor):
    if not intencao:
        return {"atendimento_encerrado": False}
    finalizou = encerrar_conversa(id_conversa, intencao["motivo_encerramento"], cursor)
    return {"atendimento_encerrado": True, "finalizou_em": finalizou,
            "bloqueio_dias": intencao["bloqueio_dias"]}
