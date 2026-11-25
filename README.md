# Chatbot do Supera

Registro de encerramento do desenvolvimento, em 14/11/2026. Este repositório conserva o atendimento determinístico do Supera pelo WhatsApp e o painel de monitoramento por unidade. A última versão numerada é **V1.20.0** (`4c44798`). O commit posterior `a7c110e` ajustou o texto do endereço. A árvore de trabalho inclui também uma correção da interpretação de pedidos de preço na etapa de profissão. O [histórico](VERSIONAMENTO.md) distingue versões, correções e estado local.

A virada do banco para a Baratão tem [procedimento próprio](core/database/README.md) e [fluxo de pós-venda](<baratão moveis.md>). As etapas 1 (nome) e 2 (CPF) do Theo, o tratamento universal compartilhado, os cartões de encaminhamento, o contador de três repetições e o bloqueio de 90 dias estão implementados. Nome e CPF são salvos no cadastro global do cliente e na cópia do atendimento. A etapa 3 já valida produto e apresenta assunto na etapa 4; a etapa 4 grava o assunto por conversa e apresenta a pergunta de pedidos na etapa 6. Na etapa 6, o bot identifica a filial de cada pedido pelo sufixo, aceita a perda da nota e encaminha para visita à loja ou detalhes. O retorno com cadastro completo começa em 3. O worker de consumo, a aba Consumo e os PDFs estão adaptados ao varejo, preservando a cobertura ESL de 1.000 mensagens ([migração e operação](deploy/consumo_mensal_meta.md)). Webhook completo, respostas das etapas 7 e 9 em diante e demais abas do painel ainda estão em adaptação; esta árvore não está pronta para iniciar o atendimento completo. As regras abaixo documentam a aplicação do Supera.

## Como funciona

1. O webhook Django valida a entrada da Meta, verifica as proteções do cliente e da unidade e registra a mensagem na fila PostgreSQL. O worker de fluxo processa um turno por vez e registra a resposta e o movimento da conversa.
2. Na abertura, o bot procura nome do titular, e-mail e destinatário na primeira mensagem. Sem link de agendamento, também procura o turno. Em unidades integradas, a FireAds pode completar os campos que faltam. O atendimento pergunta o que continuar faltando na etapa correspondente.
3. O catálogo tem **24 etapas e 32 transições**. Abrange titular e dependente, profissão, idade, oferta, triagem, reserva com link ou consultor e avaliação. As dúvidas financeiras, de endereço e de reforço escolar têm tratamento próprio. A etapa 8 responde no retorno à 9. As etapas 23 e 24 ficam fora desses tratamentos.
4. O follow-up usa até três mensagens. Os marcos sem atraso são 15 minutos, 7 horas e 14 horas. Uma reação aceita durante o ciclo ativo é processada pelo fluxo. O terceiro envio confirmado encerra a conversa sem bloqueio de 30 dias.
5. O worker do Funil processa a entrega comercial. Para unidades com FireAds, o dashboard deve ser confirmado antes do envio ao Funil. O painel permite consultar conversas, relatórios e consumo. O acesso é por unidade e a interface de monitoramento é de leitura.

## Onde encontrar cada regra

| Assunto | Referência |
| --- | --- |
| Etapas, validações, idempotência e encerramentos | [Regras de negócio](REGRAS_DE_NEGOCIO.md) |
| Componentes, banco e limites de transação | [Arquitetura](PADROES_DE_ARQUITETURA.md), [core](core/README.md), [DDL e setup](core/database/README.md) e [repositórios](core/repositories/README.md) |
| Entrada HTTP, Admin e painel | [Aplicativos Django](callback/README.md) e [origens nos relatórios](docs/monitoramento_fireads_filtros_relatorios.md) |
| Webhook e seis workers, cadências e logs | [Inventário dos serviços](workers/README.md) |
| FireAds, WhatsApp e Funil | [FireAds](docs/fireads.md), [WhatsApp](core/integrations/whatsapp/README.md) e [Funil](core/integrations/funil/README.md) |
| Apresentação e retomada de etapa | [Composição de mensagens](core/integrations/whatsapp/messages/README.md), [endereço e retorno](docs/enderecos_e_retorno.md) e [rotina de etapas](ROTINA_IMPLEMENTACAO_ETAPAS.md) |
| Operação e dados | [Implantação](deploy/README.md), [cache](core/cache/README.md), [utilitários](utilitarios/README.md) e [dados pessoais](docs/LGPD_V1.md) |
| Verificação local | [Ambiente de desenvolvimento](AMBIENTE_DESENVOLVIMENTO.md) e [testes](tests/README.md) |

## Propostas preservadas

O [plano prático de identidade WhatsApp](docs/user_id_plano_logico_pratico.md) e seu [contrato teórico](docs/user_id_plano_logico_teorico.md) descrevem suporte futuro a `user_id`. As demais [ideias de evolução](docs/ideias_futuras.md) estão registradas para consulta. A condição dos serviços em uma instalação pode ser verificada pelas unidades systemd em [deploy/systemd](deploy/systemd).
