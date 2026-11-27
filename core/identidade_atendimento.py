"""Resolução do cliente sob o lock de cada identificador apresentado pela Meta."""
from core.repositories.atendimento import conciliacao_cliente as conciliacao
from core.repositories.atendimento import identidade_cliente as repo


class IdentidadeDivergente(ValueError):
    pass


def resolver_cliente(dados, central, cursor):
    telefone, uid = dados.get("cliente_telefone"), dados.get("user_id_origem")
    chaves = ([f"wa:{telefone}"] if telefone else []) + ([f"bs:{central}:{uid}"] if uid else [])
    if not chaves:
        raise IdentidadeDivergente("Entrada sem identidade")
    for chave in sorted(chaves):
        repo.serializar_chave(chave,cursor)
    dono = repo.cliente_telefone(telefone,cursor) if telefone else None
    alias = repo.buscar_alias(central,uid,cursor) if uid else None
    if alias and (not alias[1] or (dono and alias[0] != dono)):
        raise IdentidadeDivergente("Identificadores conflitantes ou alias inativo")
    cliente = dono or (alias[0] if alias else None)
    if cliente is None:
        cliente = repo.criar_cliente(telefone,cursor)
    if uid and not alias:
        if repo.alias_vigente_do_cliente(central, cliente, cursor):
            raise IdentidadeDivergente("Cliente já possui outro BSUID vigente nesta central")
        repo.inserir_alias(central,uid,cliente,dados["id_hash_msg"],cursor)
        repo.conferir_alias(central,uid,cliente,cursor)
    if telefone and alias and not alias[2]:
        anterior = repo.dados_telefone(cliente,cursor)
        if anterior and anterior != telefone:
            raise IdentidadeDivergente("Mudança de telefone sem prova de continuidade")
        if anterior is None:
            repo.definir_telefone(cliente,telefone,cursor)
    repo.atualizar_username(cliente,dados.get("username_origem"),dados["received_data_hora"],cursor)
    return cliente


def rotacionar_bsuid(central, sistema, wamid, cursor):
    anterior, novo = sistema.get("previous_user_id"), sistema.get("user_id")
    if not anterior or not novo or anterior == novo:
        return False
    for uid in sorted((anterior,novo)):
        repo.serializar_chave(f"bs:{central}:{uid}",cursor)
    alias = repo.buscar_alias(central,anterior,cursor)
    if not alias or not alias[1]:
        return False
    if repo.buscar_alias(central,novo,cursor):
        raise IdentidadeDivergente("Novo identificador já vinculado")
    # Um telefone abandonado pode ser reatribuído a outra pessoa. A continuação
    # deste cadastro exige o identificador vinculado e um novo contato oficial.
    repo.preservar_bloqueio_na_rotacao(central, alias[0], novo, cursor)
    repo.definir_telefone(alias[0], None, cursor)
    repo.aposentadoria_alias(central,anterior,cursor)
    repo.inserir_alias(central,novo,alias[0],wamid,cursor)
    repo.suspender_alias(central,novo,cursor)
    repo.trocar_bsuid_pendente(central,anterior,novo,cursor)
    return True

def conciliar_contato_comprovado(dados, provisoria, canonica, uid, cursor):
    """Turnos e identificadores estão serializados pelo ingresso. Preserva a conversa original."""
    central = dados["id_central"]
    if repo.alias_vigente_do_cliente(central, canonica, cursor):
        return False
    origem = conciliacao.localizar_conversa_provisoria(central, provisoria, uid, cursor)
    if not origem:
        return False
    conversa, chat_provisorio = origem
    chat = conciliacao.obter_chat_canonico(canonica, central, cursor)
    if conciliacao.tem_conversa_ativa(chat, cursor):
        return False
    # Um turno no chat antigo pode ter acabado entre a primeira consulta e este lock.
    telefone = dados["interativo"]["_telefone_verificado"]
    if repo.impedimento(central, canonica, [telefone, uid], cursor):
        return False
    conciliacao.mover_conversa(conversa, chat, cursor)
    conciliacao.mover_alias(provisoria, canonica, central, uid, cursor)
    conciliacao.mover_fila(provisoria, canonica, cursor)
    conciliacao.atualizar_cadastro_pela_conversa(conversa, provisoria, canonica, cursor)
    conciliacao.excluir_chat_provisorio(chat_provisorio, provisoria, cursor)
    conciliacao.excluir_cliente_provisorio(provisoria, cursor)
    return True
