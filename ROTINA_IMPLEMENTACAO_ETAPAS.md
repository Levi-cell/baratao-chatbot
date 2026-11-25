# Rotina de implementação de novas etapas

Este padrão continua válido na passagem do Supera para a Baratão. O negócio,
os textos e o mapa mudam; a organização por responsabilidade e o ciclo
transacional permanecem. Regras do pós-venda: [baratão moveis.md](<baratão moveis.md>).
Fronteiras gerais: [PADROES_DE_ARQUITETURA.md](PADROES_DE_ARQUITETURA.md).

## Contrato de cada camada

| Camada | Arquivo ou pasta | Responsabilidade |
| --- | --- | --- |
| Mensagem | `core/integrations/whatsapp/messages/etapaN_messages.py` | Textos, quebras de linha, rótulos e composição do conteúdo. |
| Sender | `core/integrations/whatsapp/pywa_functions/pywa_senders/etapaN.py` | Enviar a mensagem pronta, obter WAMID e devolver o resultado técnico. |
| Validador contextual | `workers/worker_flow/response_flow/etapas/validadores_contexto/valida_etapaN.py` | Interpretar a resposta e produzir evento e dados válidos. |
| Validação pura | `core/validacoes/` | Extração e normalização reutilizáveis, sem I/O. |
| Resolver | `workers/worker_flow/response_flow/etapas/resolver_etapaN.py` | Priorizar tratamentos, chamar o validador, conferir o mapa e chamar o sender adequado. |
| Efeitos | `workers/worker_flow/transacoes/efeitos_transicao.py` | Escolher explicitamente, por etapa de origem e evento, quais dados serão persistidos. |
| SQL | `core/repositories/` | Executar consultas e alterações parametrizadas em funções por funcionalidade, recebendo cursor. |
| Ciclo transacional | `workers/worker_flow/response_flow/flow_worker.py` | Coordenar fila, contexto, locks, envio, checkpoints, commits, rollbacks e recuperação. |

O sender de uma etapa apresenta a pergunta dessa etapa. Por exemplo, depois
de validar o CPF na etapa 2, o resolver 2 chama o sender 3 para perguntar o
produto. O texto e os botões ficam no arquivo de mensagens 3, não no de CPF.

A saudação é exceção intencional de validação: a primeira entrada recebe as
regras do canal antes de ser interpretada. A etapa 1 apresenta
a saudação e depois aguarda o nome. O histórico confirmado identifica se a
apresentação está pendente, sem estado artificial de abertura. A etapa 11 é
encerramento com bloqueio interno de 90 dias.

## 1. Definir regra e mapa

Registrar pergunta, respostas válidas, tratamentos, eventos, destinos e efeitos
no roteiro. Navegação depende de `origem + evento → destino`, nunca de
somar 1 ao ID da etapa.

Exemplos atuais:

```text
 1 + nome_valido_falta_cpf     → 2
 2 + cpf_valido               → 3
 1 ou 2 + humano_solicitado    → 11
```

Identificadores do fluxo portado ficam em `core/etapas_pos_venda.py`.
A autorização efetiva continua vindo de `chatbot.etapa_transicao`.
Constantes não substituem o mapa persistido.

Atualizar `core/database/deploy_database/catalogo.sql` quando o mapa mudar.
O DDL final em `schema.sql` contém apenas comandos de criação. Uma mudança
incremental necessária ao banco existente fica separada em
`deploy/migrations/`. Reorganização de Python sem mudança de esquema ou
catálogo não exige migração.

## 2. Implementar mensagem e sender

Concentrar texto e quebras de linha em `messages`. O sender serializa
texto, botões ou cartões, captura o WAMID e traduz falhas externas para
`ErroEnvioMeta`. Transporte compartilhado pode ser reutilizado.

O sender não interpreta CPF/nome, decide o próximo estado, executa SQL,
grava cache, faz commit ou marca a fila como `sent`. Um envio aceito pela
Meta não equivale, sozinho, a uma transição confirmada no PostgreSQL.

Tratamento universal tem módulo compartilhado de mensagens e sender, sem
ficar artificialmente pertencendo à etapa 1.

## 3. Implementar validador e resolver

O validador contextual usa o contexto já carregado. Extratores puros podem
ficar em `core/validacoes/`, sem banco, Redis, HTTP ou importação do worker.

Nas etapas 1, 2 e 3, após a apresentação, o resolver verifica primeiro mídia,
pedido contendo “humano” e limite de turnos; depois valida nome ou CPF.
Três repetições confirmadas levam ao encaminhamento na quarta entrada.
Um avanço válido anterior a esse limite zera o contador.

Resposta específica inválida repete a etapa, com `tratamento=True`, sem
evento de transição. O encaminhamento universal, apesar do nome
“tratamento”, produz uma transição real para 11; ele não pode carregar a
flag de repetição `tratamento=True`.

Antes do HTTP, o resolver consulta o mapa carregado, verifica o destino
esperado e só então chama o sender. Depois anexa origem, evento, destino e
dados validados ao resultado técnico do envio.

Na etapa 3, os tipos interativos de botão seguem o validador específico, que só aceita as três opções. Resposta interativa desconhecida repete a pergunta; mídia segue o universal. Nas próximas etapas, fazer a distinção correspondente para suas listas/botões.

## 4. Implementar efeitos explicitamente por etapa

Em `atualizar_banco_conforme_transicao_de_etapa`, manter blocos explícitos:

```python
if etapa == ETAPA_NOME:
    # repetição, encaminhamento ou nome válido
    ...
elif etapa == ETAPA_CPF:
    # repetição, encaminhamento ou CPF válido
    ...
```

Dentro de cada bloco, conferir evento, destino e dados esperados. Verificar
a presença de uma chave complementa esse contrato; nunca usar apenas
`if "cpf_titular" in envio` como autorização para gravar o CPF.

Os efeitos chamam funções dos repositórios. Nome/CPF global e cópia do
atendimento são gravados na mesma transação do histórico e da mudança de
etapa. Ausência do registro esperado gera erro para o worker reverter.

Repetições não sobrescrevem cadastro. A contagem comum permanece em
`persistencia_resposta.py`: não adicionar outro incremento nos efeitos
específicos. Recuperação de resposta já confirmada não reaplica esses
efeitos nem conta novo turno.

## 5. Preservar o ciclo e a recuperação

O arquivo principal `flow_worker.py` é o mapa do processamento. Não mover
commits ou rollbacks para resolvers, senders, validadores ou repositórios.
O webhook possui seu próprio ponto de controle transacional; isso não
transfere a ele transações do worker.

Preservar reserva da fila, lock de conversa com versão, tratamento de
exceções externas e checkpoints. Os estados usuais são
`pending → processing → sent`; retries podem reagendar o item conforme
o tratamento existente. `sent` indica conclusão do processamento da fila,
não leitura pelo cliente.

Há dois momentos distintos depois do envio:

1. Confirmar histórico da resposta, dados e avanço/repetição.
2. Concluir a fila e aplicar encerramento quando necessário.

Se o processo cair entre esses commits, a resposta persistida permite
concluir o segundo momento sem novo envio nem novos efeitos. Se a Meta
aceitar a mensagem e o processo cair antes de confirmar o primeiro commit,
o banco pode não ter evidência suficiente: existe risco de duplicação.
Não prometer envio exatamente uma vez nem introduzir recuperação especial
por mensagem/cartão sem uma decisão explícita.

`movimento_conversa.py` distingue transição, repetição e recuperação.
A reorganização de 21/11/2026 não alterou esse módulo, o principal, os
tratadores de erros externos, os locks ou o contrato da fila.

## 6. Validar a mudança

- Conferir texto exato, quebras de linha, botões e destino antes do envio.
- Testar respostas válidas/invalidas e prioridade do tratamento universal.
- Confirmar efeitos somente na etapa/evento corretos e repetição sem escrita indevida.
- Testar falha da Meta, rollback antes do commit e replay após checkpoint.
- Testar concorrência/lock quando a alteração atingir essa responsabilidade.
- Usar PostgreSQL local descartável para a suíte de integração; nunca produção.
- Conferir que SQL executável ficou em funções de `core/repositories/`.
- Registrar entrega e pendências no roteiro e os resultados em `tests/README.md`.

## Estado atual

Etapas 1, 2 e 3 implementadas, incluindo abertura conforme cadastro e tratamento universal. A etapa 3 salva produto no atendimento 1:1 e avança para 4, apresentando a lista de assuntos. A resposta de assunto e as etapas posteriores ainda não estão implementadas. Não se pergunta cidade. IDs 5 e 10 sem uso; encerramento em 11. O dispatcher não chama etapas antigas do Supera por coincidência de ID.

Consumo Meta continua como worker independente a preservar. Seus consumidores ainda precisam ser adaptados às tabelas de central e consumo do varejo antes da ativação; essa adaptação não pertence aos resolvers de atendimento.
