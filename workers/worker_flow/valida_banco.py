"""Resolve cliente, central e conversa sem enviar mensagens."""
from core.cache.runtime.cache_cliente import buscar_cliente_cache
from core.cache.cache_unidade import obter_id_unidade_redis_ou_plsql
from core.repositories.atendimento.clientes import inserindo_em_cliente_caso_seja_novo
from core.repositories.atendimento.chats import garantir_chat_para_atendimento
from core.repositories.atendimento.conversas import buscar_estado_conversa, inserindo_em_conversa_caso_seja_nova


from core.repositories.atendimento.fila import ler_identidade_fila


def valida_cliente(telefone, cursor):
    id_cliente = buscar_cliente_cache(telefone)
    if id_cliente:
        return id_cliente, False, False
    id_cliente, inserido = inserindo_em_cliente_caso_seja_novo(telefone, cursor)
    return id_cliente, inserido, True


def validar_banco_mensagem(mensagem, cursor):
    cadastro, uid, estrutura, central_da_fila = ler_identidade_fila(mensagem["id_mensagem"], cursor)
    id_central = obter_id_unidade_redis_ou_plsql(
        mensagem["id_phone_unidade"], cursor, central_da_fila=central_da_fila,
    )
    mensagem.update(user_id_origem=uid, estrutura_compartilhamento=estrutura)
    if cadastro:
        id_cliente, inserido, pendente = cadastro, False, True
    else:
        id_cliente, inserido, pendente = valida_cliente(mensagem["cliente_telefone"], cursor)
    # A linha do chat serializa a decisão abrir/retomar, mesmo antes do lock da conversa.
    garantir_chat_para_atendimento(id_cliente, id_central, cursor)
    conversa = buscar_estado_conversa(id_cliente, id_central, cursor)
    if not conversa or conversa["estado"] == "liberada":
        inserindo_em_conversa_caso_seja_nova(id_cliente, id_central, cursor)
        conversa = buscar_estado_conversa(id_cliente, id_central, cursor)
    return {
        "id_unidade": id_central, "id_central": id_central, "id_cliente": id_cliente,
        "cliente_telefone": mensagem["cliente_telefone"], "id_phone_unidade": mensagem["id_phone_unidade"],
        "bsuid_origem": uid, "cliente_inserido": inserido, "cliente_cache_pendente": pendente, "conversa": conversa,
    }
