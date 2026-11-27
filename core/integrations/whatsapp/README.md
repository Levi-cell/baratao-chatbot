# Integração WhatsApp

Comunicação com a Meta WhatsApp Cloud API por meio da biblioteca PyWa.

- [Portal do projeto](../../../README.md)
- [Regras de negócio](../../../REGRAS_DE_NEGOCIO.md)
- [Padrões de arquitetura](../../../PADROES_DE_ARQUITETURA.md#whatsapp-e-pywa)
- [Integrações externas](../README.md)

## Direção das dependências

```text
worker -> pywa_functions -> messages
                      |--> cliente PyWa
                      `--> Meta
```

`messages` não importa PyWa. `pywa_senders` pode importar `messages`, cliente e
exceções da integração. Nenhum deles controla banco, fila, transição ou retry.

## Atendimento do pós-venda

O [catálogo de mensagens](messages/README.md) contém os textos das sete etapas. Os [senders](pywa_functions/pywa_senders) montam os envios com PyWa, inclusive a solicitação de telefone e os contatos de encaminhamento. O [remetente](remetente.py) seleciona a conta da central. A identificação do cliente fica em [identidade_cliente.py](identidade_cliente.py).

O worker ativa o [indicador de digitação](pywa_functions/digitacao.py) antes do primeiro envio do turno. O resolver devolve o resultado ao worker para registrar a resposta e a transição.

## Tools

Operações Meta compartilhadas e ferramentas administrativas usadas pelo
Django Admin e pelo webhook:

- registrar/desregistrar número;
- validar o vínculo entre WABA e phone ID;
- ativar/desativar a inscrição WABA;
- bloquear e desbloquear usuários na Meta.

O relatório de bloqueios é produzido por
[`utilitarios/monitoring/blocked_users.py`](../../../utilitarios/monitoring/blocked_users.py).
A comparação usa a chave `(waba_id, phone_id_unidade, wa_id_cliente)`.

`tools/usuarios.py` é a primitiva única de bloqueio e desbloqueio consumida pelo
webhook e pelo Admin. Os demais módulos deste diretório atendem às operações de
configuração da conta e do número. Eles podem reutilizar a fábrica de cliente,
mas não devem duplicar envio de etapa nem assumir responsabilidades de banco,
fila ou transação.

`tools/config.py` centraliza a configuração operacional da integração Meta, mas
os valores são lidos por `core/config_env.py` a partir de variáveis de ambiente:

```text
META_ACCESS_TOKEN
META_GRAPH_API_VERSION
META_HTTP_CONNECT_TIMEOUT_SECONDS
META_HTTP_READ_TIMEOUT_SECONDS
META_PHONE_REGISTRATION_PIN
```

`META_GRAPH_API_VERSION` usa o formato `27.0`, sem o prefixo `v`. Essa versão é
aplicada ao cliente PyWa e a todas as URLs diretas da Graph API. Se uma versão
nova apresentar incompatibilidade, a variável pode retornar manualmente para a
última versão estável validada.

Não adicione token ou outro valor sensível diretamente nesse arquivo. WABA ID e
phone number ID são dados por unidade e devem vir do banco/cache.
`META_PHONE_REGISTRATION_PIN` também é segredo operacional e só é necessário
para a operação administrativa de registro do número; não deve ser exibido em
logs, documentação ou mensagens.

## Limites

Esta integração não deve:

- executar SQL ou Redis;
- decidir etapa persistida;
- marcar fila como `sent`;
- escolher quantidade ou intervalo de retries;
- executar commit, rollback ou close;
- importar módulos de `callback` ou `workers`.

## Consumo Meta

O [cliente de consumo](consumo.py) consulta a API da Meta. O worker de consumo registra a coleta usada pelo painel. Uma falha de leitura preserva os totais já coletados.
