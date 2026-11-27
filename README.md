# Chatbot do Baratão Móveis

Sistema de atendimento automatizado de pós-venda pelo WhatsApp, desenvolvido para a central de atendimento do Baratão Móveis. O assistente virtual **Theo** realiza a triagem inicial dos clientes, coleta informações sobre a compra e direciona o atendimento aos setores responsáveis por Móveis e Estofados.

O projeto utiliza um fluxo determinístico, com etapas e transições controladas pelo banco de dados, processamento assíncrono de mensagens e persistência do histórico de atendimento. Também possui uma interface web de monitoramento e um componente independente de acompanhamento do consumo da API da Meta.

**Beta V0.3.0.** O webhook e os dois workers rodam na VM Ubuntu. O atendimento tem sete etapas. O Django Admin permite administrar centrais e consultar fila, histórico e transições. O portal dos operadores exibe o consumo por central e mês. Parte das métricas herdadas ainda requer adaptação ao varejo. [Admin e painel](callback/README.md#admin-e-painel)

## Objetivos

- Centralizar a entrada de clientes das diferentes lojas em um único canal de pós-venda.
- Padronizar a coleta de informações antes do atendimento humano.
- Identificar o produto, o assunto e a filial de origem da compra.
- Direcionar o cliente à equipe responsável, aproveitando os dados já coletados.
- Reduzir atividades repetitivas da equipe e manter a rastreabilidade dos atendimentos.
- Monitorar os volumes de mensagens e o consumo da integração com a Meta.

## Fluxo de atendimento

O catálogo vigente possui **7 etapas e 21 transições**. Os identificadores são definidos em `core/etapas_pos_venda.py` e as transições autorizadas pelo catálogo SQL do PostgreSQL.

| Etapa | Responsabilidade | Estado atual |
| --- | --- | --- |
| 1 | Saudação do Theo e coleta do nome completo do titular | Implementada |
| 2 | Coleta e validação do formato do CPF | Implementada |
| 3 | Identificação do produto: Estofados, Móveis ou Ambos | Implementada |
| 4 | Identificação do assunto do atendimento | Implementada |
| 5 | Coleta dos números dos pedidos ou registro de nota perdida | Implementada |
| 6 | Relato da situação em uma mensagem de texto | Implementada |
| 7 | Encaminhamento humano, aviso de assistência quando aplicável e bloqueio interno de 90 dias | Implementada |

Os IDs vão de 1 a 7. A cidade não faz parte da coleta atual.

### Abertura e retorno

- Toda nova conversa começa pelo nome do titular, inclusive em um retorno após os 90 dias.
- Após o nome, a entrada somente com BSUID exige compartilhamento oficial. Em seguida, o Theo pede o CPF desta compra.
- Se houver uma conversa ativa, o atendimento retoma a etapa persistida.

Nome e CPF são armazenados no cadastro global do cliente e na cópia do atendimento. Produto, assunto e pedidos pertencem à conversa, evitando reutilizar indevidamente informações de uma compra anterior. A validação do CPF verifica seu formato, sem comprovação de identidade ou consulta à Receita Federal.

### Produtos e assuntos

O cliente seleciona Estofados, Móveis ou Ambos. Na sequência, pode escolher um dos seguintes assuntos:

- **Entrega:** previsão de entrega do produto.
- **Assistência:** avarias no produto.
- **Montador:** necessidade de montagem.
- **Misto:** dois ou mais assuntos.
- **Outros:** solicitações não contempladas nas opções anteriores.

A etapa 5 aceita múltiplos números de pedidos na mesma mensagem, identifica a filial pelos dois dígitos finais de cada pedido e permite informar a perda da nota por texto ou botão. O catálogo inicial possui 26 filiais cadastradas.

Com as notas confirmadas ou perdidas, todos seguem para o relato (6) e o encaminhamento (7). Para Assistência e Misto, o Theo orienta sobre fotos, vídeos, loja da compra e prazo de reclamação.

### Encaminhamento humano e tratamento universal

Após a apresentação, uma mídia repete a pergunta com o aviso de texto. A quarta resposta consecutiva inválida ou um pedido textual de humano encaminha. Uma resposta válida avança e zera o contador, inclusive após três correções.

O encaminhamento apresenta os contatos de pós-venda conforme o produto escolhido. Com ambos ou sem produto definido, uma única mensagem apresenta os dois cartões com foto e botão. Os dados disponíveis da conversa podem compor o resumo encaminhado no link do WhatsApp.

Após a confirmação do encaminhamento, o fluxo registra o encerramento e aplica um bloqueio interno de 90 dias por cliente e central. Esse bloqueio não equivale a um bloqueio na plataforma WhatsApp.

O atendimento humano ocorre nos números de destino; a apresentação dos contatos não significa que o cliente já enviou uma mensagem à equipe.

## Arquitetura

A aplicação mantém a separação entre recepção HTTP, processamento do fluxo, validação, envio de mensagens, persistência e monitoramento.

[Fluxograma da arquitetura e recuperação](docs/fluxograma_arquitetura.md) · [Fluxograma do atendimento e respostas](docs/fluxograma_atendimento.md)

O worker de fluxo utiliza locks, controle de ordem, checkpoints e transações para preservar a consistência das conversas e recuperar processamentos interrompidos. Respostas já confirmadas podem ser recuperadas sem novo envio. A confirmação externa pela Meta e o commit local não são atômicos entre si: uma falha entre ambos ainda pode causar duplicação na recuperação.

### Tecnologias

| Tecnologia | Utilização |
| --- | --- |
| Python 3.12 | Linguagem principal |
| Django 6.0.10 | Webhook, autenticação e interface de monitoramento |
| PostgreSQL / Psycopg 3 | Fila, catálogo, cadastros, histórico e consumo |
| Redis | Cache e mecanismos de proteção operacional |
| WhatsApp Cloud API / PyWa 4.5.0 | Integração e envio de mensagens interativas |
| HTML, CSS e JavaScript | Interface de monitoramento |
| ReportLab e svglib | Geração de relatórios de consumo em PDF |
| Gunicorn, Nginx e systemd | Componentes de implantação em Linux |
| unittest | Testes unitários, de arquitetura e integração |

As versões completas das dependências estão em [requirements.txt](requirements.txt).

## Estrutura do projeto

```text
baratao-chatbot/
├── callback/
│   ├── callback/             # Configurações Django e rotas principais
│   ├── webhook/              # Recepção de eventos do WhatsApp
│   └── monitoramento/        # Interface web e relatórios
├── core/
│   ├── cache/                # Redis e cache de execução
│   ├── consumo_meta/         # Regras de apuração de consumo
│   ├── database/             # Conexão, DDL e catálogo SQL
│   ├── integrations/         # Integração WhatsApp, mensagens e senders
│   ├── repositories/         # Consultas e persistência de dados
│   ├── validacoes/           # Validadores e extratores
│   └── etapas_pos_venda.py   # IDs e eventos do fluxo
├── workers/
│   ├── worker_flow/          # Processamento do atendimento
│   └── worker_consumo_meta/   # Coleta independente de consumo
├── deploy/                   # Migrações, Nginx e unidades systemd
├── regras_deploy/            # Procedimentos operacionais
├── tests/                    # Testes automatizados e fixtures SQL
├── utilitarios/               # Ferramentas auxiliares
└── requirements.txt          # Dependências Python
```

Estrutura resumida, com foco nos componentes do Baratão. Alguns módulos e arquivos do sistema anterior ainda permanecem no repositório durante a migração.

## Monitoramento e consumo Meta

O módulo de consumo está adaptado ao varejo e opera por central e mês. A coleta é independente do worker de atendimento e não envia mensagens aos clientes.

- Separação entre mensagens na janela gratuita, reserva gratuita Meta e mensagens cobradas pela Meta.
- Cobertura comercial ESL Tech de 1.000 mensagens cobradas por mês, contabilizada separadamente da reserva Meta.
- Consulta do histórico, seleção de período e geração de PDFs mensais e históricos.
- Coleta periódica via `pricing_analytics`, com agenda persistida e preservação da última leitura válida em caso de falha.
- Consolidação interna conforme conferência dos volumes, sem equivaler ao fechamento da fatura Meta.
- Autenticação Django e restrição de acesso à central vinculada ao operador.

As abas de conversas e demais relatórios ainda precisam ser integralmente adaptadas ao novo modelo de pós-venda.

Consulte o [guia de consumo Meta](deploy/consumo_mensal_meta.md) para configuração, apuração, migração e operação.

## Desenvolvimento local

Requisitos: Python 3.12, PostgreSQL e Redis, além das configurações de desenvolvimento da integração WhatsApp para testes externos autorizados.

Na VM Ubuntu, na raiz do projeto:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Configure as variáveis de ambiente necessárias conforme [core/config_env.py](core/config_env.py). Utilize um arquivo `.env` privado e credenciais exclusivas de desenvolvimento.

Com o banco e o ambiente configurados, verifique o Django:

```bash
PYTHONPATH="$PWD" python callback/manage.py check
```

Para iniciar o servidor local, quando o ambiente estiver preparado:

```bash
PYTHONPATH="$PWD" python callback/manage.py runserver
```

O setup de uma base nova e a atualização de uma base existente seguem procedimentos diferentes. Consulte o [guia do banco de dados](core/database/README.md) antes de executar scripts SQL. Não aplique migrações históricas sobre uma instalação limpa que já utiliza o DDL e o catálogo vigentes.

## Testes automatizados

Na VM Ubuntu, execute `sudo -u chatbot bash deploy/testar_ubuntu.sh` na raiz da versão em teste. O script cria três bancos PostgreSQL temporários e executa a suíte com o envio à Meta simulado. Consulte [o ambiente de desenvolvimento](AMBIENTE_DESENVOLVIMENTO.md).

## Implantação

Os componentes mantidos para a arquitetura do Baratão são o serviço web (webhook e painel), o worker de fluxo e o worker de consumo Meta. Os arquivos de referência estão em [deploy/systemd](deploy/systemd) e [deploy/nginx](deploy/nginx).

A atualização do banco existente exige backup, aplicação dos complementos adequados ao estado da base e validação antes da inicialização dos serviços. Consulte o [guia do banco](core/database/README.md) e os [procedimentos de deploy](regras_deploy/rotina_deploy.md).

A versão publicada está na branch `prod`. O histórico registra o hash completo após a publicação.

## Segurança e privacidade

O sistema trata dados pessoais, incluindo nome, CPF e telefone. O código e a documentação não devem expor dados reais de clientes, credenciais, tokens da Meta, senhas ou backups do banco de dados.

Manter configurações sensíveis fora do Git, utilizar acessos restritos por central e evitar o registro em logs de URLs de encaminhamento que contenham CPF. Utilizar dados fictícios nos ensaios e respeitar as obrigações aplicáveis da LGPD.

## Documentação técnica

| Documento | Conteúdo |
| --- | --- |
| [Fluxo de pós-venda Baratão](<baratão moveis.md>) | Roteiro, mensagens, regras, etapas e decisões vigentes |
| [Banco de dados](core/database/README.md) | DDL, catálogo e migrações |
| [Consumo Meta](deploy/consumo_mensal_meta.md) | Apuração, coleta e relatórios |
| [Workers](workers/README.md) | Responsabilidades e distinção entre serviços atuais e legados |
| [Testes](tests/README.md) | Cobertura, execução e resultados registrados |
| [Rotina de deploy](regras_deploy/rotina_deploy.md) | Procedimentos operacionais |
| [Padrões de arquitetura](PADROES_DE_ARQUITETURA.md) | Referência dos padrões herdados da base anterior |
| [Regras de negócio](REGRAS_DE_NEGOCIO.md) | Turnos, repetição, bloqueio e recuperação do varejo |
| [Versionamento](VERSIONAMENTO.md) | Histórico da base de código |

O documento de fluxo do Baratão e o catálogo SQL vigente devem orientar as regras do novo atendimento. Documentos e módulos herdados do Supera não devem ser interpretados como funcionalidades ativas do Baratão sem confirmação no código atual.

## Licença

Consulte o arquivo [LICENSE](LICENSE) para os termos de licenciamento do repositório.
