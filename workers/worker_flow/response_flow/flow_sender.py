"""Despacho das etapas de pós-venda já portadas, com barreira de replay."""
from core.etapas_pos_venda import ETAPA_NOME, ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS
from workers.worker_flow.response_flow.etapas.resolver_etapa1 import resolve_etapa1
from workers.worker_flow.response_flow.etapas.resolver_etapa2 import resolve_etapa2
from workers.worker_flow.response_flow.etapas.resolver_etapa3 import resolve_etapa3
from workers.worker_flow.response_flow.etapas.resolver_etapa4 import resolve_etapa4
from workers.worker_flow.response_flow.etapas.resolver_etapa6_pedidos import resolve_etapa6_pedidos


def flow_sender(contexto_historico):
    resposta = contexto_historico.get("resposta_bot_para_mensagem_atual")
    if resposta:
        if contexto_historico["id_etapa_atual"] != resposta["id_etapa"]:
            raise ValueError("Resposta confirmada não corresponde à etapa persistida.")
        evento = ((resposta.get("interativo") or {}).get("_fluxo") or {}).get("evento")
        return {
            "enviou": False, "resposta_ja_existia": True,
            "id_hash_msg_bot": resposta["id_hash_msg"], "id_etapa_resultante": resposta["id_etapa"],
            "evento_transicao": evento,
        }
    if contexto_historico["id_etapa_atual"] == ETAPA_NOME:
        return resolve_etapa1(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_CPF:
        return resolve_etapa2(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_PRODUTO:
        return resolve_etapa3(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_ASSUNTO:
        return resolve_etapa4(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_PEDIDOS:
        return resolve_etapa6_pedidos(contexto_historico)
    # Não despachar por engano as antigas etapas do Supera com os mesmos IDs.
    raise NotImplementedError(
        f"Etapa de pós-venda {contexto_historico['id_etapa_atual']} ainda não implementada."
    )
