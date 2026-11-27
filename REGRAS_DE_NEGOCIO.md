# Regras de negócio do pós-venda Baratão

Toda nova conversa coleta o nome e o CPF do titular desta compra. Com apenas BSUID e sem telefone confirmado, há uma solicitação oficial de contato entre o nome e o CPF. Produto, assunto, pedidos e relato pertencem à conversa. [Roteiro](<baratão moveis.md>) · [Fluxograma de atendimento](docs/fluxograma_atendimento.md)

## Repetição de etapa e encerramento

Uma mídia após a saudação repete a pergunta com um aviso de texto. Botões e listas são reapresentados. Uma resposta inválida de conteúdo usa a correção própria da etapa. As duas respostas contam no mesmo limite de três repetições confirmadas. A quarta resposta consecutiva que também falhar encaminha. Uma resposta válida nessa oportcentral avança e zera o contador. Durante a solicitação oficial de telefone, a contagem é da própria pendência. Compartilhar corretamente resolve a pendência.

Um texto com “humano” após a apresentação encaminha imediatamente. Com o relato válido, o fluxo também encaminha. A confirmação do encerramento aplica bloqueio interno por 90 dias para o par cliente e central. Os bloqueios de segurança do webhook têm critérios próprios.

## 1. Um turno por vez

Para cada par `(identidade do cliente, central)`, o worker deve manter no máximo
uma mensagem aberta ainda sem resposta própria do bot. A decisão não depende
somente de `fila_mensagens.status`; ela combina filas abertas com a resposta do
bot especificamente vinculada a cada mensagem.

- A prioridade é determinada exclusivamente pela ordem de chegada, e não pelo
  tamanho, conteúdo ou aparente importância da mensagem.
- A primeira mensagem válida será persistida na fila.
- Enquanto essa primeira mensagem estiver `pending` ou `processing` e ainda não
  possuir sua própria resposta persistida do bot, qualquer mensagem posterior do
  mesmo cliente para a mesma central será descartada pelo webhook.
- A mensagem descartada não será inserida na fila nem no histórico. Para o banco,
  ela nunca existiu.
- Quando todas as filas `pending` ou `processing` já possuírem sua própria
  resposta do bot, o webhook poderá aceitar a primeira mensagem do próximo turno,
  mesmo que a limpeza da fila anterior ainda não tenha chegado ao commit de
  `fila_mensagens.status = 'sent'`.
- A decisão é serializada por `pg_advisory_xact_lock`, utilizando central e
  cliente como chaves.

Exemplo de comportamento esperado:

```text
cliente: oi
cliente: olá, quero solicitar determinada coisa
```

Nesse exemplo, `oi` chegou primeiro e é a única mensagem válida do turno. O bot
deverá responder somente a `oi`. A mensagem `olá, quero solicitar determinada
coisa` será descartada no webhook e não aparecerá na fila nem no histórico.

O objetivo não é escolher a mensagem mais completa ou mais útil. O objetivo é
garantir uma única entrada por turno e impedir que várias mensagens enviadas
antes da resposta do bot sejam interpretadas como etapas independentes.

### 1.1. Por que `fila_mensagens.status = 'sent'` não é a única fonte da decisão

`sent` continua sendo o estado terminal que confirma a conclusão administrativa
da fila. Porém, ele não é a única prova de que o turno funcional foi respondido.
A prova mais importante para recuperação é o histórico do bot vinculado à
mensagem específica por:

```text
id_conversa
id_mensagem_fila
id_hash_cliente_origem
```

Se a Meta confirmou o envio, o histórico do bot foi persistido e
`last_message_from` foi atualizado para `bot`, o cliente já recebeu a resposta.
O worker ainda pode cair antes do commit separado que altera a fila para `sent`.
Utilizar somente o status da fila faria o webhook descartar a resposta seguinte
do cliente durante essa janela, embora ela já pertença legitimamente ao próximo
turno.

O webhook atual usa o histórico específico do bot como prova de resposta. Ele não
libera uma mensagem apenas porque o `last_message_from` geral da conversa está
como `bot`; cada fila aberta precisa possuir sua própria resposta correspondente.

### 1.2. Recuperação detalhada entre resposta do bot e `sent`

#### Etapa 1 - A foi respondida, mas o worker caiu

```text
Fila A: processing
Histórico do cliente A: existe
Histórico do bot A: existe
last_message_from: bot
Lock da conversa: ocupado
```

O worker cai antes de marcar A como `sent`. A resposta já chegou ao WhatsApp do
cliente, mas A permanece `processing` por aproximadamente 2 minutos.

#### Etapa 2 - o cliente envia B

O webhook encontra A aberta, mas também encontra a resposta do bot vinculada
especificamente a A. B é a primeira mensagem do próximo turno e pode entrar:

```text
Fila A: processing, respondida
Fila B: pending, sem resposta
```

#### Etapa 3 - outro ciclo seleciona B

Antes de resolver a conversa ou tentar seu lock, o worker procura uma mensagem
anterior ainda aberta para o mesmo cliente e central. Como A continua
`processing`, B é devolvida para `pending` por 30 segundos. Essa espera não
consome tentativa de erro.

```text
Fila A: processing, respondida
Fila B: pending, sem resposta
```

#### Etapa 4 - o cliente envia C

O webhook examina individualmente todas as filas abertas:

| Fila | Status | Resposta própria do bot |
|---|---|---|
| A | `processing` | Sim |
| B | `pending` | Não |

Como B ainda não possui resposta própria:

```text
todas_abertas_respondidas = False
```

C é descartada e nunca entra no banco. O `last_message_from = 'bot'` deixado por
A não libera C, porque não existe histórico do bot vinculado especificamente a B.

#### Etapa 5 - B aguarda a recuperação de A

Enquanto A continuar aberta, cada claim de B repetirá a verificação de ordem e a
devolverá para `pending` por 30 segundos, sem tentar o lock da conversa:

```text
Fila A: processing, respondida
Fila B: pending, sem resposta
```

C e quaisquer mensagens posteriores continuarão bloqueadas por B.

#### Etapa 6 - A retorna após o timeout

Depois de aproximadamente 2 minutos:

1. A fica elegível novamente;
2. o lock antigo já expirou após 110 segundos;
3. outro worker adquire o lock;
4. encontra o histórico do bot vinculado a A;
5. não envia uma resposta duplicada;
6. marca A como `sent`;
7. libera o lock.

```text
Fila A: sent
Fila B: pending
```

#### Etapa 7 - B é processada

B já não encontra mensagem anterior aberta, resolve a conversa, adquire o lock e
segue normalmente. Se esse lock for recusado por outro motivo, B volta para
`pending` por 5 segundos, também sem consumir uma tentativa de erro.
Enquanto B não possuir sua própria resposta do bot, qualquer C será descartada.

Depois que a resposta de B for persistida, a primeira mensagem do próximo turno
poderá entrar, inclusive na pequena janela anterior ao commit de `sent` de B.

### 1.3. Limite prático de mensagens abertas

Na recuperação descrita, o sistema poderá manter temporariamente:

```text
1 mensagem antiga respondida, mas ainda processing
+
1 mensagem nova sem resposta
```

Isso não cria uma sequência ilimitada. Assim que B entra sem resposta própria,
C, D, E e todas as mensagens seguintes são descartadas pelo webhook. O advisory
lock do turno também impede que B e C sejam aceitas simultaneamente por uma
corrida entre requisições.

Implementação principal:

- `core/repositories/seguranca/turno_cliente.py`
- `callback/webhook/services/populating_fila_mensagens.py`

## 2. Idempotência na entrada do webhook

- `fila_mensagens.id_hash_msg` é único.
- A repetição do mesmo evento pela Meta não deve criar outra linha na fila.
- `ON CONFLICT DO NOTHING` é o comportamento esperado para o mesmo
  `id_hash_msg`.
- Uma mensagem nova possui outro hash e continua sujeita à regra de turno.

Ignorar um webhook duplicado não é bug.

## 3. Primeira mensagem do turno

A primeira mensagem válida deverá ser persistida na fila quando não existir outra
mensagem aberta sem resposta para o mesmo cliente e central.

É considerado bug quando a primeira mensagem, ou a única mensagem enviada no
turno, é ignorada sem que alguma regra explícita deste documento seja aplicável.

## 4. Estados e tentativas da fila

Estados utilizados:

- `pending`: aguardando processamento.
- `processing`: reservada por um worker.
- `sent`: processamento e resposta concluídos.
- `failed`: permitido pelo schema, mas não é o destino utilizado atualmente
  quando o limite de tentativas é atingido.

Regras do worker:

- O dequeue altera a mensagem para `processing` e incrementa `retry_count`.
- Uma mensagem `processing` abandonada poderá ser retomada depois de 2 minutos.
- Erros tratados reagendam a mensagem para 2 minutos depois, enquanto ainda
  houver tentativa disponível.
- O limite é de 3 tentativas de processamento.
- Ao identificar `retry_count >= 3`, a mensagem é excluída.
- Não existe uma quarta tentativa.

A exclusão ao atingir o limite de 3 tentativas é uma regra de negócio confirmada
do worker, e não um bug. Alterar esse comportamento para `failed`, dead-letter ou um
número maior de tentativas exige uma nova decisão de produto.

Implementação principal:

- `core/database/deploy_database/schema.sql`, função `chatbot.dequeue_message()`
- `workers/tratamento_erros_externos/expection_process.py`
- `core/repositories/atendimento/fila.py`

## 5. Ordenação e exclusão mútua

- Uma conversa deve ser processada por apenas um worker por vez.
- O lock da conversa poderá ser retomado se estiver abandonado por mais de 110
  segundos.
- `lock_version` impede que um worker antigo libere o lock adquirido por um
  worker mais novo.
- Uma mensagem não poderá ultrapassar outra mensagem anterior ainda aberta na
  mesma conversa.
- A ordem utiliza `received_data_hora` e, em caso de empate, `id_mensagem`.
- Uma mensagem posterior que encontrar outra anterior aberta será reagendada sem
  consumir uma tentativa de erro.

Implementação principal:

- `core/database/deploy_database/schema.sql`, funções `lock_conversa()` e
  `unlock_conversa()`
- `core/repositories/atendimento/conversas.py`
- `core/repositories/atendimento/fila.py`
- `workers/worker_flow/transacoes/lock_conversa.py`
- `workers/worker_flow/transacoes/ordem_turno.py`

## Histórico e recuperação

A fila se vincula à conversa e o histórico vincula cada resposta à entrada que a originou. O worker valida o lock ao persistir os efeitos e ao liberar a conversa. Se a resposta já ficou gravada, a recuperação utiliza essa resposta e preserva o contador. O intervalo entre o aceite externo e o commit pode produzir duplicidade no WhatsApp. [Ciclo do worker](workers/README.md)

## Cache, fallback e autocura

O banco guarda as identidades, o estado da conversa e o prazo do bloqueio. Redis acelera a consulta e pode ser reposto a partir do estado confirmado. O webhook também usa Redis para o limite de eventos. [Detalhes por domínio](core/cache/README.md)
