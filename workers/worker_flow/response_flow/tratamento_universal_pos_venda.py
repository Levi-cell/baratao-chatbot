"""O mesmo encaminhamento atende às etapas já adaptadas do pós-venda."""

from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO
from core.validacoes.encaminhamento_pos_venda import motivo_encaminhamento
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolver_tratamento_universal(contexto):
    evento = motivo_encaminhamento(contexto)
    if evento is None:
        return None
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento(contexto, evento)
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
