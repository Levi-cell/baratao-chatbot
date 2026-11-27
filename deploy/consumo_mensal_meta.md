# Consumo Meta no pós-venda Baratão

Na Beta V0.2.1, o worker de consumo está implantado na VM Ubuntu. A coleta, a seção Consumo e os PDFs usam `central_pos_venda` e `id_central`. A adaptação das outras métricas do painel segue em andamento.

## O que permanece

- Três grupos: mensagens na janela gratuita, reserva gratuita Meta e mensagens cobradas pela Meta.
- Cobertura comercial da ESL Tech de **1.000 mensagens cobradas por mês**, separada da reserva Meta. Exemplo: 1.300 cobradas → 1.000 assumidas pela ESL e 300 pela empresa; o indicador da Meta continua 1.300.
- Filtro por mês/ano, cartões, histórico, PDF mensal e PDF de todos os meses, com os mesmos cálculos.
- Coleta de volumes `SERVICE` via `pricing_analytics`, por WABA/número/fuso. A consulta não envia mensagens e não participa dos commits/checkpoints do `flow_worker`.
- Tarifa de referência já existente (R$ 0,035), identificada como referência com vigência e sujeita a atualização. Não é valor de fatura. O coletor atual não consulta COST; `valor_meta`/`moeda` preexistentes são preservados e não preenchidos por estimativa.

Esta decisão substitui a orientação anterior de remover a cobertura ESL do varejo. A política da Meta é uma dependência externa e deve continuar sendo conferida em [preços oficiais](https://developers.facebook.com/docs/whatsapp/pricing/) e na [referência de analytics](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/pricing_analytics/).

## Migração de 22/11 para bases anteriores ao detalhamento do consumo

1. Manter o `chatbot-worker-consumo-meta.service` parado durante a atualização. Usar o procedimento normal de backup e troca de código do ambiente.
2. Executar **inteiro**, com BEGIN/COMMIT, [20261122_consumo_meta_varejo.sql](migrations/20261122_consumo_meta_varejo.sql). Não executar a migração original de 20260929, que usa `unidade`, nem reaplicar a virada de 20261116. Em falha, fazer ROLLBACK e resolver a causa. A migração usa o mesmo advisory lock do coletor e expira se houver uma coleta concorrente.
3. A migração é aditiva e reaplicável. Preserva os totais, valores monetários e a identidade dos meses. Não altera clientes, conversas, bloqueios, filas, catálogo ou contas Meta.
4. A versão simplificada do banco somou janela e reserva em `qtd_gratuitas`. Esses registros passam a `pendente_detalhamento`; os novos componentes ficam NULL. A interface apresenta informação indisponível, sem deduzir uma divisão ou saldo falsos. Somente uma coleta completa da mesma conta/número/fuso pode preencher a divisão.
5. Registros de centrais ativas são reagendados; centrais antigas inativas permanecem preservadas e não reativam a integração do Supera. Um `consolidado_em` antigo é preservado enquanto a divisão está pendente. Ao recompor a divisão, o período volta à conferência: o agregado anterior não serve como segunda leitura válida para consolidar.
6. Para uma instalação limpa, usar o DDL atual em `core/database/deploy_database/schema.sql`, somente CREATE. Não executar migrações históricas após instalar o DDL final.

## Configuração e execução

Continuam sendo usadas as credenciais DB/Meta do ambiente. Não colocar tokens no código ou logs.

```dotenv
CONSUMO_META_ENABLED=True
CONSUMO_META_CICLO_SEGUNDOS=60
CONSUMO_META_INTERVALO_SEGUNDOS=3600
CONSUMO_META_LIMITE_POR_CICLO=100
CONSUMO_META_HORA_CONFERENCIA=9
```

Sem `CONSUMO_META_ENABLED=True`, o iniciador termina sem acessar a Meta. O módulo permanece `python -m workers.worker_consumo_meta.iniciar_worker_consumo_meta`. O serviço continua em [chatbot-worker-consumo-meta.service](systemd/chatbot-worker-consumo-meta.service).

Na instalação ou atualização do coletor, validar o Django no ambiente da aplicação. Atualizar os estáticos se houver mudança na interface e recarregar o systemd se o arquivo de serviço mudar. A coleta roda separada do webhook e do worker de atendimento.

Para conferir um coletor já implantado:

```bash
systemctl show chatbot-worker-consumo-meta.service -p ActiveState -p SubState -p NRestarts --no-pager
sudo journalctl -u chatbot-worker-consumo-meta.service -n 40 --no-pager
```

## Agenda, erros e consolidação

- Só centrais com `ativa = true` entram na coleta. A condição é revalidada antes do trabalho e ao persistir depois do HTTP.
- Supervisor a cada 60 segundos, mês atual por hora; meses anteriores pendentes diariamente no fuso do período. Reinício respeita a agenda persistida. Meses ausentes são recuperados desde outubro/2026, conforme a janela histórica da API.
- Primeiro prazo: dia 25 do mês seguinte. Exige duas leituras completas, de datas locais diferentes, com os três volumes iguais. Falha, divergência, falta de comparação ou prazo perdido adiam a decisão para o próximo dia 25. Não há aprovação retroativa no dia 26.
- Uma falha preserva a última leitura válida, registra tentativa e agenda nova consulta; não insere zeros. Período indisponível na janela histórica exige revisão, não fabricação de dados.
- Um erro não impede coletar as outras centrais. Advisory lock de sessão 73492601 impede dois coletores simultâneos; fechamento da conexão libera o lock.
- Não há transação aberta durante HTTP. As gravações de total e agenda são atômicas e rejeitam leituras atrasadas. Conta, telefone ou fuso diferentes exigem revisão do período, sem mistura silenciosa de dados.
- `Consolidado` significa conferência interna dos volumes, não fechamento da fatura Meta.

## Autorização e apresentação

A identidade vem da sessão Django. `monitoramento_acesso` vincula o operador à central; navegador, query string e telefone do cliente não escolhem o escopo. Contas administrativas não ganham bypass. Enquanto não há seletor de central, é necessário exatamente um vínculo ativo; ambiguidade nega acesso.

A seção Consumo e os PDFs leem apenas o PostgreSQL. Navegar entre meses não chama a Meta. Respostas e PDFs têm cabeçalhos privados/no-store. A cobertura ESL é calculada por central/número e mês, sem acumular saldo entre períodos.

O carregamento dos serviços das abas antigas foi isolado nas respectivas rotas para que o FireAds removido não impeça login/Consumo. Isso não adapta os relatórios ou conversas do Supera ao varejo.

## Verificação na VM Ubuntu

A suíte usa transporte Meta simulado e um banco descartável com prefixo `baratao_`. O script de testes configura `BARATAO_CONSUMO_TEST_DSN` para esse banco. [Documentação de testes](../tests/README.md)
