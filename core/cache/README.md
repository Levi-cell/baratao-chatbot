# Cache

Camada de Redis, cache local, fallback e reparo detectável.

- [Portal do projeto](../../README.md)
- [Regras de negócio](../../REGRAS_DE_NEGOCIO.md#18-cache-fallback-e-autocura)
- [Padrões de arquitetura](../../PADROES_DE_ARQUITETURA.md#cache)

## Arquivos

```text
core/cache/
├── redis_client.py
├── cache_unidade.py
├── cache_flood_memoria.py
├── cache_reset.py
└── runtime/
    ├── cache_cliente.py
    ├── cache_conversas_bloqueadas.py
    ├── cache_flood_redis.py
    └── cache_webhook_erro_inesperado.py
```

`redis_client.py` lê a configuração por `core/config_env.py`:

```text
REDIS_HOST
REDIS_PORT
REDIS_USERNAME
REDIS_PASSWORD
REDIS_SSL
```

Esses valores devem vir de `.env` local, variáveis do ambiente de produção ou
gerenciador de segredos. Não coloque credenciais Redis diretamente no código.

O cliente exige Redis remoto: recusa loopback, endereço indefinido e IP da
própria máquina. Endereços privados de outra máquina são aceitos. O fallback
em memória descrito abaixo não é um servidor Redis local.

## Princípios

- PostgreSQL continua sendo a fonte persistida da verdade;
- Redis acelera consultas, não controla regras sozinho;
- indisponibilidade ou valor inválido deve ser registrado;
- o fallback usado depende do domínio;
- autocura cobre divergências detectáveis, não edição manual arbitrária;
- cache não executa commit ou rollback de transações pertencentes a outro fluxo.

## Cliente

O webhook resolve a identidade no PostgreSQL e associa o cliente à entrada da
fila. O worker usa esse ID. Para uma entrada antiga sem ID, consulta o cache
do telefone; em caso de ausência ou valor inválido, resolve o cliente no banco.
Após o commit publica o vínculo no Redis por 180 dias. A chave de telefone é
global; a chave de BSUID inclui a central. A conciliação de identidades ocorre
no banco. Se um ID obsoleto causar a violação `chat_id_cliente_fkey`, o worker
tenta remover a chave do telefone após o rollback para a próxima tentativa.

## Central de pós-venda

`cache_unidade.py` publica o mapa de `phone_number_id` para `id_central` das
centrais com `ativa = true`. O PostgreSQL versiona mudanças de cadastro pelo
trigger `central_mudou`. Cada processo confere a versão no primeiro uso, a cada
300 segundos e após uma falha sinalizada do Redis.

- **Webhook.** Um número ausente no mapa é confirmado no PostgreSQL. Se a central
  estiver ativa, tenta repor o mapa e segue. Quando a confirmação está
  indisponível, responde HTTP 503. A entrada na fila também confere a conta de
  origem e o número empresarial no banco.
- **Worker.** A leitura da identidade na fila traz também a central da mensagem.
  Se o Redis falhar, omitir o número ou apontá-lo para outra central, o worker
  consulta o cadastro pelo número. Com a central ativa e o ID confirmado, tenta
  repor o mapa e segue no mesmo ciclo, inclusive se só a escrita no Redis falhar.
  Uma suspensão preserva a mensagem pendente. Se o número comercial mudou após
  a retirada da fila, a tentativa seguinte relê o remetente. Uma violação de
  `chat_id_central_fkey` também aciona a recarga após rollback.
- **Admin.** Ao cadastrar ou trocar os identificadores de um remetente, o
  formulário confere o Redis, verifica o vínculo do número com a conta na Meta,
  assina os webhooks e registra o número. Se houver WAAC, compara os telefones
  retornados pela Meta antes do registro. Só aceita o formulário com confirmação
  das três operações. Editar o nome ou suspender o atendimento dispensa chamadas
  à Meta. Após o commit de uma inclusão, edição ou exclusão, relê as centrais
  ativas e publica o mapa. Um rollback descarta essa publicação. Se o Redis
  falhar depois do commit, o Admin avisa da pendência e a versão no PostgreSQL
  permite o reparo.

O provisionamento usa o token de sistema `META_ACCESS_TOKEN` e o PIN de
registro `META_PHONE_REGISTRATION_PIN` do ambiente do webhook. Uma assinatura
que a Meta já confirmou pode permanecer ativa se o registro do número ou a
gravação local falhar. O Admin informa qual confirmação faltou quando recebe
uma recusa da API. A suspensão local continua disponível sem acesso à Meta.

A escrita do mapa, quantidade e versão ocorre na mesma transação Redis. Se
outro processo publicar durante a leitura do banco, a recarga relê os dados
antes de tentar publicar novamente. Chat, fila, histórico, conversa, locks e
filiais de compra continuam no PostgreSQL.

## Conversa bloqueada

`runtime/cache_conversas_bloqueadas.py` acelera o bloqueio após encerramento,
com TTL calculado a partir de `finalizou_em` e `bloqueio_dias` da política da
etapa. O encaminhamento final do Baratão define 90 dias. Se a chave estiver
ausente ou o Redis falhar, consulta o banco e tenta repor o bloqueio pelo
tempo restante. Se a confirmação no banco falhar, levanta
`ValidacaoBloqueioConversaIndisponivel`, convertida em HTTP 503 no webhook.

O par da chave é cliente e unidade. Esse bloqueio de conversa não é o mesmo que
bloqueio de usuário na Meta.

## Flood

`runtime/cache_flood_redis.py` é a primeira camada do rate limit. A chave combina:

```text
wa_id_cliente + phone_id_unidade
```

Clientes diferentes da mesma unidade não compartilham contagem.

O Redis usa janela fixa e deduplica o WAMID por duas horas; a deduplicação e o
incremento dos contadores são uma única operação Lua atômica. A regra atual
do webhook é 15 WAMIDs distintos em cinco segundos. Em falha Redis, o
webhook tenta o contador do banco antes da memória.

`cache_flood_memoria.py` é a última barreira quando Redis e banco falham. É local
ao processo, limitada e não substitui Redis em ambiente com múltiplas instâncias.

## Erro inesperado do webhook

`runtime/cache_webhook_erro_inesperado.py` mantém um contador Redis por WAMID
para o tratamento genérico de exceções do POST. Permite três respostas 503;
da quarta ocorrência em diante, o webhook retorna 200 e ignora o evento. O
TTL de sete dias é renovado a cada incremento.

Sem WAMID ou com contador Redis indisponível, esse tratamento também retorna
200, sem fallback de contagem no banco ou em memória. Os 503 específicos de
validação e persistência não usam esse limite.

## Reset de desenvolvimento

`cache_reset.py` conserva o reset dos caches do chatbot usado pelo setup de
desenvolvimento: remove as chaves do mapa de unidades e os prefixos
operacionais e tenta recarregar o mapa. Não executa `FLUSHDB`.

## Testes relacionados

- `tests/test_etapa1_pos_venda_postgres.py` cobre os ciclos do worker, inclusive
  divergência da central e indisponibilidade no reparo.
- `tests/admin_central_postgres.py` cobre provisionamento, edição, suspensão,
  rollback e publicação após commit no Admin. Defina `BARATAO_TEST_REDIS_SOCKET`
  com o socket Unix de um Redis exclusivo de testes para incluir o percurso
  Admin → worker → webhook com publicação e leitura reais.

Esses arquivos cobrem o núcleo transacional; consulte também
[`tests/README.md`](../../tests/README.md).
