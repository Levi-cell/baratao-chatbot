"""Efeitos de negócio por etapa de origem, após o envio confirmado.

O ciclo transacional permanece no flow_worker. Este módulo coordena chamadas
aos repositórios; não executa SQL, commit, rollback, HTTP ou escrita em cache.
"""

from core.etapas_pos_venda import (
    ETAPA_NOME, ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, EVENTO_PRODUTO_ESCOLHIDO,
    ETAPA_PEDIDOS, EVENTO_ASSUNTO_ESCOLHIDO,
    ETAPA_ENCAMINHAMENTO, EVENTO_NOME_VALIDO_FALTA_CPF,
    EVENTO_NOME_VALIDO_CPF_PRESENTE, EVENTO_CPF_VALIDO,
    EVENTOS_ENCAMINHAMENTO,
)
from core.repositories.atendimento.clientes import atualizar_nome_titular, atualizar_cpf_titular
from core.repositories.atendimento.pos_venda import (
    atualizar_nome_do_atendimento, atualizar_cpf_do_atendimento,
    registrar_contatos_encaminhados, atualizar_produto_do_atendimento,
    atualizar_assunto_do_atendimento,
)
from core.validacoes.assunto_pos_venda import ASSUNTOS
from core.validacoes.encaminhamento_pos_venda import setores_encaminhamento
from core.validacoes.produto_pos_venda import PRODUTOS
from core.validacoes.pedidos_pos_venda import pedidos_de_filiais_cadastradas, transicao_dos_pedidos
from core.repositories.atendimento.pedidos import inserir_pedidos_da_conversa, registrar_situacao_nota

_CAMPOS_EFEITO = frozenset({
    "nome_titular", "cpf_titular", "produto", "assunto", "encaminhado_moveis", "encaminhado_sofas",
    "numeros_pedido",
})


def _validar_campos_efeito(envio, permitidos):
    """Presença de chaves complementa a etapa/evento; não escolhe o efeito."""
    if (_CAMPOS_EFEITO & envio.keys()) != set(permitidos):
        raise ValueError("Dados de negócio incompatíveis com a etapa e o evento.")
    campos_textuais = permitidos - {"numeros_pedido"}
    if any(not isinstance(envio[chave], str) or not envio[chave].strip() for chave in campos_textuais):
        raise ValueError("Dado obrigatório ausente ao confirmar efeito da etapa.")


def _validar_destino(contexto, envio, destino_esperado):
    evento = envio.get("evento_transicao")
    if (
        envio["id_etapa_resultante"] != destino_esperado
        or (contexto.get("transicoes_permitidas") or {}).get(evento) != destino_esperado
        or envio.get("tratamento")
    ):
        raise ValueError("Efeito incompatível com a transição autorizada.")


def _registrar_encaminhamento(contexto, envio, cursor):
    """O efeito exige os contatos dos setores definidos para este atendimento."""
    _validar_destino(contexto, envio, ETAPA_ENCAMINHAMENTO)
    setores = setores_encaminhamento(contexto.get("produto"))
    _validar_campos_efeito(envio, {f"encaminhado_{setor}" for setor in setores})
    registrar_contatos_encaminhados(
        contexto["id_conversa"], envio.get("encaminhado_moveis"),
        envio.get("encaminhado_sofas"), cursor,
    )
    return {"encaminhado": True}


def atualizar_banco_conforme_transicao_de_etapa(contexto, envio, cursor):
    # Recuperação de resposta já confirmada não repete efeitos de negócio.
    if envio.get("resposta_ja_existia"):
        return {}

    etapa = contexto["id_etapa_origem_transicao"]
    evento = envio.get("evento_transicao")
    destino = envio["id_etapa_resultante"]
    if envio.get("id_etapa_origem_transicao", etapa) != etapa:
        raise ValueError("Origem do envio diferente da etapa da mensagem processada.")

    # NOME (1): repetição, encaminhamento universal ou nome confirmado → CPF.
    if etapa == ETAPA_NOME:
        if not evento and destino == ETAPA_NOME:
            _validar_campos_efeito(envio, set())
            # O contador comum é persistido em persistencia_resposta, uma única vez.
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento in {EVENTO_NOME_VALIDO_FALTA_CPF, EVENTO_NOME_VALIDO_CPF_PRESENTE}:
            esperado = ETAPA_CPF if evento == EVENTO_NOME_VALIDO_FALTA_CPF else ETAPA_PRODUTO
            _validar_destino(contexto, envio, esperado)
            _validar_campos_efeito(envio, {"nome_titular"})
            nome = envio["nome_titular"]
            atualizar_nome_titular(contexto["id_cliente"], nome, cursor)
            atualizar_nome_do_atendimento(contexto["id_conversa"], nome, cursor)
            return {"nome_titular": nome}

    # CPF (2): repetição, encaminhamento universal ou CPF confirmado → produto.
    elif etapa == ETAPA_CPF:
        if not evento and destino == ETAPA_CPF:
            _validar_campos_efeito(envio, set())
            # Não sobrescrever CPF global em resposta inválida nem duplicar o contador.
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_CPF_VALIDO:
            _validar_destino(contexto, envio, ETAPA_PRODUTO)
            _validar_campos_efeito(envio, {"cpf_titular"})
            cpf = envio["cpf_titular"]
            if len(cpf) != 11 or not cpf.isascii() or not cpf.isdigit():
                raise ValueError("O efeito de CPF exige 11 dígitos ASCII já normalizados.")
            atualizar_cpf_titular(contexto["id_cliente"], cpf, cursor)
            atualizar_cpf_do_atendimento(contexto["id_conversa"], cpf, cursor)
            return {"cpf_titular": cpf}

    # PRODUTO (3): pertence ao atendimento atual, nunca ao cadastro global.
    elif etapa == ETAPA_PRODUTO:
        if not evento and destino == ETAPA_PRODUTO:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_PRODUTO_ESCOLHIDO:
            _validar_destino(contexto, envio, ETAPA_ASSUNTO)
            _validar_campos_efeito(envio, {"produto"})
            produto = envio["produto"]
            if produto not in PRODUTOS:
                raise ValueError("Produto inválido ao confirmar escolha.")
            atualizar_produto_do_atendimento(contexto["id_conversa"], produto, cursor)
            return {"produto": produto}

    # ASSUNTO (4): a escolha pertence à mesma conversa que o produto.
    elif etapa == ETAPA_ASSUNTO:
        if not evento and destino == ETAPA_ASSUNTO:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_ASSUNTO_ESCOLHIDO:
            _validar_destino(contexto, envio, ETAPA_PEDIDOS)
            _validar_campos_efeito(envio, {"assunto"})
            assunto = envio["assunto"]
            if assunto not in ASSUNTOS:
                raise ValueError("Assunto inválido ao confirmar escolha.")
            atualizar_assunto_do_atendimento(contexto["id_conversa"], assunto, cursor)
            return {"assunto": assunto}

    # PEDIDOS (6): o vínculo com a filial pertence a cada número desta conversa.
    elif etapa == ETAPA_PEDIDOS:
        if not evento and destino == ETAPA_PEDIDOS:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        _validar_campos_efeito(envio, {"numeros_pedido"})
        numeros = envio["numeros_pedido"]
        if not isinstance(numeros, list):
            raise ValueError("O efeito de pedidos exige a lista de números confirmados.")
        perdeu_nota = not numeros
        esperado, destino_esperado = transicao_dos_pedidos(contexto["assunto"], perdeu_nota=perdeu_nota)
        if evento != esperado:
            raise ValueError("Evento de pedidos incompatível com o assunto ou a opção de nota perdida.")
        _validar_destino(contexto, envio, destino_esperado)
        if numeros:
            if not pedidos_de_filiais_cadastradas(numeros, contexto["codigos_filiais"]):
                raise ValueError("Pedido ou filial inválidos ao confirmar o atendimento.")
            inserir_pedidos_da_conversa(contexto["id_conversa"], numeros, cursor)
        registrar_situacao_nota(contexto["id_conversa"], perdeu_nota, cursor)
        return {"perdeu_nota": perdeu_nota}

    raise ValueError(
        f"Efeito não implementado para etapa={etapa}, evento={evento}, destino={destino}."
    )
