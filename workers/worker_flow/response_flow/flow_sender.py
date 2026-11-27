"""Despacho das etapas de pós-venda já portadas, com barreira de replay."""
from core.etapas_pos_venda import ETAPA_NOME, ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS, ETAPA_DETALHES
from core.integrations.whatsapp.remetente import usar_remetente_central
from workers.worker_flow.response_flow.etapas.resolver_etapa1 import resolve_etapa1
from workers.worker_flow.response_flow.etapas.resolver_etapa2 import resolve_etapa2
from workers.worker_flow.response_flow.etapas.resolver_etapa3 import resolve_etapa3
from workers.worker_flow.response_flow.etapas.resolver_etapa4 import resolve_etapa4
from workers.worker_flow.response_flow.etapas.resolver_etapa5_pedidos import resolve_etapa5_pedidos


from workers.worker_flow.response_flow.etapas.resolver_etapa6_detalhes import resolve_etapa6_detalhes
from core.validacoes.destinatario_whatsapp import escolher_destinatario
from workers.worker_flow.response_flow.etapas.resolver_compartilhamento import pedir, resolver_turno_contato


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
    with usar_remetente_central(
        contexto_historico["central"], contexto_historico["mensagem_cliente_atual"]["id_phone_unidade"],
    ):
        mensagem = contexto_historico["mensagem_cliente_atual"]
        telefone = contexto_historico.get("wa_id_confirmado", mensagem.get("cliente_telefone"))
        uid = contexto_historico.get("bsuid_vigente")
        pendencia = contexto_historico.get("solicitacao_contato")
        tipo, valor = escolher_destinatario(telefone, uid, pendencia)
        ctx = dict(contexto_historico, destinatario_envio=valor)
        if pendencia:
            envio = resolver_turno_contato(ctx)
        elif uid and not telefone and ctx["id_etapa_atual"] != ETAPA_NOME:
            envio = pedir(ctx, ctx["id_etapa_atual"], ctx["cadastro"].get("nome_titular"),
                          reconfirmar=ctx.get("reconfirmar_telefone",False))
        else:
            envio = _despachar_etapa(ctx)
        envio.setdefault("tipo_destinatario",tipo)
        envio.setdefault("valor_destinatario",valor)
        return envio


def _despachar_etapa(contexto_historico):
    if contexto_historico["id_etapa_atual"] == ETAPA_NOME:
        return resolve_etapa1(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_CPF:
        return resolve_etapa2(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_PRODUTO:
        return resolve_etapa3(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_ASSUNTO:
        return resolve_etapa4(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_PEDIDOS:
        return resolve_etapa5_pedidos(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_DETALHES:
        return resolve_etapa6_detalhes(contexto_historico)
    # Não despachar por engano as antigas etapas do Supera com os mesmos IDs.
    raise NotImplementedError(
        f"Etapa de pós-venda {contexto_historico['id_etapa_atual']} ainda não implementada."
    )
