from core.repositories.atendimento.conversas import (
    atualizar_conversa_por_transicao, atualizar_conversa_resposta_bot_sem_avancar,
)

MOVIMENTO_TRANSICAO = "transicao"
MOVIMENTO_SEM_AVANCO = "sem_avanco"
MOVIMENTO_RECUPERACAO = "recuperacao"


def persistir_movimento_conversa(contexto, envio, data_bot, cursor):
    if envio.get("resposta_ja_existia"):
        return MOVIMENTO_RECUPERACAO
    destino = envio["id_etapa_resultante"]
    origem = contexto["id_etapa_origem_transicao"]
    evento = envio.get("evento_transicao")
    if evento:
        if envio.get("tratamento"):
            raise ValueError("Repetição da pergunta não pode avançar de etapa.")
        atualizar_conversa_por_transicao(contexto["id_conversa"], origem, evento, destino, data_bot, cursor)
        return MOVIMENTO_TRANSICAO
    if destino != origem:
        raise ValueError("Mudança de etapa sem transição autorizada.")
    atualizar_conversa_resposta_bot_sem_avancar(contexto["id_conversa"], data_bot, cursor)
    return MOVIMENTO_SEM_AVANCO
