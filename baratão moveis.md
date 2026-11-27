# Baratão Móveis — pós-venda com o Theo

A central atende clientes das lojas Baratão e Atacadão. Um chat reúne um cliente e a central de pós-venda. Cada nova conversa começa pelo nome do titular e coleta novamente o CPF. O titular pode ser diferente de quem escreve. A filial de compra vem do sufixo da nota.

**Beta V0.3.0.** Sete etapas e 21 transições. [Fluxograma do atendimento](docs/fluxograma_atendimento.md) · [Fluxograma da arquitetura](docs/fluxograma_arquitetura.md)

## Roteiro do cliente

A cada entrada, localizar o chat do cliente com a central e retomar a conversa ativa antes de pensar em abrir outra. Respeitado o bloqueio vigente, toda nova conversa começa pelo nome na etapa 1. Não reabrir a conversa encerrada; criar outra no mesmo chat.

| Passo | O que o cliente recebe | Resposta e efeito |
| --- | --- | --- |
| 1 · Nome | “Boa tarde, eu sou o Theo, assistente do pós-venda do Baratão e Atacadão! 😁<br><br>Olha antes de começarmos peço que envie somente mensagens de texto!  Caso você não seja o titular da compra, recomendamos que direcione esse atendimento para o titular, caso foi você que fez a compra ignore este aviso.<br><br>Antes de te encaminhar para um atendimento humano, preciso coletar algumas informações suas tá ? vai levar apenas alguns minutos, para começar, me informe o nome completo do titular da compra.” A saudação acompanha o horário. | Guardar o nome completo validado. Não interpretar a entrada que disparou a apresentação como resposta ao nome. |
| 2 · CPF | Com telefone disponível, “Certo Carlos. Em uma única mensagem, me informe o CPF do titular da compra.” Após compartilhar o contato, “Obrigado por compartilhar seu contato Ana! Em uma única mensagem, me informe o CPF do titular da compra.” Usar o primeiro nome do titular. | Extrair os 11 dígitos e guardar o CPF declarado no atendimento. Na V0.3.0, a [conciliação do cadastro](docs/conciliacao_cliente_por_cpf.md) escolhe o ID definitivo e reúne o histórico por central. |
| 3 · Produto | “Sobre qual tipo de produto você quer falar?” | Botões **Apenas Estofados**, **Apenas Móveis** e **Estofados e Móveis**; rodapé **Selecione apenas uma opção abaixo.** Etiquetas **Estofados**, **Móveis** e **Ambos**. |
| 4 · Assunto | “Certo, sobre qual assunto você quer falar? Selecione apenas uma opção.” | Registrar o assunto na conversa e avançar para a etapa 5. |
| 5 · Pedidos | “Me informe o número do pedido que aparece na sua nota.” | Extrair os números válidos ou aceitar **Perdi a nota**, por botão ou texto. |
| 6 · Situação | “Certo, estamos quase lá! 😁<br><br>Para podermos te ajudar da melhor forma possível, descreva com o máximo de detalhes a sua situação e o que você precisa.” | Salvar o relato deste atendimento. |
| 7 · Encaminhamento | Apresentar o contato de Móveis, o de Estofados ou os dois, conforme o produto desta conversa. | Aplicar a variante do produto e enviar uma mensagem com um botão ou um carrossel de dois cartões. Registrar os números apresentados depois do aceite da Meta. |

A lista de assunto usa títulos curtos, com a explicação na descrição da opção.

| Título | Significado apresentado | Etiqueta |
| --- | --- | --- |
| Previsão de entrega | Quero falar sobre a previsão de entrega do meu produto | Entrega |
| Avarias no produto | Meu produto veio com avarias | Assistência |
| Preciso de um montador | Preciso de um montador | Montador |
| Dois ou mais assuntos | Duas ou mais opções acima | Misto |
| Outros | Outros | Outros |

O cliente também pode digitar. “Previsão de entrega” identifica Entrega. “Previsão de entrega e montagem” identifica Misto. “Outra coisa” e “outro assunto” identificam Outros. Quando a resposta não corresponde a uma opção, o bot pergunta “Olha, não consegui entender. Sobre qual assunto você quer falar?” e apresenta as cinco opções novamente. Respostas à antiga opção combinada “Mais de um ou outros” também reapresentam a lista para esclarecer a escolha.

**Cliente que retorna.** Pedir novamente nome e CPF do titular. Atualizar o cliente e a cópia no atendimento. O resumo usa somente os dados desta conversa. Uma conversa já ativa continua na etapa persistida.

**Correção e encaminhamento.** Após a saudação, uma mídia repete a pergunta com o aviso de texto. Uma correção usa o mesmo contador da etapa. Um texto com “humano” ou a quarta resposta consecutiva inválida leva à etapa 7. Resposta válida avança e zera a contagem. O encaminhamento usa o produto confirmado nesta conversa.

**Encaminhamento na etapa 7.** Um único produto recebe seu botão. Ao concluir a coleta com um único produto, o Theo diz “Obrigado pelas informações. Use o botão abaixo para falar com o pós-venda.” No encaminhamento antecipado com um único produto, usa a frase do setor indicada abaixo. Com ambos os produtos ou sem produto confirmado, a mensagem inclui um carrossel de dois cartões.

| Produto desta conversa | Mensagem de saída | Contatos registrados |
| --- | --- | --- |
| Apenas móveis | “Para falar sobre seus móveis, toque abaixo.” Botão **Pós-venda Móveis**. | Número de Móveis usado no botão. |
| Apenas estofados | “Para falar sobre seus estofados, toque abaixo.” Botão **Pós-venda Estofados**. | Número de Estofados usado no botão. |
| Ambos | O Theo explica que a compra inclui estofados e móveis e apresenta o contato dos dois setores. | Registrar ambos os contatos no mesmo encaminhamento. |
| Produto ainda não informado | O Theo explica que ainda não conseguiu identificar o produto e oferece o contato de cada setor. | Registrar ambos os contatos e manter o produto em aberto. |

O carrossel orienta a deslizar para ver as duas opções. Cada cartão tem uma foto sem legenda e o nome do setor no botão. O envio possui um único WAMID. Cada URL abre o setor correspondente com o resumo da conversa.

O resumo usa os dados do atendimento no formato definido em “Relato, aviso e resumo para o consultor”. O telefone do setor define o destino do botão. Codificar o texto do link, conferir o destino e evitar registrar em log a URL que contém o CPF. Encerrar a conversa e marcar **Encaminhadas** depois que a Meta aceitar todos os envios previstos. Até a confirmação do conjunto no banco, a conversa continua aberta. Os números apresentados ficam gravados no atendimento. O cliente ainda precisa enviar a mensagem à equipe escolhida.

## Etapas e mapa de transição

IDs vigentes: 1 nome, 2 CPF, 3 produto, 4 assunto, 5 pedidos, 6 detalhes e 7 encaminhamento. A etapa 7 é a única terminal. A primeira resposta que apresenta uma pergunta não conta como repetição.

| Origem | Evento | Destino |
| --- | --- | --- |
| 1 · Nome | `nome_valido_falta_cpf` | 2 · CPF |
| 2 · CPF | `cpf_valido` | 3 · Produto |
| 3 · Produto | `produto_escolhido` | 4 · Assunto |
| 4 · Assunto | `assunto_escolhido` | 5 · Pedidos |
| 5 · Pedidos | `pedidos_assistencia` ou `nota_perdida_assistencia` | 6 · Detalhes |
| 5 · Pedidos | `pedidos_demais_assuntos` ou `nota_perdida_demais_assuntos` | 6 · Detalhes |
| 6 · Detalhes | `situacao_informada` | 7 · Encaminhamento |
| Cada etapa de 1 a 6 | `humano_solicitado` ou `limite_sem_avanco` | 7 · Encaminhamento com os dados disponíveis |

Cada alternativa “ou” e cada origem da última linha representa um registro separado. Uma entrada inválida pede correção e mantém a etapa. Recuperar uma conversa ativa mantém a etapa gravada. Esses dois casos dispensam uma aresta de transição. O par origem e evento é único. Vários eventos podem levar da mesma origem ao mesmo destino, por exemplo, um pedido informado e uma nota perdida. Cadastros importados também começam pelo nome.

## Repetições, bloqueio e retorno

A primeira entrada apresenta o Theo e pede o nome, inclusive se chegar áudio ou pedido de humano. Depois disso, mídia e formatos não aceitos recebem aviso de texto e a pergunta que o cliente estava respondendo. Produto, assunto e nota conservam botões ou lista. Na solicitação de telefone, o botão oficial de compartilhamento volta a aparecer. Texto com “humano” segue diretamente para o encaminhamento.

As três primeiras entradas inválidas consecutivas geram correções. O limite é compartilhado entre mídia e erros da etapa. Na quarta entrada, uma nova falha encaminha com o resumo parcial. Uma resposta válida avança e zera o contador. A contagem da solicitação de contato fica na pendência própria. O replay da mesma mensagem e a falha de envio não consomem outra tentativa.

Com o encaminhamento confirmado, o banco registra o encerramento e o Redis recebe o prazo restante do bloqueio interno de 90 dias. Móveis ou Estofados recebe apenas o botão do setor. Quem escolheu ambos ou ainda não informou produto recebe um carrossel com os dois contatos. O bloqueio antiabuso no webhook é independente.

## Relato, aviso e resumo para o consultor

Nos assuntos Assistência e Misto, o aviso instrui a tirar fotos e vídeos e ir pessoalmente à loja da compra, informa os 90 dias contados do recebimento e orienta quem já foi à loja e está na garantia a desconsiderar o aviso. Todos os assuntos seguem do pedido para o relato e o encaminhamento.

Cada link abre o WhatsApp do setor com um rascunho editável. O texto começa com “Olá, boa tarde! Fui encaminhado(a) pelo assistente Theo e gostaria de atendimento humano.” A saudação varia conforme o horário de São Paulo no momento do encaminhamento. Após uma linha em branco, cada dado coletado aparece em um tópico, na ordem titular da compra, CPF do titular, produto, assunto e número da nota. Cada número aparece com o nome cadastrado da filial entre parênteses. Com duas ou mais notas, o tópico “Números das notas” lista cada número e sua filial em uma linha própria. A escolha “Perdi a nota” ocupa esse mesmo campo. O relato do cliente aparece após outra linha em branco, como parágrafo livre, preservando suas quebras de linha. A entrada que aciona o tratamento universal não conta como relato. Os dois contatos de “Móveis e Estofados” recebem o mesmo rascunho quando o cliente abre os respectivos botões.

O nome do titular pode vir sozinho ou em apresentação própria ou de terceiro. “Eu me chamo Ana Maria Silva” e “O nome dele é João-Pedro da Silva” conservam os sobrenomes. Um prefixo sem nome completo volta à pergunta da etapa 1.

## Pedidos, dados e filtros

- O formato é `[0-9]+[.][0-9]{2}`. Todo número precisa terminar com o código de dois dígitos de uma filial cadastrada. “Meus pedidos são 0012.09 e 987.29.” identifica dois pedidos, cada um de uma filial. Preservar os zeros da esquerda. A pontuação da frase fica fora do número. Letras ou sinais dentro do identificador, como em `AB12.09`, `12.09X`, `1.2.09` ou `12-3.09`, impedem sua extração.
- A etapa 5 valida a resposta inteira antes de registrar os pedidos. Em “234.01 e 345.1”, o segundo pedido tem formato inválido e a primeira nota também aguarda o reenvio. Um código de filial ausente, como `.04`, tem o mesmo efeito. Em “comprei 2 cadeiras no pedido 234.01”, o 2 é uma quantidade.
- Com uma nota inválida, ou sem uma nota identificável, o Theo responde “Olha, não consegui identificar uma nota válida. Me fala novamente a nota, por favor.” Com duas ou mais notas informadas e qualquer erro, responde “Olha, uma ou mais notas estão inválidas. Digite todas novamente, por favor.” O botão **Perdi a nota** acompanha as duas mensagens.
- A nova resposta define o conjunto a gravar. Se o cliente reenviar só uma nota válida, o atendimento avança com essa nota. Cada resposta recusada conta como um turno sem avanço. O quarto turno encaminha ao humano conforme o produto escolhido.
- “Perdi a nota” por texto ou pelo próprio botão é a única escolha sem número. Os códigos marcados “APENAS CONSULTA”, o depósito e as lojas de feirão fazem parte do catálogo informado. A descrição da loja pertence ao pedido. A central de atendimento é a mesma para todas as filiais. O [catálogo de filiais](core/database/deploy_database/catalogo.sql) conserva as denominações do ERP.
- Cada nota tem um número de pedido. Guardar o número declarado em `pedido_conversa`, como texto, com chave primária `(id_conversa, numero)`. Uma conversa aceita vários números. O mesmo número pode aparecer em outra conversa do mesmo cliente ou de outro cliente. Uma repetição dentro da mesma conversa continua sendo um único registro. Usar o chat da conversa para consultar seu histórico de pedidos. A igualdade entre números declarados por pessoas diferentes não comprova que as compras sejam a mesma. Na mesma transação, vincular os números aceitos e registrar `perdeu_nota=false`, ou registrar `true` sem números. Nulo significa que o cliente ainda não respondeu.
- **Melhoria futura com o ERP Objetivo.** Quando houver integração, verificar como o ERP identifica a compra, a loja, o número da nota e o titular, e se os números são reutilizados. Hoje a informação do cliente é declaratória. A validação com o ERP poderá complementar o registro original, preservando os atendimentos antigos e permitindo tratar divergências.
- Confirmar nome e CPF em cada conversa. Produto, assunto, pedido e relato pertencem ao atendimento. As colunas legadas de visita e cidade preservam dados históricos.
- Buscar as conversas do chat com mensagem **do cliente** dentro do período selecionado, escolher a de início mais recente (desempate por ID) e **só depois** aplicar as etiquetas. Essa ordem evita que um atendimento antigo de entrega reapareça quando o último foi de montagem. O histórico do chat pode reunir várias conversas. Os filtros e a lista respeitam a central do operador.
- As etiquetas de assunto e produto nascem das respostas. O operador pode acrescentar ou retirar etiquetas complementares de assunto na conversa. Exibir a união sem duplicatas. Uma correção no assunto principal deve ser explícita e distinguível da adição de uma etiqueta. Derivar **Encaminhadas** dos motivos finais de encaminhamento e não de texto digitado ou clique presumido.
- Decisão atual de 22/11/2026: manter a janela gratuita, a reserva mensal Meta, as mensagens cobradas e a **cobertura adicional de 1.000 mensagens da ESL Tech**, com o mesmo filtro mensal, organização visual, histórico e PDFs. Esta decisão substitui a anterior que retirava a cobertura ESL. O coletor usa `central_pos_venda`/`id_central` e só processa centrais ativas; o painel lê somente o banco da central autenticada. A cobertura ESL é uma divisão das mensagens cobradas, não um abatimento no total informado pela Meta. Valores de referência não representam fatura real. A integração atual lê volumes SERVICE; os campos opcionais de valor e moeda existentes são preservados, sem preenchimento inventado.
- O DDL final mantém separado o período de 72 horas e a reserva Meta. A migração [20261122_consumo_meta_varejo.sql](deploy/migrations/20261122_consumo_meta_varejo.sql) restaura esses campos no banco já convertido para varejo, preservando o total gratuito antigo. Quando a divisão não existe, a tela/PDF mostram detalhamento pendente até uma coleta válida. Não atribuir todo o agregado a uma categoria nem mostrar saldo desconhecido como zero. A primeira recoleta não consolida automaticamente um mês antigo; continua valendo a conferência do dia 25. Consulte o [guia de consumo](deploy/consumo_mensal_meta.md).

## Implementação e evolução

O cadastro global recebe nome e CPF, e o atendimento guarda sua própria cópia para o resumo. O número da nota pode aparecer em diferentes conversas; a confirmação junto ao ERP Objetivo continua como evolução futura. O painel consulta dados por central. Algumas consultas antigas de relatórios ainda requerem adaptação.

[Identidade do cliente e reconfirmação](docs/user_id_plano_logico_teorico.md) · [SQL e migrações](core/database/README.md) · [Mensagens enviadas](core/integrations/whatsapp/messages/README.md)
