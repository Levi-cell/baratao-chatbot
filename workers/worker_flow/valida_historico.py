"""Carrega a etapa original da entrada e a resposta já confirmada, se houver."""
from core.repositories.atendimento.conversas import atualizar_conversa_mensagem_cliente
from core.repositories.atendimento.historico import inserir_historico_mensagem_cliente, buscar_resposta_bot_por_mensagem_cliente
from core.repositories.fluxo.transicoes import listar_transicoes_permitidas
from core.repositories.fluxo.contextos.pos_venda import buscar_contexto_pos_venda


def valida_historico(mensagem, contexto_banco, cursor):
    conversa = contexto_banco["conversa"]
    id_conversa = conversa["id_conversa"]
    id_hist, recebido, etapa, inserido = inserir_historico_mensagem_cliente(
        mensagem, id_conversa, conversa["id_etapa_atual"], cursor)
    resposta = buscar_resposta_bot_por_mensagem_cliente(id_conversa, mensagem["id_mensagem"], mensagem["id_hash"], cursor)
    if inserido and not resposta:
        atualizar_conversa_mensagem_cliente(id_conversa, recebido, cursor)
    contexto_pos_venda = buscar_contexto_pos_venda(id_conversa, cursor)
    return {
        **contexto_banco, "id_conversa": id_conversa, "id_etapa_atual": conversa["id_etapa_atual"],
        "id_etapa_cliente": etapa, "id_etapa_origem_transicao": etapa, "id_etapa_resposta": etapa,
        "mensagem_cliente_inserida": inserido, "retry_count": mensagem["retry_count"],
        "turnos_sem_avanco": conversa["turnos_sem_avanco"],
        "lock_version": conversa["lock_version"],
        "transicoes_permitidas": listar_transicoes_permitidas(etapa, cursor),
        "resposta_bot_para_mensagem_atual": resposta,
        **contexto_pos_venda,
        "telefone_compartilhado_apto": (mensagem.get("estrutura_compartilhamento") or {}).get("_telefone_verificado"),
        "mensagem_cliente_atual": {
            **mensagem, "id_mensagem": id_hist, "id_mensagem_fila": mensagem["id_mensagem"],
            "id_hash_msg": mensagem["id_hash"], "id_etapa": etapa, "received_data_hora": recebido,
        },
    }
