# Banco de dados do pós-venda Baratão

O banco continua sendo `db_chatbot` e os objetos da aplicação continuam no schema `chatbot`. A estrutura de negócio pertence ao SQL versionado. O Django administra suas tabelas de usuários, permissões e sessões. A configuração da conexão permanece em `connection_aws.py`.

## Banco e Django Admin na beta V0.2.1

Uma instalação limpa usa `schema.sql` com as declarações `CREATE` finais e `catalogo.sql` com sete etapas e 21 transições. Ao migrar uma base existente, atualize também esses arquivos quando a estrutura ou os dados iniciais mudarem. A retirada das seis saídas por mídia mudou apenas o catálogo. As funções PostgreSQL `dequeue_message()`, `lock_conversa(integer)` e `unlock_conversa(integer, integer)` continuam no DDL. A versão V0.2.1 atualiza o mapeamento Django e as permissões do Admin. O deploy executa `manage.py migrate` para cadastrar essas permissões.

Em **Administração → Centrais de pós-venda**, o cadastro valida o remetente na Meta. A central concentra as configurações do agente, os dois telefones de encaminhamento e as consultas de acessos, bloqueios, identidades e consumo. Alterações confirmadas no PostgreSQL atualizam a versão do cache e disparam a publicação no Redis após o commit. Em **Conversas**, abra uma conversa para consultar seus pedidos, etiquetas e recuperações de contato. Fila, histórico, etapas e transições são telas de consulta.

Ao excluir uma central, a confirmação mostra os vínculos afetados. A exclusão de uma central sem histórico remove também os vínculos de acesso e sua agenda de coletas. Chats, mensagens, identidades, bloqueios e consumo registrado protegem a central contra exclusão. Para interromper o atendimento preservando esses registros, desmarque **Ativa**. A exclusão local mantém o registro do número na plataforma Meta.

## Conferência do contato na etapa de CPF (Beta V0.3.0)

A V0.3.0 acrescenta `chatbot.atendimento_pos_venda.telefone_compartilhado` para os casos em que o telefone confirmado já pertence a outro cadastro. O índice parcial por CPF e ID acelera a busca inclusive em bases com duplicatas antigas. A coluna é opcional. Os registros anteriores ficam com NULL e as etapas e transições permanecem iguais. Para uma base na Beta V0.2.1, usar a [migração incremental](../../deploy/migrations/20261127_contato_conferencia_cpf.sql).

## Catálogo de produção

Na conferência de 27/11/2026, a base publicada tinha **7 etapas, 21 transições e bloqueio de 90 dias no encaminhamento**. As migrações descritas a seguir documentam o caminho das bases anteriores. A produção já chegou ao estado final.

A base que concluiu a migração de nove etapas com WAAC e BSUID recebe o [SQL incremental das sete etapas](../../deploy/migrations/20261126_baratao_sete_etapas.sql). Com a aplicação parada, executar o arquivo completo no DBeaver. A consulta final retorna IDs de 1 a 7, 28 transições, detalhes (6), encaminhamento (7) e 90 dias.

Na sequência, executar o [SQL de recoleta do titular](../../deploy/migrations/20261126_recoleta_titular.sql). A recoleta deixa 27 transições e `pula_cpf=false`. Depois, a [migração da Beta V0.2.0](../../deploy/migrations/20261127_midia_repete_etapa.sql) retira as seis arestas de mídia para a etapa final. O catálogo vigente tem 7 etapas e 21 transições.

O motivo histórico `visita_pendente` continua com retorno imediato. Os registros dos antigos encaminhamentos preservam a data de encerramento. A solicitação de contato por BSUID retoma a etapa equivalente. Instalações novas usam diretamente o schema e o catálogo atuais. Para uma base anterior ao WAAC, aplicar primeiro o [consolidado de nove etapas](../../deploy/migrations/20261126_pendencias_baratao_etapas_sequenciais.sql).

## Histórico das migrações até 25/11

Na base com o catálogo de 9 etapas e 25 transições, aplicar o [complemento de assunto](../../deploy/migrations/20261125_etapa4_assunto.sql) antes de iniciar o worker atualizado. Ele acrescenta `misto` ao tipo `chatbot.assunto` e os eventos `humano_solicitado` e `limite_sem_avanco` da etapa 4 para a 11. Os assuntos anteriores preservam seus valores.

Após a migração de assunto, aplicar [etapa 6 e filiais dos pedidos](../../deploy/migrations/20261125_etapa6_pedidos_filiais.sql) antes de iniciar o worker atualizado. O catálogo inicial tem 26 filiais. Em `pedido_conversa`, `codigo_filial` deriva dos dois dígitos finais de `numero` e referencia `filial_compra.codigo`. A última consulta da migração mostra filiais, transições da etapa 6 e eventuais pedidos antigos com filial desconhecida. Novas gravações exigem código cadastrado.

Um banco já atualizado até os complementos de 18/11 recebe [20261122_etapas_produto_encerramento.sql](../../deploy/migrations/20261122_etapas_produto_encerramento.sql), com os serviços parados. Em seguida recebe [20261122_etapa3_produto_assunto.sql](../../deploy/migrations/20261122_etapa3_produto_assunto.sql), que remapeia assunto de 5 para 4 e completa os eventos da etapa 3. Preservam dados e datas de bloqueio. Não reaplicar um complemento anterior depois do mais recente. Uma instalação limpa usa o DDL e catálogo atuais e não executa as migrações históricas. Essas duas migrações de etapas não mudam colunas; os campos de cidade antigos são conservados.

As seções abaixo registram a ordem das migrações anteriores. Seus totais de etapas/transições descrevem cada versão histórica, não substituem o catálogo acima. Não reaplicar os scripts de 18/11 depois do complemento de 22/11.

## Consumo Meta no varejo — 22/11/2026

Para a base já convertida em varejo, aplicar [20261122_consumo_meta_varejo.sql](../../deploy/migrations/20261122_consumo_meta_varejo.sql), com o coletor parado. É independente dos complementos de catálogo. O DDL final permanece somente com comandos CREATE e já contém a estrutura resultante.

A migração adiciona divisão entre janela gratuita e reserva Meta, configuração mensal da cobertura ESL de 1.000 mensagens e os campos de conferência. Preserva `qtd_gratuitas`, `qtd_cobradas_meta`, `valor_meta`, `moeda` e a identidade do período. Linhas agregadas ficam `pendente_detalhamento`, com a divisão NULL até leitura válida; não há reconstrução artificial. Centrais inativas não são recoletadas nem expostas a operadores. O histórico anterior completo continua no backup.

O acesso agora usa `monitoramento_acesso` → `central_pos_venda`. Enquanto não há seletor de central, cada usuário do painel deve ter exatamente um vínculo ativo; ausência ou ambiguidade nega acesso. O guard mantém aliases de leitura `id_unidade`/`nome_unidade` só para o restante do painel ainda em adaptação. As consultas de Consumo usam diretamente `id_central`.

## Virada do Supera no banco existente

1. Com os processos antigos parados, confirme que há um backup atual do schema `chatbot`, inclusive os dados das partições do histórico. Um arquivo PostgreSQL de formato personalizado (`.dump`) pode ser restaurado com `pg_restore`. Guarde-o fora do repositório. Se houve gravações após a exportação, repita o backup antes da virada.
2. No editor SQL do DBeaver conectado ao banco de destino, execute o [arquivo de migração inteiro](../../deploy/migrations/20261116_baratao_pos_venda.sql) com **Executar script SQL**. O arquivo abre a transação, verifica a origem, trava as tabelas de negócio, migra as estruturas e confere os saldos antes do commit. Um erro antes do commit permite `ROLLBACK;` na mesma conexão. O script recusa reaplicação.
3. A consulta final deve mostrar 11 etapas, 29 transições, zero centrais ativas e zero conversas. As outras duas colunas mostram quantos registros mensais e bloqueios Meta foram conservados. Associar o operador e configurar a central da Baratão é uma etapa posterior. Antes de iniciar os processos novos, usar chaves Redis próprias da Baratão ou invalidar somente o cache do aplicativo anterior. A virada SQL alcança apenas o PostgreSQL.

### Destino dos registros

| Dados do Supera | Resultado da virada |
| --- | --- |
| Cadastro das unidades | As mesmas chaves, WABAs e números empresariais passam para centrais inativas, sem operadores atribuídos. Os novos números de destino devem ser distintos e são obrigatórios para ativar uma central. |
| Consumo e agenda da Meta | Mantêm central, mês, quantidade cobrada e agenda de leitura. Os dois contadores de mensagens gratuitas do Supera são somados. Valor monetário e moeda ficam nulos nas linhas antigas. Os detalhes originais, inclusive a antiga regra comercial da ESL, continuam no backup. |
| Bloqueios e eventos de flood | Mantêm o número do cliente vinculado à central de origem. A data dos bloqueios antigos fica nula porque o legado não a registrava. Esses registros refletem a proteção operacional. O bloqueio temporário do fluxo fica separado dos bloqueios Meta. A etapa 10 terá prazo de 90 dias após a migração complementar; a etapa 8 permite retorno imediato. |
| Clientes, chats, conversas, fila e histórico | Os dados anteriores ficam no backup. A operação do varejo começa vazia. O histórico novo tem WAMID único e guarda os dados da interação. |
| Funil, dependente, FireAds, follow-up, endereços, desafios e satisfação | As tabelas e os campos específicos do Supera são retirados do schema em operação. |
| Autenticação do Django | Os usuários, grupos e permissões são preservados. A relação `monitoramento_acesso` começa vazia e tem uma FK real para `chatbot.auth_user(id)`. |

Depois do commit, a recuperação integral do Supera exige restaurar o backup. Para consultar dados antigos, restaure-o em um ambiente isolado. O arquivo contém dados de clientes e autenticação.

## Instalação em um schema preparado

Com `chatbot.auth_user` já criado pelo Django e sem tabelas de negócio, execute na raiz do projeto:

```bash
cd /opt/chatbot/app
sudo -u chatbot bash -c 'set -a; source /etc/chatbot/chatbot.env; set +a; /opt/chatbot/venv/bin/python -m core.database.deploy_database.setup_database'
```

O setup aplica o [DDL final](deploy_database/schema.sql) e o [catálogo de etapas e transições](deploy_database/catalogo.sql) em uma única transação de `transacao_deploy.py`. Ele exige um schema existente, recusa o legado ou uma instalação já iniciada e deixa a configuração da role e o Redis sob responsabilidade do ambiente.

## Contratos do fluxo

O chat identifica o par cliente e central. Cada chat pode ter várias conversas e no máximo uma ativa. O cadastro do titular pertence ao cliente. Produto, assunto, relato, encaminhamento e pedidos pertencem à conversa. A combinação conversa e número do pedido é única e o mesmo número pode ser declarado em outros atendimentos.

A fila preserva a reserva, o vencimento de uma reserva abandonada e a ordenação dos turnos na mesma central. O banco mantém o lock com versão, o vínculo de cada resposta ao WAMID de entrada e a versão de cache das centrais. O encaminhamento para dois setores grava um único carrossel e seu WAMID.

O worker grava nome e CPF no cadastro global e no atendimento da conversa. Salva o produto na passagem de 3 para 4, o assunto de 4 para 5 e os pedidos ou a perda da nota de 5 para 6. Em seguida grava o relato e finaliza na etapa 7. Um encaminhamento antecipado usa as informações já coletadas. O webhook, o worker e a seção Consumo operam sobre o schema de varejo. Algumas métricas legadas do painel ainda dependem de adaptação. [Fluxo do pós-venda](<../../baratão moveis.md>)


## Atualização da etapa 1 e bloqueio de 90 dias

Depois da virada de 16/11/2026, executar [20261118_etapa1_encaminhamento_90_dias.sql](../../deploy/migrations/20261118_etapa1_encaminhamento_90_dias.sql) com o worker parado. Esse arquivo é complementar; não executar a virada destrutiva novamente em um banco que já contém `central_pos_venda`.

Esse complemento estabelece `etapa.bloqueio_dias` (0 ou 90), contador de 0 a 3, cinco motivos de encerramento e 30 transições na base da virada. Encaminhamento (etapa 10) encerra com bloqueio por cliente/central de 90 dias a partir da data final; visita pendente (8) encerra sem bloqueio. A abertura técnica não encaminha mídia antes de explicar as regras. Os eventos de pedido humano e limite de repetição são acrescentados à etapa 1.

O script complementar não apaga dados de atendimento, é reaplicável e preserva `finalizou_em`: não reinicia o prazo em uma reaplicação. Se houver encerramentos existentes na etapa 10, o prazo passa a ser calculado como 90 dias desde a data original. Os contadores existentes acima de 3 ficam em 3.

A instalação limpa pelo setup já inclui essas decisões e o complemento de CPF descrito abaixo; nela não é necessário aplicar migrations. Uma base já convertida ao varejo recebe apenas os complementos ainda pendentes, na ordem etapa 1 e depois etapa 2. Não executar novamente a virada destrutiva.

O contador não promove mais bloqueio na Meta. O fechamento só produz o cache após commit. Prefixos de cliente, central e bloqueio da nova aplicação começam por `baratao:`. Os aliases `id_unidade` e `id_phone_unidade` permanecem em algumas interfaces Python/retorno do dequeue para preservar o protocolo transacional; as consultas do caminho implementado utilizam `id_central` e `central_pos_venda`.

## Atualização da etapa 2 — CPF

Depois do complemento da etapa 1, executar [20261118_etapa2_cpf.sql](../../deploy/migrations/20261118_etapa2_cpf.sql), com o worker parado. O arquivo acrescenta duas transições com origem 2: `humano_solicitado` e `limite_sem_avanco`, ambas para o encaminhamento (10). O catálogo final tem **11 etapas e 32 transições**. A transição de mídia da etapa 2 já existia.

Os campos de CPF já existem no DDL final. Não há nova coluna, `ALTER TABLE` nem atualização de dados de clientes nesse complemento; ele pode ser reaplicado. A validação do aplicativo exige 11 dígitos ASCII e guarda texto sem pontuação, preservando zeros iniciais, sem calcular dígitos verificadores. O SQL mantém a restrição de formato correspondente.

A migração e os testes de persistência/rollback foram verificados em PostgreSQL 18.3 local isolado em 20/11/2026. A base da virada, após os complementos das etapas 1 e 2, coincidiu com a instalação limpa em colunas, CHECKs, etapas e transições; o complemento de CPF foi reaplicado sem duplicar eventos. Ter esses arquivos no projeto não significa que foram aplicados no banco de produção.
