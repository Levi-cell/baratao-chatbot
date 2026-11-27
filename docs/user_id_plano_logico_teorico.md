# Identidade do cliente no WhatsApp do Baratão

**Implementado no projeto em 26/11/2026.** A fila aceita telefone ou BSUID identificado. A publicação no banco existente requer o [SQL consolidado de remetente, identidade e etapas](../deploy/migrations/20261126_pendencias_baratao_etapas_sequenciais.sql). O [SQL das sete etapas](../deploy/migrations/20261126_baratao_sete_etapas.sql) aplica a numeração atual sobre a base de nove etapas. O plano prático contém o código integral dos arquivos. A habilitação da rota empresarial WAAC real segue o calendário da Meta. [Implementação](user_id_plano_logico_pratico.md) · [Cronograma da plataforma](../CRONOGRAMA_META_2027_2028.md)

## Qual identificador usar

| Informação de entrada | Decisão para o atendimento |
|---|---|
| Apenas WA ID | Usar o telefone. Abrir toda nova conversa pedindo o nome do titular. |
| WA ID e BSUID do mesmo remetente | Usar WA ID e vincular o BSUID comprovado à pessoa no escopo empresarial da central. Guardar a mensagem que forneceu a evidência. |
| Apenas BSUID, sem telefone comprovado | Aceitar a entrada e responder pelo BSUID. O bot exige o compartilhamento oficial do contato para prosseguir na coleta. O encaminhamento universal é a saída assistida para quem não concluir. |
| Apenas BSUID já ligado a um telefone vigente | Tentar o WA ID conhecido. A omissão do telefone em um webhook, por si só, não invalida o cadastro. |
| Falha definitiva específica do destinatário telefônico, com BSUID comprovado e vigente | Pedir reconfirmação pelo BSUID uma vez. Suspender o envio ao telefone anterior enquanto a confirmação estiver pendente. Conservar etapa, assunto, pedidos e histórico. |
| Username presente em evento autenticado | Guardar o último valor observado no cadastro global do cliente, com o instante da observação. Uma reentrega antiga ou um campo omitido não apaga nem reverte um valor mais recente. |

O BSUID é texto opaco. A Meta o vincula ao negócio e pode regenerá-lo quando o cliente muda de número. Isolar vínculos por central enquanto o escopo empresarial comum não estiver verificado. Tratar os eventos oficiais `user_changed_number` e `user_changed_user_id` com validação do vínculo anterior antes de aceitar o novo. Nome, CPF, nota e username não autorizam fusão. O username pode aparecer em `contacts[].profile.username`; o estado armazenado significa “último observado”. [Identificadores e mudanças de número na Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids)

## Conciliação do cliente provisório

Uma resposta oficial ao botão pode revelar um número já cadastrado. O telefone identifica o contato do WhatsApp; o titular desta compra é declarado novamente. O webhook exige assinatura validada, a solicitação em aberto da mesma central, o BSUID e a prova de compartilhamento. Confere o WAMID de contexto quando presente. O telefone do envelope, quando presente, deve coincidir com o do cartão.

Após o bloqueio vencer, se a ficha provisória representa apenas o atendimento em curso e o cadastro do telefone não tem atendimento concorrente nem BSUID vigente conflitante na central, o webhook conserva o ID antigo do cliente. Move a conversa para o chat canônico, reassocia a fila e o alias e remove a ficha provisória na transação da entrada. O histórico, o ID da conversa, o contador e a solicitação de contato continuam os mesmos. O worker envia a pergunta do CPF usando o primeiro nome recém-informado. O cadastro global recebe os dados desta compra; as conversas encerradas conservam seus próprios dados.

Um cartão de terceiro, número digitado, bloqueio vigente, outro vínculo incompatível ou conflito de conversas impede a associação automática. A regra de turno e o bloqueio de segurança são consultados para as duas identidades.

## Abertura e solicitação obrigatória

Toda nova conversa começa pelo nome completo do titular, inclusive após os 90 dias. Se a resposta ao nome veio apenas pelo BSUID, pedir o contato oficial e, após a confirmação, o CPF desta compra. Com WA ID disponível, o CPF vem logo após o nome. A regra é igual para clientes antigos e novos. O resumo usa a cópia do atendimento atual. Uma conversa ativa mantém a etapa que já alcançou.

Na primeira interação, inclusive se vier mídia ou pedido de humano, apresentar o Theo e a primeira pergunta do percurso. Usar `obter_saudacao_por_horario()` na abertura e uma única apresentação por conversa. Na primeira solicitação de contato, apresentar o botão oficial da Meta. O texto explica a necessidade do telefone sem atribuir ao cliente uma configuração de privacidade que o bot não consegue observar.

> Ana, para continuar seu atendimento, preciso confirmar seu número de WhatsApp. Toque no botão abaixo para compartilhá-lo comigo.

> Para seguir com o atendimento, toque no botão abaixo e compartilhe seu número de WhatsApp.

> Obrigado por compartilhar seu contato Ana! Em uma única mensagem, me informe o CPF do titular da compra.

O nome coletado é o do **titular da compra**. Por decisão do Baratão, nas próximas etapas o Theo usa a primeira palavra desse nome para se dirigir a quem escreve, mesmo quando for outra pessoa. Usar o vocativo onde soar natural, sem duplicá-lo no mesmo turno. O cadastro conserva o nome completo. Perguntar se o interlocutor é o titular fica para uma análise futura.

Enquanto aguarda o contato, validar primeiro o compartilhamento oficial. Confirmado o contato, agradecer e fazer a próxima pergunta pendente. Nas demais entradas, um pedido textual de humano encaminha. Mídia repete o botão com o aviso de texto. Texto inválido também repete o botão. A apresentação da solicitação não consome tentativa; depois de três repetições sem avanço, a quarta entrada novamente inválida encaminha. Uma prova válida nessa entrada resolve a pendência. O envio dos contatos humanos respeita o produto conhecido e, após confirmação do envio, aplica o bloqueio interno de 90 dias, inclusive ao provisório identificado só por BSUID. Reentregas não contam como novos turnos.

## Reconfirmação em qualquer etapa

A falha da API nem sempre diz algo sobre o telefone. Timeout, indisponibilidade, erro de permissão, limite de taxa ou de janela e o código genérico `131026` não provam mudança de número. Uma aceitação com WAMID é registrada e aguarda recibo. Não reenviar automaticamente pelo segundo identificador quando a primeira tentativa tem resultado incerto. Para trocar de rota, exigir evidência inequívoca da troca ou da rejeição específica do endereço, correlacionada à tentativa e à central. Registrar o motivo. No plano prático atual, a evidência que suspende o telefone é o evento oficial de mudança de identidade. O Theo solicita a reconfirmação pelo BSUID na próxima mensagem do cliente e mantém a mesma conversa. Um novo código de recusa da API só deve habilitar esse comportamento quando a Meta documentar que ele identifica o telefone inválido sem ambiguidade. [Códigos de erro da Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/support/error-codes)

Uma mídia de contato só vale como prova se for do mesmo remetente e da mesma conversa com solicitação pendente, trouxer `origin=contact_request` e exatamente um WA ID utilizável. Número digitado e cartão de terceiro não bastam. Enquanto o botão está pendente, um telefone que reapareça no envelope, sozinho, também não conclui a solicitação. Ao confirmar, restaurar a etapa e reapresentar a pergunta pendente. Reconciliar vínculos sob lock, respeitar bloqueios preexistentes e preservar as informações já aceitas. O histórico mantém o destinatário de cada tentativa. O painel pode apresentar o nome ou username conforme a autorização da central. O BSUID fica interno.

## Rota da central

Separar a escolha da pessoa da escolha do remetente. Para a central, manter `id_central` no banco, o Phone Number ID no cadastro e o valor da conta de mensagens em `waba_id`. No envio, esse valor segue como `messaging_account_id`. O adaptador usa o WAAC ID validado quando cadastrado e o Phone Number ID enquanto estiver ausente. Preparar e testar a rota nova antes do prazo da Meta. Um erro HTTP não deve alternar o remetente nem produzir um segundo envio. A troca de versão exige homologação também para webhook, cadastro de números, bloqueios e métricas, cada qual com seu contrato. A remoção da rota antiga depende de evidência de descontinuação e de todas as centrais já estarem migradas. [Evolução das contas na Meta](https://developers.facebook.com/documentation/business-messaging/whatsapp/account-model-evolution/)

O [plano prático](user_id_plano_logico_pratico.md) detalha os arquivos e os ensaios para a implantação futura.

No cronograma publicado em novembro de 2026, a Meta prevê disponibilizar o WAAC ID na fase do primeiro semestre de 2027. Ele tem relação de um para um com o Phone Number ID, mas recebe outro valor. A previsão para exigir o WAAC ID nas rotas que hoje apontam para telefone é o primeiro semestre de 2028. O ID da WABA existente é reaproveitado como ID da conta de mensagens. Se o token alcançar várias contas de mensagens no mesmo número, informar a conta explicitamente evita atribuir o envio à conta errada. Durante a implantação, obter o WAAC ID real de cada central quando a Meta disponibilizá-lo e homologar antes da troca obrigatória. [Cronograma das contas](https://developers.facebook.com/documentation/business-messaging/whatsapp/account-model-evolution/) · [Seleção da conta para envio](https://developers.facebook.com/documentation/business-messaging/whatsapp/account-model-evolution/messaging/)


## Verificação de entrada e proteção por identidade

Nos seis formatos com WA ID ou BSUID, a presença ou ausência de username preserva a decisão de rota. Username isolado e evento sem os três campos recebem HTTP 200 e ficam fora da fila. Cada item do lote conserva a conta, o número empresarial e o WAMID. O webhook verifica a assinatura antes de interpretar o corpo. Um recibo de entrega ou leitura pode atualizar o username quando a conta, o envio e o destinatário estão correlacionados.

O turno usa o ID interno do cliente e a central. Sem fila aberta, aceita a entrada. Com entrada pendente ou em processamento sem resposta confirmada, aguarda. Quando todas as entradas abertas já têm resposta confirmada, pode aceitar uma nova mensagem mesmo durante a recuperação. A comparação temporal respeita os segundos fornecidos pela Meta. O WAMID impede contar a reentrega duas vezes.

A proteção contra flood consulta as rotas já vinculadas ao cliente. A rajada de 15 WAMIDs distintos em cinco segundos pode atravessar telefone e BSUID. O sistema grava a intenção de bloqueio antes de chamar a Meta e mantém o bloqueio local se o serviço remoto recusar. A próxima entrada já marcada permite repetir a chamada remota. O encaminhamento comercial tem um prazo de 90 dias no sistema.
