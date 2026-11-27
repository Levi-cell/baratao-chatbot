# Django, webhook e monitoramento

O Nginx encaminha as requisições HTTPS ao Gunicorn. O mesmo serviço Django publica o callback, a autenticação, as consultas do painel e o Admin. O cliente fala com o WhatsApp da central. O atendente que recebe o encaminhamento continua a conversa pelo número do setor.

## Entrada do WhatsApp

1. O GET atende a verificação de assinatura do callback. No POST, o sistema verifica formato, tamanho e assinatura conforme a configuração e separa mensagens, recibos e eventos de sistema.
2. Uma mensagem precisa de identidade utilizável. A proteção do remetente e o controle de flood precedem a fila. O webhook confere central ativa e bloqueio temporário. Um evento ignorado pode receber HTTP 200. Uma falha recuperável de validação ou persistência pode retornar 503 para permitir reentrega.
3. O vínculo da identidade, a decisão de turno sob lock e a inserção idempotente pelo WAMID protegem contra eventos repetidos ou concorrentes. Uma mídia elegível entra na fila com o seu tipo. O worker decide qual pergunta repetir.
4. Recibos de entrega e leitura seguem a rotina de identidade. Uma falha de entrega gera um registro correlacionável e, quando elegível, reserva a reconfirmação do telefone. Eventos de sistema podem atualizar o vínculo do BSUID.

## Admin e painel

O Admin da central administra a configuração empresarial e a ativação do atendimento. O cadastro e a alteração de remetente passam pelas validações da Meta; após o commit, o Admin publica o mapa de centrais ativas no Redis. O painel exige autenticação e vínculo com a central. O Consumo consulta dados mensais persistidos. Há consultas e telas de métricas herdadas cuja adaptação ao varejo é parcial.

[Fluxo da arquitetura](../docs/fluxograma_arquitetura.md) · [Ingresso do webhook](webhook/services/post_flow.py) · [Rotas do painel](monitoramento/urls.py) · [Cache](../core/cache/README.md)
