"""Coleta do CPF e apresentação do produto, sem consulta ou coleta de cidade."""

from core.etapas_pos_venda import ETAPA_PRODUTO
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa2 import (
    enviar_cpf_invalido, enviar_etapa2,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa2 import validar_contexto_etapa2
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa2(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = mensagem["cliente_telefone"], mensagem["id_phone_unidade"]
    # Cadastro parcial: uma nova conversa pergunta o CPF antes de interpretar sua entrada.
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa2(
            destinatario, remetente,
            nome_titular=(contexto_historico.get("cadastro") or {}).get("nome_titular"),
        )
    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa2(contexto_historico)
    if validacao is None:
        return enviar_cpf_invalido(destinatario, remetente)

    evento = validacao["evento"]
    destino = resolver_destino_transicao(
        contexto_historico, evento, destinos_esperados={ETAPA_PRODUTO},
    )
    envio = enviar_etapa3(destinatario, remetente)
    envio["cpf_titular"] = validacao["cpf_titular"]
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
