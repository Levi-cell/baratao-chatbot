"""IDs do pós-venda. O mapa no PostgreSQL autoriza as transições.

A etapa 1 é saudação/coleta de nome; 3 é produto; 7 é encerramento.
Não há etapa técnica de abertura nem coleta de cidade.
"""

ETAPA_NOME = 1
ETAPA_CPF = 2
ETAPA_PRODUTO = 3
ETAPA_ASSUNTO = 4
ETAPA_PEDIDOS = 5
ETAPA_DETALHES = 6
ETAPA_ENCAMINHAMENTO = 7

EVENTO_SITUACAO_INFORMADA = "situacao_informada"

EVENTO_NOME_VALIDO_FALTA_CPF = "nome_valido_falta_cpf"
EVENTO_CPF_VALIDO = "cpf_valido"
EVENTO_PRODUTO_ESCOLHIDO = "produto_escolhido"
EVENTO_ASSUNTO_ESCOLHIDO = "assunto_escolhido"
EVENTO_PEDIDOS_ASSISTENCIA = "pedidos_assistencia"
EVENTO_PEDIDOS_DEMAIS_ASSUNTOS = "pedidos_demais_assuntos"
EVENTO_NOTA_PERDIDA_ASSISTENCIA = "nota_perdida_assistencia"
EVENTO_NOTA_PERDIDA_DEMAIS_ASSUNTOS = "nota_perdida_demais_assuntos"
EVENTO_MIDIA_RECEBIDA = "midia_recebida"
EVENTO_HUMANO_SOLICITADO = "humano_solicitado"
EVENTO_LIMITE_SEM_AVANCO = "limite_sem_avanco"

EVENTOS_ENCAMINHAMENTO = frozenset({
    EVENTO_MIDIA_RECEBIDA, EVENTO_HUMANO_SOLICITADO, EVENTO_LIMITE_SEM_AVANCO,
})
