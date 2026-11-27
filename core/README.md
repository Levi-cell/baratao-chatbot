# Core

Recursos compartilhados pelo webhook, monitoramento, workers, Django Admin e ferramentas
operacionais. `core` não conhece o fluxo completo de nenhum ponto de entrada.

- [Portal do projeto](../README.md)
- [Padrões de arquitetura](../PADROES_DE_ARQUITETURA.md)

## Mapa

| Pasta ou arquivo | Responsabilidade | Documento |
|---|---|---|
| `cache/` | Redis, cache local, fallback e autocura | [cache/README.md](cache/README.md) |
| `database/` | Conexão, DDL, funções PostgreSQL e setup | [database/README.md](database/README.md) |
| `repositories/` | SQL de runtime usando cursor recebido | [repositories/README.md](repositories/README.md) |
| `integrations/` | Comunicação com serviços externos | [integrations/README.md](integrations/README.md) |
| `validacoes/` | Regras puras dos dados do pós-venda | [Nome do titular](validacoes/nome_titular.py), [CPF](validacoes/cpf_titular.py), [pedidos](validacoes/pedidos_pos_venda.py) |
| `config_env.py` | Leitura de `.env`, variáveis de ambiente e validação de tipos | [Padrões de arquitetura](../PADROES_DE_ARQUITETURA.md#configuração-e-segredos) |
| `logging_config.py` | Configuração comum de logs e redução de identificadores | [Padrões de arquitetura](../PADROES_DE_ARQUITETURA.md#logging-e-exceções) |

## Contrato

`core` pode:

- encapsular infraestrutura compartilhada;
- executar operações de baixo nível;
- fornecer contratos simples para pontos de entrada;
- compartilhar regras puras e catálogos usados por mais de um consumidor;
- definir exceções de domínio compartilhadas.

`core` não deve:

- iniciar o laço infinito do worker;
- retornar `JsonResponse`;
- decidir etapa da conversa;
- escolher limite de retry;
- conter mocks ou dados exclusivos de teste;
- importar `workers` ou `callback`.

As transações pertencem ao arquivo que conhece o fluxo completo. Repositórios e
integrações não devem assumir propriedade de conexão recebida de outro módulo.

## Políticas e dados do atendimento

Nome e CPF são globais com cópia no atendimento. Produto, assunto, pedidos e detalhes pertencem à conversa. O catálogo autoriza cada avanço. O worker registra os efeitos da etapa após o envio e o bloqueio de 90 dias é publicado no cache após a confirmação no banco. [Roteiro do pós-venda](<../baratão moveis.md>)
