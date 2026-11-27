# Padrões de arquitetura do Baratão

O atendimento determinístico tem seis etapas de coleta e uma de encaminhamento. O catálogo do PostgreSQL autoriza as transições. A repetição é um resultado do próprio estágio, sem aresta de retorno no catálogo. [Fluxograma do sistema](docs/fluxograma_arquitetura.md)

## Responsabilidades por camada

| Camada | Responsabilidade |
| --- | --- |
| Webhook | Verificar envelope, assinatura, identidade empresarial e elegibilidade do turno. Resolver ou conciliar identidade com as provas disponíveis e inserir a mensagem uma vez na fila. |
| Worker de fluxo | Reservar a entrada, conferir ordem, obter e renovar o lock da conversa, carregar contexto e confirmar os checkpoints. Coordenar os rollbacks e as tentativas. |
| Validador | Extrair dados e decidir se a entrada é aceita. As regras puras ficam em `core/validacoes`. A adaptação ao contexto fica em `workers/worker_flow/response_flow/etapas/validadores_contexto`. |
| Resolver | Selecionar apresentação, correção ou transição permitida. Uma repetição por mídia usa o mesmo limite das demais correções da etapa. |
| Mensagem e sender | O texto, os rótulos e as opções pertencem a `messages`. O sender constrói o payload PyWa e devolve o WAMID e a representação que irá ao histórico. |
| Efeitos | Após o envio confirmado, aplicar os efeitos declarados por etapa, atualizar os dados coletados e o contador na mesma transação da resposta. Um replay usa o histórico. |
| Repositórios | As operações SQL de atendimento ficam em funções de domínio que recebem o cursor. O ciclo que abriu a transação decide o commit ou rollback. |
| Painel e consumo | Django controla o acesso por central. O worker de consumo consulta Pricing Analytics por período, com agenda própria e persistência da última leitura válida. |

## Cache

Cliente, mapa versionado de centrais, bloqueio temporário e proteções de entrada têm chaves próprias. O lock da conversa e a decisão de turno são do PostgreSQL. A publicação do bloqueio em Redis ocorre após o commit de encerramento. [Estratégias por domínio](core/cache/README.md)

## WhatsApp e PyWa

Conta de mensagens e número empresarial identificam a central. A seleção do destinatário considera WA ID, BSUID vigente e solicitação de contato pendente. Uma alteração de username atualiza metadados. A rota empresarial WAAC depende da habilitação e da configuração da central. [Identidade e reconfirmação](docs/user_id_plano_logico_teorico.md)

## Integrações externas

Falha antes do aceite da Meta, falha de banco após o aceite e queda após a confirmação local são situações diferentes. A última permite recuperar a resposta registrada. O intervalo entre aceite externo e persistência cria risco de envio duplicado. [Checkpoints e recuperação](workers/README.md)

## Configuração e segredos

Os serviços carregam o ambiente de `/etc/chatbot/chatbot.env`. O certificado de confiança do RDS acompanha a instalação Ubuntu. Os testes usam credenciais de ensaio e bancos descartáveis. [Configuração operacional](regras_deploy/modificando_env_e_banco_em_prod.md)

## Logging e exceções

No journal, acompanhe `fila_insert_ok`, `mensagem_processando` e `mensagem_processada` pelo mesmo `id_mensagem`. A referência opaca `ref_envio` relaciona o envio e um recibo de erro. O status local `sent` registra a conclusão da fila. A confirmação de entrega vem da Meta.

[Rotina para implementar etapas](ROTINA_IMPLEMENTACAO_ETAPAS.md) · [Regras de negócio](REGRAS_DE_NEGOCIO.md)
