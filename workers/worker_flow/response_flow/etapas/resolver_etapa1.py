"""Saudação na própria etapa 1, coleta de nome e encaminhamento universal."""

from core.etapas_pos_venda import ETAPA_CPF
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa1 import enviar_etapa1, enviar_nome_invalido
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa2 import enviar_etapa2
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa1 import validar_contexto_etapa1
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


from workers.worker_flow.response_flow.etapas.resolver_compartilhamento import pedir
from core.integrations.whatsapp.messages.compartilhamento_contato import primeiro_nome


def resolve_etapa1(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = contexto_historico.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]

    # Histórico confirmado diferencia saudação de resposta ao nome, sem etapa artificial.
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa1(destinatario, remetente)

    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa1(contexto_historico)
    if validacao is None:
        return repetir_etapa(contexto_historico, enviar_nome_invalido, destinatario, remetente)

    evento = validacao["evento"]
    destino = resolver_destino_transicao(contexto_historico, evento, destinos_esperados={ETAPA_CPF})
    nome = validacao["nome_titular"]
    uid = contexto_historico.get("bsuid_vigente")
    if uid and (not mensagem.get("cliente_telefone") or not contexto_historico.get("wa_id_confirmado")):
        envio = pedir(contexto_historico, destino, nome)
    else:
        envio = enviar_etapa2(destinatario, remetente, nome_titular=primeiro_nome(nome))
    envio["nome_titular"] = nome
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
