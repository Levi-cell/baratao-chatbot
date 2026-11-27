# Repositorios

SQL de runtime da aplicacao. Os modulos sao agrupados por dominio e entidade,
nao pelo consumidor nem pelo tipo de comando SQL.

- [Portal do projeto](../../README.md)
- [Padroes de arquitetura](../../PADROES_DE_ARQUITETURA.md#sql-e-repositórios)
- [Banco e deploy](../database/README.md)

## Pós-venda Baratão — responsabilidades atuais

O SQL executável fica somente em funções desta pasta. Os consumidores montam
o fluxo e fornecem o cursor; as funções não criam conexões nem fazem commit.

| Arquivo | Operações |
| --- | --- |
| `atendimento/chats.py` | Garantir o chat e serializar a decisão de abrir/retomar. |
| `atendimento/clientes.py` | Identificador do cliente, nome e CPF globais. |
| `atendimento/pos_venda.py` | Cópia de nome/CPF do atendimento e contatos realmente enviados. |
| `fluxo/contextos/pos_venda.py` | Ler cadastro global e contatos da central para o contexto. |
| `atendimento/entrada_fila.py` | Registro da entrada do webhook na fila. |
| `consumo_meta/coletas.py` | Consultas de consumo e aquisição do lock de sessão da coleta. |
| `seguranca/comparacao_bloqueios.py` | Fotografia de leitura dos bloqueios e unidades para comparação; nomes legados preservados. |
| `infraestrutura/conexao.py` | Consulta de versão do PostgreSQL no diagnóstico de conexão. |

O [catálogo de etapas](../database/deploy_database/catalogo.sql) define os eventos que os resolvers podem aplicar. A serialização por conversa fica em [locks.py](atendimento/locks.py), a ordenação no webhook em [turno_cliente.py](seguranca/turno_cliente.py) e o histórico usado no replay em [historico.py](atendimento/historico.py). O monitoramento filtra os dados pela central autorizada para o usuário.

## Contrato

Uma funcao de repositorio deve:

- receber `cursor`;
- usar SQL parametrizado;
- retornar linha, tupla, booleano, quantidade afetada ou uma representacao
  simples do resultado;
- validar invariantes persistidas quando necessario;
- deixar excecoes de persistencia chegarem ao orquestrador.

Uma funcao de repositorio nao deve:

- chamar `get_conn`;
- executar `commit`, `rollback` ou `close`;
- decidir retry;
- retornar resposta HTTP;
- acessar Redis, Meta ou outro servico externo;
- escolher a proxima etapa do atendimento.

## Mapeamento de resultados

Converter uma linha SQL em `dict`, tupla nomeada ou dataclass pertence ao
repositorio quando isso apenas nomeia os dados consultados. Decisoes de negocio,
montagem de mensagens, retry e efeitos externos continuam fora desta pasta.

## Propriedade da transacao

```text
worker_flow  -> flow_worker.py
webhook      -> post_flow.py, flood_guard.py ou bloqueio_meta_guard.py
scripts      -> proprio ponto de entrada
```

O repositorio nao anuncia rollback que nao executou. Ele propaga a excecao para
o dono real da transacao registrar e decidir a recuperacao.

## Idempotencia e concorrencia

- `seguranca/turno_cliente.py` usa advisory lock por cliente e unidade;
- `atendimento/fila.py` preserva a ordem por timestamp Meta e ID;
- `atendimento/historico.py` reutiliza os vinculos da mensagem original;
- `fluxo/transicoes.py` carrega somente as arestas permitidas para a origem;
- updates de conversa exigem origem, evento e destino compativeis;
- reaplicacao idempotente aceita somente a origem ou o destino exato.

## Ao criar um repositorio

Acrescente a operacao ao modulo da entidade correspondente. Crie um novo modulo
quando houver um dominio real e coeso; nao crie `utils.py` generico e nao mova
DDL para esta pasta.

## Testes na VM

O [roteiro Ubuntu](../../deploy/testar_ubuntu.sh) executa a suíte com PostgreSQL descartável. As instruções de implantação estão no [guia de deploy](../../deploy/README.md).
