"""Saudação na própria etapa 1, coleta de nome e encaminhamento universal."""

from core.etapas_pos_venda import ETAPA_CPF, ETAPA_PRODUTO, EVENTO_NOME_VALIDO_CPF_PRESENTE
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa1 import enviar_etapa1, enviar_nome_invalido
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa2 import enviar_etapa2
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa1 import validar_contexto_etapa1
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa1(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = mensagem["cliente_telefone"], mensagem["id_phone_unidade"]

    # Histórico confirmado diferencia saudação de resposta ao nome, sem etapa artificial.
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa1(destinatario, remetente)

    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa1(contexto_historico)
    if validacao is None:
        return enviar_nome_invalido(destinatario, remetente)

    evento = validacao["evento"]
    destino = ETAPA_PRODUTO if evento == EVENTO_NOME_VALIDO_CPF_PRESENTE else ETAPA_CPF
    resolver_destino_transicao(contexto_historico, evento, destinos_esperados={destino})
    sender = enviar_etapa3 if destino == ETAPA_PRODUTO else enviar_etapa2
    envio = sender(destinatario, remetente)
    envio["nome_titular"] = validacao["nome_titular"]
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
