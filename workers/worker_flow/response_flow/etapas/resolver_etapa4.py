"""Assunto do atendimento: repetir a lista, encaminhar ou apresentar os pedidos."""
from core.etapas_pos_venda import ETAPA_PEDIDOS
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa4 import enviar_etapa4
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa5_pedidos import enviar_etapa5_pedidos
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa4 import validar_contexto_etapa4
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    anexar_transicao_ao_contexto_envio, resolver_destino_transicao,
)


def resolve_etapa4(contexto):
    mensagem = contexto["mensagem_cliente_atual"]
    destinatario, remetente = contexto.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]
    if contexto.get("apresentacao_pendente"):
        return enviar_etapa4(destinatario, remetente)
    tratamento = resolver_tratamento_universal(contexto)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa4(contexto)
    if validacao is None:
        return repetir_etapa(contexto, enviar_etapa4, destinatario, remetente, invalido=True)
    evento = validacao["evento"]
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_PEDIDOS})
    envio = enviar_etapa5_pedidos(destinatario, remetente)
    envio["assunto"] = validacao["assunto"]
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
