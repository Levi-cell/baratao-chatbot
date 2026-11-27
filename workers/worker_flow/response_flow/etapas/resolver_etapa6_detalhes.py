"""Coleta o relato e encaminha o atendimento para os setores escolhidos."""
from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO, EVENTO_SITUACAO_INFORMADA
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa6_detalhes import enviar_etapa6_detalhes
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_detalhes_etapa6 import validar_contexto_detalhes
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa6_detalhes(contexto):
    entrada = contexto["mensagem_cliente_atual"]
    telefone = contexto.get("destinatario_envio", entrada.get("cliente_telefone"))
    central = entrada["id_phone_unidade"]
    if contexto.get("apresentacao_pendente"):
        return enviar_etapa6_detalhes(telefone, central)
    tratamento = resolver_tratamento_universal(contexto)
    if tratamento is not None:
        return tratamento
    detalhes = validar_contexto_detalhes(contexto)
    if not detalhes:
        return enviar_etapa6_detalhes(telefone, central, repetir=True)
    evento = EVENTO_SITUACAO_INFORMADA
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento({**contexto, "detalhes": detalhes}, evento)
    envio["detalhes"] = detalhes
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
