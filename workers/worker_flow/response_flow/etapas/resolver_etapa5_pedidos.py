"""Coleta os pedidos do varejo e apresenta a pergunta definida no mapa de transição."""
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa5_pedidos import enviar_etapa5_pedidos
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa6_detalhes import enviar_etapa6_detalhes
from core.validacoes.pedidos_pos_venda import transicao_dos_pedidos
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_pedidos_etapa5 import validar_contexto_pedidos
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa5_pedidos(contexto):
    mensagem = contexto["mensagem_cliente_atual"]
    destinatario, remetente = contexto.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]
    if contexto.get("apresentacao_pendente"):
        return enviar_etapa5_pedidos(destinatario, remetente)
    tratamento = resolver_tratamento_universal(contexto)
    if tratamento is not None:
        return tratamento
    numeros, quantidade_informada = validar_contexto_pedidos(contexto)
    if numeros is None:
        return repetir_etapa(contexto, enviar_etapa5_pedidos, destinatario, remetente, quantidade_para_correcao=quantidade_informada)
    evento, esperado = transicao_dos_pedidos(contexto["assunto"], perdeu_nota=not numeros)
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={esperado})
    envio = enviar_etapa6_detalhes(destinatario, remetente)
    envio["numeros_pedido"] = numeros
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
