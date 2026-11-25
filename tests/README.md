# Testes das etapas 1 a 4 e 6 do pós-venda

Testes locais sem mensagens reais. A Meta e o Redis são simulados; a suíte de integração exercita o worker e SQL reais em PostgreSQL.

```powershell
python -m unittest tests.test_etapa1_pos_venda tests.test_etapa2_pos_venda tests.test_etapa3_pos_venda -v
python -m unittest tests.test_arquitetura_pos_venda tests.test_abertura_digitacao_pos_venda -v
```

Para integração, criar um banco local descartável cujo nome comece com `baratao_`. Definir `BARATAO_TEST_DSN` com a conexão desse banco e executar:

```powershell
python -m unittest tests.test_etapa1_pos_venda_postgres -v
```

A suíte recusa host remoto e recria o schema `chatbot` no banco de teste. Não usar credenciais de produção. Sem a variável, os testes de integração são marcados como ignorados.

Cobertura: saudação mesmo com mídia/pedido de humano, nomes acentuados/hífen/ponto final, caracteres inválidos, três repetições e quarto encaminhamento, uma mensagem com dois cartões/URLs, serialização no SDK, configuração incompleta, envio sem WAMID/falha Meta, rollback antes do commit, replay após checkpoint sem reenvio e sem contar outro turno, lock com versão, dados do titular, contatos apresentados, isolamento por central, expiração de 90 dias, cache vazio/indisponível e escrita atômica do TTL, migração reaplicável e etapa 8 sem bloqueio.

Para CPF: extração em frases, 11 dígitos com ou sem pontuação, separadores esquecidos, zeros iniciais, rejeição de letras/números maiores/CPFs diferentes, ausência intencional de cálculo de dígitos verificadores, pergunta e correção exatas, prioridade do tratamento universal, passagem para produto independentemente de haver cidade histórica no cadastro, armazenamento global e cópia do atendimento, rollback conjunto, replay sem novo envio e complemento de catálogo reaplicável. A suíte PostgreSQL mantém o nome `test_etapa1_pos_venda_postgres`, mas cobre as três etapas.

Resultado em 20/11/2026: **35 testes unitários e 19 de integração aprovados**. Um ensaio separado comparou a base da virada após os dois complementos à instalação atual: colunas, CHECKs, 11 etapas e 32 transições equivalentes.

Na revisão dos caracteres permitidos no CPF, a suíte passou a **36 testes unitários, todos aprovados**. A regressão verifica símbolos inseridos entre os dígitos e símbolos ligando o documento a dígitos extras, para impedir a aceitação de apenas um trecho. Somente ponto e hífen ASCII podem separar os dígitos do CPF. Essa revisão altera o extrator e não exige migração SQL.

Na reorganização de 21/11/2026, passaram **66 testes**: os 36 das etapas, 11 de
arquitetura e efeitos e os 19 de integração em PostgreSQL local. Os novos
testes cobrem gravação somente na etapa/evento corretos, dados ausentes ou
indevidos, repetição/replay sem escrita de cadastro, SQL fora de repositórios
e commits/rollbacks indevidos nas camadas internas. Os cenários de integração
confirmam que os dois checkpoints, o bloqueio, o contador e a recuperação
continuam funcionando após mover o SQL.

Na revisão de 22/11/2026 passaram **82 testes**: 56 unitários/arquitetura e 26 de integração. A etapa 11 é encerramento, a saudação está na própria etapa 1 e a etapa 3 pergunta produto sem coletar cidade. Foram acrescentados testes de digitação antes de todo tipo de resposta, ausência de digitação em replay/recusa anterior ao envio, falha opcional do indicador, abertura com cadastro parcial/completo, saudação após falha e migração preservando prazo e histórico. A fixture SQL de 18/11 existe só para testar migrações, não é o catálogo de instalação.

O teste não autoriza produção: webhook completo, processamento das respostas de visita e detalhes, demais abas do painel ainda estão em adaptação. Para exibir imagens reais na Meta, configurar a URL HTTPS pública descrita em [baratão moveis.md](<../baratão moveis.md>).


Na entrega de produto de 22/11/2026: **102 testes aprovados (69 unitários/arquitetura + 33 PostgreSQL)**. `test_etapa3_pos_venda` cobre texto com acentos/caixa/frases, palavras inteiras, negação de um ou ambos os setores, negativa de entrega sem excluir produto, botões e IDs estritos, opção desconhecida, rodapé e lista de assuntos, tratamento universal e efeito autorizado só na etapa 3. Integração confirma produto em atendimento 1:1, novo atendimento sem produto herdado, quarto turno, reset de contador, rollback/replay e migração de assunto 5 → 4. O erro inicial de conexão do ambiente local foi resolvido ao iniciar o PostgreSQL na porta 51221; a integração foi então executada com sucesso.

`test_etapa4_pos_venda` cobre cada linha da lista pelo extrator do webhook, IDs, frases com assuntos distintos, repetição e encaminhamento por produto. `test_etapa1_pos_venda_postgres` exercita o ciclo real da etapa 4, inclusive o contador, a persistência do assunto e a retomada após commit.

`test_etapa6_pedidos` cobre formato, sufixo de filial, múltiplos pedidos e a perda da nota por texto ou botão. `test_etapa1_pos_venda_postgres` cobre os vínculos por conversa e filial, o encaminhamento após três correções e a recuperação da fila após commit.


## Consumo Meta do varejo — 22/11/2026

```powershell
python -m unittest tests.test_consumo_meta_varejo -v
python -m unittest tests.test_consumo_meta_varejo_postgres -v
```

A integração usa `BARATAO_CONSUMO_TEST_DSN`, separada da variável dos testes de atendimento. Exige localhost e nome do banco iniciado por `baratao_`; recria somente o schema chatbot desse banco descartável. `tests/fixtures/consumo_meta_agregado.sql` representa a estrutura simplificada anterior para testar a migração, não é DDL de instalação.

**132 testes aprovados** na execução conjunta: 102 das etapas/arquitetura + 13 unitários de consumo + 17 de consumo em PostgreSQL. Cobrem os limites da cobertura ESL de 1.000 mensagens, total Meta sem abatimento artificial, reserva independente, recorte SERVICE/telefone/fuso, rejeição de resposta parcial, migração repetida sem perda de totais ou valores monetários, igualdade das colunas do DDL final e da base migrada, estado de detalhamento pendente, consolidação e falha no dia 25, resposta atrasada, HTTP fora de transação, advisory lock exclusivo, central inativa, isolamento por usuário/central, respostas privadas 401/403/503, filtro mensal e download de PDF.

Conferência visual com dados fictícios: tela em 1440 px e 390 px, seleção de meses, estado pendente sem zeros fictícios, tabela com rolagem interna e ausência de erros JavaScript. PDFs mensal, histórico e pendente renderizados e inspecionados. Django checks para as rotas/modelos usados pelo monitoramento: sem problemas. Hashes do núcleo de `worker_flow`, recuperação de erros externos e repositórios de atendimento conferidos, sem alteração nesta entrega.

Os testes simulam a Meta e não enviam WhatsApp. A migração foi exercitada somente no PostgreSQL local; não foi aplicada à base real ou à VM.
