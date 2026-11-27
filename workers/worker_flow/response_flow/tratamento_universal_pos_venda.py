"""Encaminha por solicitação ou no quarto turno que de fato repetiria a etapa."""
from core.etapas_pos_venda import (
    ETAPA_ENCAMINHAMENTO, EVENTO_HUMANO_SOLICITADO, EVENTO_LIMITE_SEM_AVANCO,
)
from core.validacoes.encaminhamento_pos_venda import (
    LIMITE_TURNOS_SEM_AVANCO, entrada_nao_suportada, pediu_humano,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from core.integrations.whatsapp.pywa_functions.pywa_senders.repeticao_midia import enviar_repeticao_midia
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def _encaminhar(contexto, evento):
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento(contexto, evento)
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)


def repetir_etapa(contexto, sender, *args, **kwargs):
    if int(contexto.get("turnos_sem_avanco") or 0) >= LIMITE_TURNOS_SEM_AVANCO:
        return _encaminhar(contexto, EVENTO_LIMITE_SEM_AVANCO)
    return sender(*args, **kwargs)


def resolver_tratamento_universal(contexto):
    entrada = contexto["mensagem_cliente_atual"]
    tipo = entrada.get("tipo_mensagem")
    if pediu_humano(tipo, entrada.get("conteudo_texto")):
        return _encaminhar(contexto, EVENTO_HUMANO_SOLICITADO)
    etapa = contexto["id_etapa_atual"]
    if entrada_nao_suportada(etapa, tipo):
        return repetir_etapa(contexto, enviar_repeticao_midia, contexto["destinatario_envio"],
                             entrada["id_phone_unidade"], etapa)
    return None
