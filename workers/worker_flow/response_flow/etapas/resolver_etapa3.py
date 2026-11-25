"""Produto: apresentação, tratamento universal, correção e avanço para assunto."""
from core.etapas_pos_venda import ETAPA_ASSUNTO
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa4 import enviar_etapa4
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa3 import validar_contexto_etapa3
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa3(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = mensagem["cliente_telefone"], mensagem["id_phone_unidade"]
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa3(
            destinatario, remetente,
            nome_titular=(contexto_historico.get("cadastro") or {}).get("nome_titular"),
        )
    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa3(contexto_historico)
    if validacao is None:
        return enviar_etapa3(destinatario, remetente, invalido=True)
    evento = validacao["evento"]
    destino = resolver_destino_transicao(contexto_historico, evento, destinos_esperados={ETAPA_ASSUNTO})
    envio = enviar_etapa4(destinatario, remetente)
    envio["produto"] = validacao["produto"]
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
