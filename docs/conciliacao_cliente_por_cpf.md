# Qual cadastro fica com o histórico do titular

Na etapa 2, o Theo usa o CPF declarado do titular da compra e o telefone confirmado nesta conversa para escolher o cadastro definitivo. Isso também atende quem mudou de número. O nome serve para o atendimento e pode ter uma grafia diferente da registrada anteriormente.

## Como escolher o ID

| Resultado da busca antes de gravar o CPF atual | Decisão |
| --- | --- |
| Há ficha anterior com o mesmo telefone e CPF | Vence o maior `id_cliente` entre as fichas com os dois valores iguais. |
| Há ficha anterior com o mesmo CPF em outro telefone | Vence o maior `id_cliente` entre as fichas desse CPF. O telefone confirmado agora passa ao vencedor. |
| Nenhuma ficha anterior tem o CPF e o telefone está livre | O cadastro atual fica com o CPF e o telefone. |
| Nenhuma ficha anterior tem o CPF e outro cadastro já tem o telefone compartilhado | Vence o maior ID antigo com o telefone confirmado, inclusive se o CPF anterior estava vazio. O vencedor recebe o CPF declarado nesta conversa. |
| O atendimento termina antes de um CPF válido | O Theo encerra com os dados já coletados. A fusão depende da etapa de CPF. |

O intervalo entre atendimentos não determina a identidade. O bloqueio de 90 dias é verificado separadamente. O ID é sequencial e define “mais recente” neste desempate. Uma ficha criada nesta conversa chega à comparação sem CPF global e não concorre com os antigos. Se o webhook já reconheceu uma ficha antiga pelo telefone ou BSUID, ela pode participar com o CPF que possuía antes deste turno. A restrição de telefone único do PostgreSQL já impede duas fichas com o mesmo telefone preenchido.

## O que acontece com os perdedores

Entram na decisão apenas a ficha atual e as fichas que possuem o CPF declarado ou o telefone confirmado. Quando há vencedor, a ficha provisória e todas as fichas perdedoras cedem seus atendimentos, inclusive a que coincidia apenas pelo telefone e tinha outro CPF. Cada central conserva seu próprio chat com o vencedor. As conversas mantêm os IDs, as datas, as notas, o titular declarado no atendimento e as mensagens enviadas e recebidas. A consulta do histórico ordena as mensagens pela data original e usa o ID da mensagem como desempate.

O vencedor recebe o CPF declarado, o nome informado nesta conversa, o telefone confirmado e o username mais recente observado, quando disponível. O telefone anterior do vencedor deixa de ser seu contato. Um BSUID antigo aposentado continua no histórico de vínculos e deixa de autorizar envios. As referências da fila acompanham o vencedor. Só então o banco exclui os chats vazios e as fichas redundantes.

**Exemplo com número reaproveitado.** O ID 10 tinha o telefone atual e o CPF de Ana. Os IDs 20 e 30 tinham o CPF de Bruno em outros números. O provisório 40 compartilha o telefone do ID 10 e declara o CPF de Bruno. O ID 30 recebe o nome e o telefone atuais e reúne as conversas dos quatro IDs, cada uma em sua central. A consulta do atendimento antigo de Ana ainda mostra o CPF declarado naquela compra. Uma busca no cadastro global pelo CPF antigo de Ana já não encontra o ID 10. Se o ID 20 tivesse também o telefone confirmado e o ID 30 tivesse só o CPF, venceria o 20.

Se não existissem os IDs 20 e 30 nesse exemplo, venceria o ID 10 pelo telefone. Seu cadastro global passaria a representar Bruno e o atendimento anterior conservaria a declaração de Ana.

## Proteções e recuperação

O botão oficial comprova o contato para o fluxo privado. Enquanto o telefone está em disputa, o Theo fala com quem iniciou a conversa pelo BSUID. Após a fusão, usa o telefone confirmado para os próximos envios. O destinatário já gravado nas mensagens anteriores continua sendo o que a Meta recebeu.

O PostgreSQL serializa a decisão pelo CPF e pelo telefone e protege os registros envolvidos. Outra conversa ativa, uma fila concorrente, um turno fora de ordem ou bloqueios vigentes impedem a união naquele turno. Nesse caso o CPF declarado fica no atendimento e as fichas continuam separadas. Um novo atendimento elegível pode voltar a avaliar a situação. A fusão ocorre durante o atendimento, sem varredura que altere cadastros em massa.

As mudanças de cadastro, chats, conversas e fila fazem parte da mesma transação que registra a resposta da etapa. Falha antes do commit reverte o conjunto. O replay de uma resposta confirmada conserva o resultado. O Redis acompanha o commit e a resolução de uma entrada legada por telefone confere no PostgreSQL se o vínculo ainda vale.

[Plano teórico de identidade](user_id_plano_logico_teorico.md) · [Implementação por arquivo](user_id_plano_logico_pratico.md) · [SQL para a base V0.2.1](../deploy/migrations/20261127_contato_conferencia_cpf.sql)
