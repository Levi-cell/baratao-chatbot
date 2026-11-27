# Django, webhook e monitoramento

O Nginx encaminha as requisições HTTPS ao Gunicorn. O mesmo serviço Django publica o callback, a autenticação, as consultas do painel e o Admin. O cliente fala com o WhatsApp da central. O atendente que recebe o encaminhamento continua a conversa pelo número do setor.

## Entrada do WhatsApp

1. O GET atende a verificação de assinatura do callback. No POST, o sistema verifica formato, tamanho e assinatura conforme a configuração e separa mensagens, recibos e eventos de sistema.
2. Uma mensagem precisa de identidade utilizável. A proteção do remetente e o controle de flood precedem a fila. O webhook confere central ativa e bloqueio temporário. Um evento ignorado pode receber HTTP 200. Uma falha recuperável de validação ou persistência pode retornar 503 para permitir reentrega.
3. O vínculo da identidade, a decisão de turno sob lock e a inserção idempotente pelo WAMID protegem contra eventos repetidos ou concorrentes. Uma mídia elegível entra na fila com o seu tipo. O worker decide qual pergunta repetir.
4. Recibos de entrega e leitura seguem a rotina de identidade. Uma falha de entrega gera um registro correlacionável e, quando elegível, reserva a reconfirmação do telefone. Eventos de sistema podem atualizar o vínculo do BSUID.

## Admin e painel

### Cadastro e edição da central

Em `/admin/`, o usuário da equipe precisa das permissões da operação. Em **Centrais de pós-venda**, configure o número empresarial, WABA, Phone Number ID, WAAC quando disponível e os contatos dos setores. Para ativar a central, informe dois destinos válidos e distintos para móveis e estofados.

- **Inclusão ou troca de identificador do remetente.** O formulário verifica o Redis, confirma o telefone na Meta, assina a conta para receber webhooks e registra o número. A gravação depende dessas confirmações.
- **Correção apenas do telefone comercial.** O Admin confere se o telefone corresponde ao remetente na Meta. A assinatura e o registro existentes são preservados.
- **Edição de nome, setores ou situação.** Essas alterações são locais. Após o commit de inclusão, edição ou exclusão, o Admin relê as centrais ativas no PostgreSQL e publica o mapa no Redis. O PostgreSQL conserva o estado que permite reparar o cache se a publicação falhar.
- **Exclusão.** A página de confirmação mostra as dependências. Vínculos de acesso e agenda de coleta podem acompanhar a exclusão. Chats, mensagens na fila, identidades, eventos de segurança, bloqueios e consumo mensal protegem o cadastro. Para interromper o atendimento de uma central com histórico, desative-a. A exclusão local preserva o registro do número na Meta.

### Consultas e desbloqueio

Os 22 modelos de negócio correspondem às tabelas do schema `chatbot`. O Admin oferece 14 listas principais. Abra uma **Central** para consultar seus acessos, identidades, bloqueios e consumo. Em **Conversas**, abra o atendimento para ver os pedidos, etiquetas e recuperações de contato. Fila, histórico, etapas e transições podem ser consultados diretamente. No bloqueio de segurança, a ação de desbloquear na Meta exige confirmação do provedor antes de remover o registro local. O prazo interno de 90 dias após encaminhamento é uma regra distinta. [Modelos](webhook/models.py) · [Consultas vinculadas](webhook/admin_relacoes.py)

### Painel do operador

O operador entra com uma conta ativa vinculada a uma única central ativa. O portal e o Admin têm controles de acesso próprios. A seção **Consumo** consulta os dados mensais persistidos pelo coletor. Algumas consultas e relatórios herdados do painel ainda precisam de adaptação ao varejo.

[Fluxo da arquitetura](../docs/fluxograma_arquitetura.md) · [Ingresso do webhook](webhook/services/post_flow.py) · [Rotas do painel](monitoramento/urls.py) · [Cache](../core/cache/README.md)
