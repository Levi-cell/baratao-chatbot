# Workers do pós-venda

O webhook e o painel rodam no Gunicorn. A VM executa dois processos de trabalho.

| Serviço | Entrada | Responsabilidade |
| --- | --- | --- |
| Fluxo | [iniciar_flow_worker.py](worker_flow/iniciar_flow_worker.py) | Responder à fila da central e registrar os efeitos da conversa. |
| Consumo Meta | [iniciar_worker_consumo_meta.py](worker_consumo_meta/iniciar_worker_consumo_meta.py) | Consultar a Meta e atualizar os dados mensais do painel. |

## Ciclo da mensagem

O [worker de fluxo](worker_flow/response_flow/flow_worker.py) controla os commits, rollbacks e a conexão do ciclo. Depois de reivindicar uma entrada da fila, ele respeita a ordem das mensagens, valida a central e verifica o bloqueio do atendimento. Com o lock da conversa adquirido, vincula a entrada, relê a conversa e grava o histórico do cliente.

Antes de enviar, o worker renova o lock e verifica novamente a central. O [despacho](worker_flow/response_flow/flow_sender.py) consulta a resposta já registrada e chama o resolver da etapa quando precisa de uma nova resposta. O worker verifica a posse do lock ao persistir os efeitos e novamente ao finalizar a fila. O bloqueio temporário de encerramento chega ao cache após o commit no banco.

### Vínculo da fila com a conversa

O vínculo `fila_mensagens.id_conversa` é uma anotação de integridade e
ordenação; ele não é o lock de turno e não substitui a resolução atual por
`(cliente, central)`.

O repositório preenche o vínculo quando ele está vazio ou já aponta para a mesma
conversa. Um vínculo legado divergente só é reparado quando a fila ainda não tem
histórico. Se nenhuma linha puder ser vinculada com segurança, o worker falha
fechado: devolve a mensagem para `pending` por 300 segundos, sem consumir uma
tentativa de erro e sem enviar resposta.

Se a conversa anterior continuar ativa, a mensagem permanece na mesma conversa
e segue a etapa já atualizada. Se o encerramento tiver bloqueio vigente, a
mensagem é removida como conversa bloqueada. Uma conversa nova só é resolvida
quando o encerramento permite recomeço imediato (`bloqueio_dias = 0`) ou quando
o bloqueio já expirou.

As barreiras que continuam decidindo o atendimento são:

- advisory lock do turno por cliente e central no webhook;
- lock versionado da conversa no worker;
- verificação de mensagem anterior ainda aberta;
- `resposta_bot_para_mensagem_atual`, que impede novo envio em um retry.

## Retry e recuperação

- dequeue incrementa `retry_count`;
- `processing` abandonado volta a ser elegível após o timeout do banco;
- falhas tratadas usam `tratamento_erros_externos/expection_process.py`;
- o limite atual é de três tentativas;
- ao atingir o limite, a mensagem é excluída;
- retry com histórico do bot existente não chama a Meta novamente.

O worker mantém a fila sem `sent` quando envio ou persistência final falham.
Depois de uma resposta do bot persistida, o retry repara contexto e conclui a
fila sem duplicar o envio.

## Locks e ordenação

- apenas um worker processa a conversa por vez;
- `lock_version` impede unlock por proprietário antigo;
- uma mensagem posterior não ultrapassa outra anterior aberta;
- a verificação de mensagem anterior ocorre logo depois do claim, antes de
  resolver conversa e tentar seu lock;
- espera por mensagem anterior (30 segundos) ou lock recusado (5 segundos) não
  consome tentativa de erro.

## Consumo e operação

O worker de consumo tem um lock próprio para a coleta. Uma falha na API preserva a última leitura válida do painel. Consulte o [guia de consumo](../deploy/consumo_mensal_meta.md) e a [rotina de implantação na VM Ubuntu](../deploy/README.md).
