# Baratão Móveis — chatbot de pós-venda

Projeto de pós-venda, com uma central de pós-venda que recebe os clientes de todas as lojas e os encaminha às equipes de Móveis e de Sofás. Este documento reúne as mensagens, o mapa de etapas e o DDL de referência. O DDL, o catálogo e as migrações estão versionados. As etapas 1 (nome), 2 (CPF), 3 (produto), 4 (assunto) e 6 (pedidos), o tratamento universal compartilhado e suas dependências de persistência no worker estão implementados. A etapa 2 apresenta o produto na etapa 3. O retorno já reaproveita nome e CPF e abre diretamente na etapa 3. A etapa 3 valida e salva o produto e apresenta a lista de assuntos na etapa 4. A etapa 4 salva o assunto do atendimento e apresenta a pergunta de pedidos. A etapa 6 valida os pedidos pela filial e apresenta a próxima pergunta. O processamento das respostas de visita à loja (7) e de detalhes (9), a adaptação integral do webhook e as abas de conversas/relatórios continuam pendentes. O worker de consumo, a aba Consumo e seus PDFs já foram adaptados ao varejo, com migração SQL própria. Este documento distingue regras planejadas da entrega atual.

## Decisão vigente de etapas — 25/11/2026

- **1:** saudação e nome completo; a primeira entrada sempre recebe as regras.
- **2:** CPF; um retorno com nome e sem CPF já começa nesta pergunta.
- **3:** produto — Estofados, Móveis ou Ambos. Nome e CPF já cadastrados levam a uma nova conversa diretamente nesta etapa, sem perguntar cidade.
- **4:** assunto do atendimento. Uma escolha válida leva à pergunta da etapa 6 sobre o número do pedido.
- **6:** validar os números dos pedidos e suas filiais ou registrar a opção “Perdi a nota”. Assistência leva à pergunta de visita à loja (7). Os demais assuntos levam à pergunta de detalhes (9).
- **11:** encerramento depois de confirmar o envio dos contatos; bloqueio de 90 dias apenas no sistema, por cliente × central. Depois do prazo, uma nova mensagem pode abrir outra conversa.

Cidade saiu do fluxo. Produto ocupa 3 e assunto ocupa 4. Permanecem 6 pedidos, 7 visita à loja, 8 visita pendente, 9 detalhes e 11 encerramento; os IDs 5 e 10 não têm uso. O catálogo tem 9 etapas e 29 transições; não é necessário que os IDs sejam consecutivos.

Os números 2.1, 2.2 etc. do roteiro abaixo identificam os passos do rascunho, não são IDs do banco. No banco, o passo de produto é 3 e o encerramento é 11.

O efeito **digitando** permanece no mecanismo compartilhado do worker: uma solicitação antes da primeira resposta efetiva do turno, após as verificações de processamento. Aplica-se também à saudação, correções de entrada inválida e encaminhamento. Replay, mensagem bloqueada ou resolução sem envio não aciona o indicador. Falha do indicador não impede a resposta nem grava um turno adicional.

Na limpeza das etapas iniciais foram removidos o validador de apresentação do Supera, seu contexto de unidade/agente, mensagens/sender de abertura FireAds, coordenador e persistência da coleta de abertura e ramos de repetição das antigas etapas 1/2. As funções genéricas de lock, fila, rollback e recuperação foram mantidas. O helper de e-mail FireAds e seu extrator puro continuam apenas como dependências dos módulos legados de outras etapas ainda não portadas. Os antigos arquivos de produto na etapa 4 também foram retirados após a mudança para 3.

Para um banco já migrado até 18/11, aplicar [20261122_etapas_produto_encerramento.sql](deploy/migrations/20261122_etapas_produto_encerramento.sql) com os serviços parados. Ela remapeia conversas e histórico, preserva WAMIDs e datas de encerramento e substitui o mapa. Em seguida aplicar [etapa 3 e assunto](deploy/migrations/20261122_etapa3_produto_assunto.sql). Cada complemento é reaplicável no seu estado de destino; não executar o anterior depois do mais recente. Não executar os complementos antigos depois dela. O DDL continua apenas com CREATE; não foi preciso alterar colunas. Nenhuma migração foi aplicada em produção nesta revisão.

Validação de 22/11: **82 testes aprovados**, sendo 56 unitários/arquitetura e 26 com PostgreSQL local. Cobrem retorno completo/parcial, saudação com retry, contador, bloqueio, digitando, migração de conversas antigas e preservação do prazo. Esse resultado antecedeu a entrega completa de produto descrita ao final; o dispatcher não executa os resolvers Supera com IDs coincidentes.

## Organização mantida na virada — revisão de 21/11/2026

Descontinuar o Supera significa trocar o atendimento e retirar funcionalidades
sem uso no varejo. O padrão determinístico, as camadas, a organização dos
arquivos, os comentários e o ciclo transacional permanecem.

| Responsabilidade | Local atual |
| --- | --- |
| IDs e eventos do fluxo portado | `core/etapas_pos_venda.py`; autorização no mapa SQL. |
| Mensagens por etapa | `core/integrations/whatsapp/messages/etapaN_messages.py`. |
| Sender por etapa | `core/integrations/whatsapp/pywa_functions/pywa_senders/etapaN.py`. |
| Validação contextual | `workers/worker_flow/response_flow/etapas/validadores_contexto/valida_etapaN.py`. |
| Extração pura de nome/CPF/produto/assunto | `core/validacoes/nome_titular.py`, `cpf_titular.py`, `produto_pos_venda.py` e `assunto_pos_venda.py`. |
| Coordenação e mapa antes do envio | `resolver_etapaN.py`. |
| Efeitos explícitos por etapa e evento | `workers/worker_flow/transacoes/efeitos_transicao.py`. |
| SQL por funcionalidade | `core/repositories/`, em funções que recebem cursor. |
| Commits, rollbacks e ciclo de atendimento | `workers/worker_flow/response_flow/flow_worker.py`. |

Nome só é persistido pelo evento autorizado da etapa 1. CPF só é persistido
pelos eventos autorizados da etapa 2. Conferir chaves e valores complementa
essas condições; enviar uma chave isolada não autoriza gravá-la. Repetições
possuem ramos explícitos e não sobrescrevem cadastro. Seu contador comum
continua sendo incrementado uma única vez na persistência da resposta.

A pergunta do produto fica nos arquivos da etapa 3. A coleta da cidade foi retirada do fluxo em 22/11/2026. Produto agora é validado na etapa 3 e leva à lista de assuntos da etapa 4. A etapa 4 valida o assunto e envia a pergunta de pedidos. A etapa 6 registra a resposta e envia a pergunta da etapa 7 ou 9. O dispatcher continua
recusando o processamento das etapas seguintes ainda não portadas. A mensagem universal, os rótulos dos
cartões e a composição do resumo dos links têm módulo compartilhado em
`messages/encaminhamento_pos_venda.py`.

SQL que estava em carregadores de contexto, efeitos, entrada da fila do
webhook, coleta de consumo, comparação de bloqueios e teste de conexão foi
isolado nos repositórios. A extração dos consumidores ainda legados não migra
seus nomes de tabelas/colunas para varejo; a adaptação integral desses
consumidores permanece uma tarefa própria.

### O que significa recuperação neste fluxo

Não há etapa técnica de abertura. Uma conversa nova começa em 1 se faltar nome,
em 2 se faltar apenas CPF, ou em 3 quando ambos estiverem presentes. O histórico
de respostas confirmadas distingue apresentação de resposta à pergunta. A
primeira entrada não é interpretada como resposta a uma pergunta ainda não feita.
A etapa 11 é exclusivamente encerramento com bloqueio interno de 90 dias.

Exemplo de recuperação: o bot recebe o CPF, envia a pergunta do produto e
confirma CPF, resposta e avanço no banco. Se cair antes de concluir a fila,
a nova tentativa encontra essa resposta, não envia outra pergunta nem
reaplica efeitos, e termina a parte pendente. Quando houver encerramento,
ele também é concluído antes de materializar o bloqueio no cache.

Essa proteção depende de o checkpoint ter sido confirmado. Se a Meta aceitar
uma mensagem e o processo cair antes do commit da resposta, pode ocorrer
duplicação na recuperação. Esse limite permanece, inclusive o risco já
aceito para as duas mensagens da etapa final planejada.

Nesta reorganização, `movimento_conversa.py` permaneceu intacto, assim como
`flow_worker.py`, `persistencia_resposta.py`, os tratadores de erros externos,
os locks e o repositório da fila. As remoções anteriores de FireAds e
follow-up do ciclo foram aceitas; nenhuma proteção de concorrência foi
retirada nesta revisão.

Validação: **66 testes aprovados** — 36 das etapas, 11 de arquitetura/efeitos e
19 do worker real com PostgreSQL local isolado. Meta e Redis simulados;
nenhuma mensagem real ou alteração em produção. A reorganização não altera
DDL ou catálogo e não exige uma nova migração SQL.

## Serviços e responsabilidades

| Componente | Responsabilidade na Baratão |
| --- | --- |
| Webhook | Identificar o número empresarial, validar a origem das requisições, reconhecer reentregas da Meta, aplicar proteção contra flood, receber texto e interações e enfileirar a entrada. Uma mídia recebida produz um evento para o fluxo. O conteúdo binário não é necessário para o atendimento. |
| Worker de fluxo | Reservar a mensagem, recuperar o contexto, respeitar a ordem do turno do cliente, consultar o mapa por etapa e evento, validar a resposta, enviar a próxima mensagem e confirmar o resultado. Reaproveitar o ciclo principal com seus limites de transação. Adaptar os repositórios, o sender, os resolvers, os validadores, as mensagens e os pontos de extensão específicos do Supera. |
| `worker_consumo_meta` | Adaptado para central/mês, agenda persistida e coleta de volumes Meta. Mantém os três grupos e a cobertura ESL Tech de 1.000 mensagens. Não participa do turno do chatbot. |
| Site de monitoramento | Autenticar e limitar o acesso à central. Oferecer histórico por chat, seleção de período, etiquetas, filtros, relatórios aplicáveis ao pós-venda e consumo Meta. O atendimento humano acontece nos números de destino. |

Funil de vendas, consultas FireAds, origens de anúncios, triagem cognitiva, satisfação e follow-ups do Supera ficam fora deste desenho. Para o contador, um turno é uma entrada aceita do cliente e a resposta do bot confirmada no banco. A fila também preserva a ordenação e impede sobreposição de processamento no mesmo atendimento. A preferência de horário do treinamento do Supera era outra regra.

## Quem pode iniciar o atendimento

O canal atende clientes. Para uma primeira versão, propõe-se uma lista de números internos da empresa, mantida pela operação e consultada antes de abrir um atendimento. Um telefone desconhecido pode pertencer a um cliente novo. O cargo de uma pessoa não pode ser inferido de seu texto ou telefone. Um bloqueio interno é uma decisão da empresa. Um bloqueio confirmado pela Meta tem registro próprio.

O chat representa um cliente em contato com uma central de pós-venda. Hoje uma única central atende todas as lojas. Cidade não é mais perguntada nem usada para escolher a etapa inicial.

O WhatsApp identifica o contato. O titular da compra pode ser outra pessoa. O cadastro global guarda nome completo e CPF, e o atendimento conserva sua cópia. Nome e CPF são salvos a cada avanço confirmado. Aceitar o mesmo titular em contatos diferentes. Armazenar CPF como texto de 11 dígitos ASCII, preservando zeros iniciais, sem cálculo de dígitos verificadores ou consulta à Receita. Telefone e CPF declarado não comprovam identidade. As colunas de cidade já existentes permanecem para preservar registros anteriores; não fazem parte da coleta atual nem impedem retornar na etapa 3.

## Roteiro do cliente

A cada entrada, localizar o chat do cliente com a central e retomar a conversa ativa antes de pensar em abrir outra. Uma nova conversa começa diretamente em 1, 2 ou 3 conforme nome e CPF já cadastrados, depois de respeitar o bloqueio vigente. Não reabrir a conversa encerrada; criar outra no mesmo chat.

| Passo | O que o cliente recebe | Resposta e efeito |
| --- | --- | --- |
| 2.1 · Nome | “Olá eu sou o Theo, assistente do pós-venda, antes de te passar para um consultor humano, vou precisar fazer algumas perguntinhas para entender melhor como podemos te ajudar, vai levar apenas alguns minutos, para começar me informe o Nome completo do titular da compra.” Uma linha em branco antes de “Nota: por aqui consigo entender apenas mensagens de texto.” | Guardar o nome completo validado. Não interpretar a entrada que disparou a apresentação como resposta ao nome. |
| 2.2 · CPF | “Certo agora em uma única mensagem me informe seu CPF.” | Extrair um CPF com 11 dígitos, guardando apenas os números no cadastro e no atendimento. |
| 2.4 · Produto | “Sobre qual tipo de produto você quer falar?” | Botões **Apenas Estofados**, **Apenas Móveis** e **Estofados e Móveis**; rodapé **Selecione apenas uma opção abaixo.** Etiquetas **Estofados**, **Móveis** e **Ambos**. |
| 2.5 · Assunto | “Certo, sobre qual assunto você quer falar? Selecione apenas uma opção.” | Registrar o assunto na conversa e avançar para a etapa 6. |
| 2.6 · Pedidos | “Me informe o número do pedido que aparece na sua nota. Se tiver mais de um, pode mandar todos na mesma mensagem. Pode procurar com calma. Se perdeu a nota, é só avisar.” | Extrair os números válidos ou aceitar **Perdi a nota**, por botão ou texto. |
| 2.7 · Avarias | “Em caso de avaria, pedimos que tire fotos e vídeos do produto e vá pessoalmente à loja onde fez a compra para abrir um chamado. Você já foi à loja?” | Botões **Sim, já fui à loja** e **Ainda não fui**. As fotos e os vídeos são para apresentar na loja. |
| 2.8 · Visita pendente | “Entendi. Em caso de avaria, por uma questão de protocolo e segurança, precisamos que você vá primeiro à loja onde fez a compra. Depois da visita, pode voltar por aqui se o assunto continuar pendente.” | Confirmado o envio, encerrar esta conversa. A próxima mensagem abre outra imediatamente. |
| 2.9 · Situação | “Certo, agora me conte em uma única mensagem mais detalhes da situação.” | Salvar o relato deste atendimento. |
| 2.10 · Encaminhamento | Agradecer pelas informações e apresentar o contato de Móveis, o de Sofás ou os dois, conforme o produto desta conversa. | Aplicar a variante do produto e enviar uma ou duas mensagens. Registrar os números apresentados depois do aceite da Meta. |

A lista de assunto usa títulos curtos, com a explicação na descrição da opção.

| Título | Significado apresentado | Etiqueta |
| --- | --- | --- |
| Previsão de entrega | Quero falar sobre a previsão de entrega do meu produto | Entrega |
| Avarias no produto | Meu produto veio com avarias | Assistência |
| Preciso de um montador | Preciso de um montador | Montador |
| Dois ou mais assuntos | Duas ou mais opções acima | Misto |
| Outros | Outros | Outros |

O cliente também pode digitar. “Previsão de entrega” identifica Entrega. “Previsão de entrega e montagem” identifica Misto. “Outra coisa” e “outro assunto” identificam Outros. Quando a resposta não corresponde a uma opção, o bot pergunta “Olha, não consegui entender. Sobre qual assunto você quer falar?” e apresenta as cinco opções novamente. Respostas à antiga opção combinada “Mais de um ou outros” também reapresentam a lista para esclarecer a escolha.

**Cliente que retorna.** Toda nova conversa com nome e CPF já cadastrados começa pelo passo **etapa 3 (produto)**, inclusive quando há uma conversa anterior encerrada. Usar “Olá, {nome}! Sobre qual tipo de produto você quer falar?” com os mesmos três botões do primeiro atendimento. Perguntar o produto novamente porque o cliente pode ter feito outra compra. Depois da escolha, apresentar a lista de assuntos da etapa 2.5. Se o cadastro estiver incompleto, coletar nome/CPF que faltam e seguir para 3. Se a conversa ainda estiver ativa, retomar a etapa gravada.

**Tratamento universal nas etapas 1 a 4 e 6 (implementado).** A primeira entrada recebe a apresentação da etapa inicial escolhida pelo cadastro. Depois da apresentação, mídia/tipo não suportado, texto contendo “humano” ou quarta entrada após três repetições consecutivas aciona o encaminhamento compartilhado. Antes de concluir a etapa 3, o produto ainda não foi escolhido: enviar os dois setores em carrossel, sem gravar produto. Na etapa 3, botões são encaminhados à validação específica; uma opção desconhecida repete a pergunta. Na etapa 4, o clique seleciona um assunto e o tratamento universal usa o produto registrado na conversa.

**Encaminhamento na etapa 2.10.** A central configura um WhatsApp para Móveis e outro para Estofados. Cada mensagem tem um botão de URL, sem foto ou template. Para um único setor, enviar uma mensagem. Para os dois setores, enviar duas mensagens consecutivas na ordem Estofados, depois Móveis.

| Produto desta conversa | Mensagem de saída | Contatos registrados |
| --- | --- | --- |
| Apenas móveis | “Para falar sobre seus móveis, toque abaixo.” Botão **Pós-venda Móveis**. | Número de Móveis usado no botão. |
| Apenas estofados | “Para falar sobre seu estofado, toque abaixo.” Botão **Pós-venda Estofados**. | Número de Estofados usado no botão. |
| Ambos | Primeiro enviar a mensagem **Pós-venda Estofados**. Depois enviar **Pós-venda Móveis**, cada uma com o resumo disponível no link. | Registrar o telefone correspondente a cada envio confirmado. |

Dentro da janela de atendimento, usar `interactive.type = cta_url` em cada envio. Para os dois setores, enviar Estofados e depois Móveis. A mesma transação confirma as duas respostas e o encerramento. A ordem no histórico identifica cada resposta. A recuperação continua no nível da entrada original. Uma falha entre o aceite externo e o commit pode levar ao reenvio de uma ou das duas mensagens. Esse risco foi aceito. [Botão de URL](https://developers.facebook.com/documentation/business-messaging/whatsapp/messages/interactive-cta-url-messages)

O resumo usa nome e CPF do titular e os dados desta conversa já coletados (produto, assunto, pedidos ou nota perdida, visita e relato). Cidade não é coletada nem exigida para montar o resumo. Codificar o texto do link, conferir o destino e evitar registrar em log a URL que contém o CPF. Encerrar a conversa e marcar **Encaminhadas** depois que a Meta aceitar todos os envios previstos. Até a confirmação do conjunto no banco, a conversa continua aberta. Os números apresentados ficam gravados no atendimento. O cliente ainda precisa enviar a mensagem à equipe escolhida.

## Etapas e mapa de transição

IDs do catálogo vigente: 1 nome, 2 CPF, 3 produto, 4 assunto, 6 pedidos, 7 visita à loja, 8 visita pendente, 9 detalhes e 11 encerramento. Apenas 8 e 11 são terminais; 8 permite retorno imediato, 11 bloqueia por 90 dias. A criação da conversa escolhe 1, 2 ou 3 conforme o cadastro, sem aresta artificial de abertura. A primeira resposta na mesma etapa é apresentação, não correção e não conta repetição.

| Origem | Evento | Destino |
| --- | --- | --- |
| 1 · Nome | `nome_valido_falta_cpf` | 2 · CPF |
| 1 · Nome | `nome_valido_cpf_presente` | 3 · Produto |
| 2 · CPF | `cpf_valido` | 3 · Produto |
| 3 · Produto | `produto_escolhido` | 4 · Assunto |
| 4 · Assunto | `assunto_escolhido` | 6 · Pedidos |
| 6 · Pedidos | `pedidos_assistencia` ou `nota_perdida_assistencia` | 7 · Visita à loja |
| 6 · Pedidos | `pedidos_demais_assuntos` ou `nota_perdida_demais_assuntos` | 9 · Detalhes |
| 7 · Visita à loja | `loja_nao_visitada` | 8 · Visita pendente |
| 7 · Visita à loja | `loja_visitada` | 9 · Detalhes |
| 9 · Detalhes | `situacao_informada` | 11 · Encaminhamento/encerramento |
| Cada uma de 1, 2, 3, 4, 6, 7 e 9 | `midia_recebida` | 11 · Encaminhamento parcial (implementado em 1 a 4 e 6) |
| 1 · Nome, 2 · CPF, 3 · Produto, 4 · Assunto e 6 · Pedidos | `humano_solicitado` ou `limite_sem_avanco` | 11 · Encaminhamento parcial |

Cada alternativa “ou” e cada origem da última linha representa um registro separado. Uma entrada inválida pede correção e mantém a etapa. Recuperar uma conversa ativa mantém a etapa gravada. Esses dois casos dispensam uma aresta de transição. O par origem e evento é único. Vários eventos podem levar da mesma origem ao mesmo destino, por exemplo, um pedido informado e uma nota perdida. Para um cadastro importado completo sem atendimento anterior, o primeiro atendimento começa pelo produto.

## Contrato do tratamento universal para todas as etapas

Este contrato deve acompanhar a implementação de cada etapa. O código compartilhado já é usado pelas etapas 1 a 4 e 6; conectar as demais quando forem adaptadas, incluindo suas arestas no catálogo.

1. A primeira entrada recebe a saudação e a orientação de texto. Não validar essa entrada como nome nem encaminhar antes de explicar a regra.
2. Depois da saudação, encaminhar ao humano por mídia/tipo não suportado, por texto que contenha “humano” (sem distinguir maiúsculas) ou pela quarta entrada após três turnos consecutivos sem avanço. Respostas interativas válidas dos botões/listas do próprio bot devem seguir o fluxo de sua etapa.
3. Um turno contado exige entrada do cliente e resposta confirmada do bot, mantendo a etapa. Três respostas de correção deixam o contador em 3. Na próxima entrada, verificar o limite antes do validador específico e encaminhar. Avançar zera o contador; saudação, falha externa, rollback e replay não acrescentam repetição indevida.
4. O tratamento específico continua existindo: nome inválido repete a pergunta do nome e CPF inválido pede novamente o CPF. Ambos usam o mesmo contador de turnos; o limite não substitui os validadores.
5. Selecionar os contatos com base no produto **desta conversa**, sem reutilizar a escolha de uma compra anterior. Antes da escolha ou com **Ambos**, apresentar os dois setores. Com **Apenas estofados**, apresentar somente **Pós-venda Estofados**. Com **Apenas móveis**, apresentar somente **Pós-venda Móveis**. Ajustar também o texto ao setor escolhido. A etapa 4 já consulta o produto salvo para escolher o destino.
6. Encaminhamento antecipado tem o mesmo efeito do final: registrar os contatos efetivamente enviados, encerrar a conversa na etapa 11 e impedir novas conversas daquele cliente com aquela central por 90 dias. É um bloqueio temporário **somente no sistema**, contado de `finalizou_em`, com PostgreSQL como fonte de verdade e Redis como cache do prazo restante. Não bloquear o número na Meta por esse motivo, não renovar o prazo com novas tentativas e permitir nova conversa após expirar.
7. As proteções operacionais do webhook contra flood/abuso continuam sendo outro mecanismo. Quando suas próprias condições exigirem bloqueio na Meta, manter o bloqueio no sistema e a confirmação da API da Meta. A regra temporária de 90 dias não substitui nem remove essas proteções. A adaptação integral do webhook ao banco de varejo ainda está pendente.

## Pedidos, dados e filtros

- O formato é `[0-9]+[.][0-9]{2}`. Todo número precisa terminar com o código de dois dígitos de uma filial cadastrada. “Meus pedidos são 0012.09 e 987.29.” identifica dois pedidos, cada um de uma filial. Preservar os zeros da esquerda. A pontuação da frase fica fora do número. Letras ou sinais dentro do identificador, como em `AB12.09`, `12.09X`, `1.2.09` ou `12-3.09`, impedem sua extração.
- A etapa 6 valida a resposta inteira antes de registrar os pedidos. Em “234.01 e 345.1”, o segundo pedido tem formato inválido e a primeira nota também aguarda o reenvio. Um código de filial ausente, como `.04`, tem o mesmo efeito. Em “comprei 2 cadeiras no pedido 234.01”, o 2 é uma quantidade.
- Com uma nota inválida, ou sem uma nota identificável, o Theo responde “Olha, não consegui identificar uma nota válida. Me fala novamente a nota, por favor.” Com duas ou mais notas informadas e qualquer erro, responde “Olha, uma ou mais notas estão inválidas. Digite todas novamente, por favor.” O botão **Perdi a nota** acompanha as duas mensagens.
- A nova resposta define o conjunto a gravar. Se o cliente reenviar só uma nota válida, o atendimento avança com essa nota. Cada resposta recusada conta como um turno sem avanço. O quarto turno encaminha ao humano conforme o produto escolhido.
- “Perdi a nota” por texto ou pelo próprio botão é a única escolha sem número. Os códigos marcados “APENAS CONSULTA”, o depósito e as lojas de feirão fazem parte do catálogo informado. A descrição da loja pertence ao pedido. A central de atendimento é a mesma para todas as filiais. O [catálogo de filiais](core/database/deploy_database/catalogo.sql) conserva as denominações do ERP.
- Cada nota tem um número de pedido. Guardar o número declarado em `pedido_conversa`, como texto, com chave primária `(id_conversa, numero)`. Uma conversa aceita vários números. O mesmo número pode aparecer em outra conversa do mesmo cliente ou de outro cliente. Uma repetição dentro da mesma conversa continua sendo um único registro. Usar o chat da conversa para consultar seu histórico de pedidos. A igualdade entre números declarados por pessoas diferentes não comprova que as compras sejam a mesma. Na mesma transação, vincular os números aceitos e registrar `perdeu_nota=false`, ou registrar `true` sem números. Nulo significa que o cliente ainda não respondeu.
- **Melhoria futura com o ERP Objetivo.** Quando houver integração, verificar como o ERP identifica a compra, a loja, o número da nota e o titular, e se os números são reutilizados. Hoje a informação do cliente é declaratória. A validação com o ERP poderá complementar o registro original, preservando os atendimentos antigos e permitindo tratar divergências.
- Nome e CPF são reutilizados a partir do cadastro do cliente. As colunas antigas de cidade preservam o histórico, sem coleta nem validação de cidade no fluxo atual. Tipo de produto, assunto, visita, nota perdida, relato, cópia da identificação e números de destino apresentados pertencem ao atendimento. Detalhes parciais são válidos. Pelo mapa de pedidos, Assistência segue à pergunta sobre visita à loja. Entrega, Montador, Misto e Outros seguem ao relato.
- Buscar as conversas do chat com mensagem **do cliente** dentro do período selecionado, escolher a de início mais recente (desempate por ID) e **só depois** aplicar as etiquetas. Essa ordem evita que um atendimento antigo de entrega reapareça quando o último foi de montagem. O histórico do chat pode reunir várias conversas. Os filtros e a lista respeitam a central do operador.
- As etiquetas de assunto e produto nascem das respostas. O operador pode acrescentar ou retirar etiquetas complementares de assunto na conversa. Exibir a união sem duplicatas. Uma correção no assunto principal deve ser explícita e distinguível da adição de uma etiqueta. Derivar **Encaminhadas** dos motivos finais de encaminhamento e não de texto digitado ou clique presumido.
- Decisão atual de 22/11/2026: manter a janela gratuita, a reserva mensal Meta, as mensagens cobradas e a **cobertura adicional de 1.000 mensagens da ESL Tech**, com o mesmo filtro mensal, organização visual, histórico e PDFs. Esta decisão substitui a anterior que retirava a cobertura ESL. O coletor usa `central_pos_venda`/`id_central` e só processa centrais ativas; o painel lê somente o banco da central autenticada. A cobertura ESL é uma divisão das mensagens cobradas, não um abatimento no total informado pela Meta. Valores de referência não representam fatura real. A integração atual lê volumes SERVICE; os campos opcionais de valor e moeda existentes são preservados, sem preenchimento inventado.
- O DDL final mantém separado o período de 72 horas e a reserva Meta. A migração [20261122_consumo_meta_varejo.sql](deploy/migrations/20261122_consumo_meta_varejo.sql) restaura esses campos no banco já convertido para varejo, preservando o total gratuito antigo. Quando a divisão não existe, a tela/PDF mostram detalhamento pendente até uma coleta válida. Não atribuir todo o agregado a uma categoria nem mostrar saldo desconhecido como zero. A primeira recoleta não consolida automaticamente um mês antigo; continua valendo a conferência do dia 25. Consulte o [guia de consumo](deploy/consumo_mensal_meta.md).

## Contratos de recuperação para a futura implementação

1. Aceitar o evento de entrada uma vez por WAMID. A fila pode anteceder a conversa. Antes de vinculá-la, conferir o remetente e a central do chat. Se já houver histórico confirmado para aquele WAMID, recuperar o resultado sem abrir conversa ou enviar de novo, inclusive após a limpeza da fila.
2. Preservar o commit curto da reserva do item, a recuperação de item abandonado, a revalidação da central ativa, a proteção de ordem por cliente e número empresarial e os limites existentes para reagendamento, falha definitiva e turnos sem avanço. Uma central desativada conserva seus itens pendentes sem consumir tentativa. Uma mensagem atrasada já em processamento exige a segunda conferência de ordem no worker.
3. O lock da conversa vence após 110 segundos, com versão crescente por aquisição. Toda gravação protegida, renovação e liberação confere a versão. A fila recupera uma reserva de processamento após dois minutos. Respeitar o orçamento de tentativas do worker. A confirmação ou o reagendamento de um item também deve conferir que a reserva ainda pertence ao ciclo.
4. Preservar o vínculo entre entrada, resposta e etapa. Registrar a entrada antes da resposta. Confirmar resposta aceita, dados coletados, movimento, destino de encaminhamento e fechamento segundo os checkpoints do ciclo. No envio para os dois setores, uma queda após o aceite da Meta e antes do commit usa a recuperação do ciclo e pode causar duplicidade externa. Um índice no PostgreSQL impede duplicar um registro local, mas não pode desfazer um envio externo.
5. PostgreSQL é a fonte de verdade. Atualizar cache de contexto depois do commit, reler a conversa após adquirir o lock e recarregar o cadastro de centrais em caso de divergência de versão. Nesta proposta, a mudança da central incrementa a versão no banco via trigger. O adaptador deve ler a chave `centrais_pos_venda` e evitar um segundo incremento manual. Preservar degradação do controle de flood, deduplicação, registro de eventos e conciliação dos bloqueios com a Meta.
6. A função de reserva mantém as nove posições de retorno e os dois nomes legados relativos à unidade na interface SQL. As tabelas de negócio usam `central_pos_venda` e `id_central`. O histórico proposto tem unicidade global de WAMID e dispensa particionamento inicial. O payload interativo guarda botão, lista ou CTA necessário à remontagem do histórico. A consulta e o envio continuam a exigir os adaptadores adequados.
7. As tabelas de autenticação e sessões pertencem às migrations do Django. O DDL vincula o operador à central por FK para chatbot.auth_user e exclui seus vínculos quando o usuário é removido. O painel deve exigir esse vínculo para autorizar o acesso. Os templates, relatórios e permissões de etiqueta serão adaptados em outra entrega.

## Banco e implantação

O banco de destino continua sendo `db_chatbot`, no schema `chatbot`. O [DDL de instalação](core/database/deploy_database/schema.sql) descreve a estrutura final, somente com comandos `CREATE`. O [catálogo](core/database/deploy_database/catalogo.sql) carrega as 9 etapas e as 29 transições. A [migração do Supera](deploy/migrations/20261116_baratao_pos_venda.sql) altera o banco existente e inclui todas as instruções para executar a virada no DBeaver. Em uma base que já passou pela virada, aplicar apenas os complementos que ainda faltam, na ordem: [etapa 1 e bloqueio de 90 dias](deploy/migrations/20261118_etapa1_encaminhamento_90_dias.sql), depois [etapa 2 e eventos universais](deploy/migrations/20261118_etapa2_cpf.sql) depois [produto e encerramento](deploy/migrations/20261122_etapas_produto_encerramento.sql), [etapa 3 e assunto](deploy/migrations/20261122_etapa3_produto_assunto.sql), [etapa 4 e Misto](deploy/migrations/20261125_etapa4_assunto.sql) e [etapa 6 e filiais](deploy/migrations/20261125_etapa6_pedidos_filiais.sql). Não reaplicar a virada destrutiva.

Os dados do atendimento anterior ficam em um backup PostgreSQL externo ao projeto. As antigas unidades permanecem inativas para associar o consumo mensal e os bloqueios ao número correto. A central da Baratão inicia com cadastro e permissões próprios. O encaminhamento confirmado na etapa 11 bloqueia novas conversas daquele cliente com aquela central por 90 dias. A etapa 8, visita pendente, encerra sem bloqueio. Os [procedimentos do banco](core/database/README.md) descrevem a conferência do resultado e a restauração do histórico.

## Entrega da etapa 1 — 18/11/2026

### Nome e repetição

O validador aceita letras Unicode (incluindo acentos), espaços, hífen ASCII entre duas letras e um único ponto no final. Remove o ponto final e normaliza espaços antes de persistir. Pede ao menos duas partes para o nome completo; não usa lista de primeiros nomes e não comprova identidade. Aceita `João da silva.`, `João-Pedro da Silva` e `João-Pedro da Silva.`. Rejeita números, símbolos, emoji, hífen isolado ou separado por espaços e ponto no começo/meio ou repetido.

Entrada inválida recebe exatamente:

> Desculpa, não consegui entender, em uma única mensagem me informe apenas seu nome completo

A saudação não conta como repetição. Três turnos consecutivos sem avanço deixam `conversa.turnos_sem_avanco` em 3; a próxima resposta encaminha aos humanos. A verificação ocorre antes da validação do nome nessa quarta entrada. A persistência só conta uma resposta confirmada por WAMID. Reprocessar a mesma entrada não conta novamente. Uma transição confirmada zera o contador. Falha de envio ou rollback não consome uma repetição. O limite antigo de 12 foi substituído por 3 no banco e no repositório. O webhook não promove mais esse contador a bloqueio na Meta; as proteções de flood são independentes.

Nome válido é gravado no cadastro e na cópia do atendimento, na mesma transação do histórico e da passagem para a etapa 2. A mensagem enviada passou a ser “Certo agora em uma única mensagem me informe seu CPF.”. A validação de CPF está descrita na entrega da etapa 2 abaixo. O dispatcher recusa os resolvers antigos do Supera: coincidência de ID não autoriza reutilizar uma etapa antiga.

### Encaminhamento e cartões

Corpo aprovado para os três motivos (mídia, humano e limite de repetição):

> Olha como só consigo entender apenas mensagens de texto vou te enviar o contato dos nossos consultores humanos para o setor de móveis e de estofados

Uma única mensagem `interactive.carousel`, na ordem:

1. Imagem de sofá e botão **Pós-venda Estofados** → `central_pos_venda.telefone_sofas`.
2. Imagem de mesa/cadeiras e botão **Pós-venda Móveis** → `central_pos_venda.telefone_moveis`.

O WhatsApp controla o tamanho dos cartões e os apresenta lado a lado, com rolagem horizontal. As imagens ilustrativas têm proporção aproximada de 16:9, sem textos embutidos, e menos de 5 MB cada. Estão em `callback/monitoramento/static/monitoramento/img/pos_venda/`. Os links usam somente dados já validados. O texto inválido fornecido como nome não vai para o link. Nenhum número dos testes é usado como padrão de produção.

O SDK/API exige URLs públicas das imagens neste formato. Configurar `WHATSAPP_MIDIAS_BASE_URL` com a URL HTTPS da pasta pública, sem query string e sem autenticação, por exemplo `https://SEU-DOMINIO/static/monitoramento/img/pos_venda`. Publicar as imagens junto dos arquivos estáticos (`collectstatic` no deploy). Configuração ausente ou contatos incompletos interrompem o envio; a conversa não é encerrada como se os contatos tivessem sido enviados.

A decisão anterior de duas mensagens consecutivas na etapa final por produto permanece como plano dessa etapa. O carrossel está implementado para o tratamento universal compartilhado pelas etapas 1 a 4 e 6 quando há dois setores de destino. Ele produz um único WAMID e um único registro de resposta. Não foi introduzida recuperação por cartão.

### Encerramento, bloqueio e recuperação

A etapa 11 tem `bloqueio_dias = 90`, tanto para o encerramento final planejado quanto para o encaminhamento antecipado. A etapa 8 mantém zero. O motivo distingue `encaminhamento_midia`, `encaminhamento_humano` e `encaminhamento_sem_avanco`, além de `encaminhamento` normal e `visita_pendente`.

Os números realmente apresentados, o histórico com o evento interno `_fluxo.evento`, o contador e o avanço são confirmados juntos. O checkpoint seguinte encerra a conversa e conclui a fila. Só depois desse commit o Redis recebe o bloqueio. Uma queda entre os checkpoints recupera a resposta já gravada e conclui o encerramento sem reenviar.

A data inicial do bloqueio é `conversa.finalizou_em`, e novas tentativas do cliente não reiniciam o prazo. O bloqueio vale apenas para cliente × central; não bloqueia o atendimento no número humano nem chama a API de bloqueio da Meta. Após 90 dias, o mesmo chat poderá abrir outra conversa. Redis vazio ou indisponível provoca consulta ao PostgreSQL; a gravação do hash e de sua expiração no Redis é atômica. Os caches de cliente, central e bloqueio usam prefixo `baratao:` para não reaproveitar identificadores ou prazos do Supera.

### Migração e limite da entrega

Registro histórico: a [migração complementar de 18/11](deploy/migrations/20261118_etapa1_encaminhamento_90_dias.sql) é aplicada depois da virada de 16/11/2026. Ela restaura a coluna de bloqueio, configura 90 dias no antigo encaminhamento (10), reduz o contador e inclui os motivos/eventos novos. Depois do complemento de CPF, a migração de 22/11 remapeia esse encerramento para 11 sem reiniciar o prazo. Não reaplicar os complementos de 18/11 após essa mudança. Esses scripts não enviam mensagens nem alteram Redis. O DDL final continua contendo somente `CREATE` e já descreve a estrutura resultante.

Validação local: testes unitários, payload real do SDK com HTTP simulado e ciclo real do worker em PostgreSQL 18.3 isolado. A migração complementar foi comparada com o DDL novo e reaplicada. Não houve envio real no WhatsApp nem migração no banco de produção nesta entrega. O projeto ainda está sendo adaptado por etapas; não iniciar o atendimento completo antes de concluir webhook, demais etapas e painel.

## Entrega da etapa 2 — concluída em 20/11/2026

### Pergunta e correção de CPF

Ao confirmar o nome na etapa 1, apresentar exatamente:

> Certo agora em uma única mensagem me informe seu CPF.

A etapa 2 usa primeiro o tratamento universal compartilhado. Se ele não for acionado, extrair o CPF do texto. Aceitar o documento sozinho ou dentro de uma frase, com 11 dígitos numéricos ASCII. Os únicos separadores permitidos dentro do CPF são ponto (`.`) e hífen ASCII (`-`); ambos são opcionais, inclusive quando o cliente esquece apenas parte da formatação. Barras, letras, sublinhado, espaços e outros símbolos dentro do documento não são removidos para formar um CPF. Rejeitar o candidato inteiro, sem aproveitar um pedaço de algo como `01234567890@1`. A restrição vale para o documento extraído; o texto e a pontuação da frase ao redor continuam permitidos. Guardar como texto sem separadores, preservando zeros iniciais.

| Entrada de exemplo | Resultado |
| --- | --- |
| `012.345.678-90` | `01234567890` |
| `01234567890` | `01234567890` |
| `Meu CPF é 012.345678-90, obrigado.` | `01234567890` |
| `CPF: 012345.67890` | `01234567890` |
| 10 ou 12 dígitos, ou uma letra no lugar de um dígito | Pedir correção; não salvar nem avançar. |
| `012/345/678-90`, `012_345_678_90` ou `01234567890@1` | Pedir correção por caractere não permitido no documento. |
| Dois CPFs diferentes na mesma mensagem | Pedir novamente para evitar escolher o titular errado. |

Não aproveitar 11 dígitos de um número maior ou de um identificador misturado com letras. Não juntar números soltos pela frase. A repetição do mesmo CPF na mensagem não causa ambiguidade. A validação é de **formato e quantidade**, conforme aprovado: não calcula dígitos verificadores e não verifica existência ou regularidade do CPF em serviço externo.

Se não houver um CPF extraível sem ambiguidade, enviar exatamente:

> Olha você esqueceu de digitar algum digito ou colocou um digito a mais no CPF, por favor em uma única mensagem informe seu CPF novamente

Manter a etapa 2 e contar a repetição somente após confirmar a resposta. O quarto turno sem avanço encaminha ao humano pelo tratamento universal. Um CPF aceito antes desse limite zera o contador e avança.

### Persistência e próxima pergunta

Gravar `cliente.cpf_titular` globalmente e `atendimento_pos_venda.cpf_titular` como cópia da conversa, na mesma transação da resposta e da transição. O nome já coletado permanece em ambos os registros. Reaproveitar esse cadastro em novas conversas: nome e CPF presentes levam diretamente à apresentação do produto na etapa 3.

CPF válido avança para a etapa 3 e apresenta a pergunta de produto com os três botões aprovados, exista ou não cidade histórica no cadastro. A validação e persistência do produto foram implementadas na entrega de 22/11 descrita abaixo.

Falha no envio não salva o CPF nem avança. Queda antes do commit reverte CPF, histórico e transição juntos. Se o checkpoint da resposta já foi confirmado, o replay aproveita esse resultado, preserva o cadastro e não envia outra resposta nem incrementa novamente o contador.

### Catálogo e validação

Registro histórico: a [migração da etapa 2](deploy/migrations/20261118_etapa2_cpf.sql), iniciada em 18/11, acrescenta `humano_solicitado` e `limite_sem_avanco` com origem 2 e destino 10. `midia_recebida` já existia para a etapa 2. O arquivo é reaplicável, não altera colunas e não modifica dados de clientes. Requer a virada de varejo e o complemento da etapa 1. O complemento de 22/11 remapeia esses eventos para 11. Uma instalação limpa usa somente o DDL e catálogo atuais, sem reaplicar os complementos antigos.

Validação concluída em 20/11/2026: **54 testes aprovados**, sendo 35 unitários e 19 do ciclo real do worker em PostgreSQL 18.3 local. Cobrem formato, extração em frases, separadores ausentes, ambiguidade, zeros iniciais, mensagens exatas, encaminhamento universal, contador, persistência global e cópia do atendimento, rollback e replay. Meta e Redis são simulados. Em outro banco local descartável, a base da virada recebeu os dois complementos e foi comparada à instalação atual: colunas, 50 CHECKs, 11 etapas e 32 transições coincidiram; reaplicar o complemento da etapa 2 conservou o catálogo. Esta entrega não enviou mensagens reais nem aplicou migrações em produção.


## Entrega da etapa 3 — 22/11/2026

Pergunta: **Sobre qual tipo de produto você quer falar?**
Botões: **Apenas Estofados**, **Apenas Móveis**, **Estofados e Móveis**.
Rodapé nativo: **Selecione apenas uma opção abaixo.**
No retorno com cadastro completo, prefixar a pergunta com `Olá, {nome}!`.

Resposta inválida: **Não entendi, sobre qual tipo de produto você quer falar?**
Reapresentar os três botões e o mesmo rodapé, sem duplicar a orientação no corpo.

- Texto aceita palavras inteiras, sem distinguir caixa/acentos: móveis/móvel e estofados/estofado; sofá/sofás também identifica Estofados. Duas categorias, ambos ou dos dois identificam Ambos. Não aproveitar fragmentos de palavras como automóveis ou imóveis.
- Negar Móveis seleciona Estofados; negar Estofados seleciona Móveis. Negar os dois, contradizer a mesma categoria ou declarar dúvida repete a pergunta. Negativa de um problema, como “não recebi meus móveis”, não exclui o produto.
- Clique aceita somente IDs/rótulos das três opções. Rótulos antigos equivalentes são aceitos para botões já enviados. Opção interativa desconhecida repete a etapa; não é confundida com mídia.
- Tratamento universal precede a validação específica. Mídia, pedido textual contendo humano ou quarta entrada após três repetições confirmadas encaminha aos dois setores, encerra em 11 e aplica 90 dias internos. Até confirmar o produto na transição, não há setor escolhido neste atendimento.
- Avanço válido confirma `produto_escolhido: 3 → 4`, grava `atendimento_pos_venda.produto` e zera o contador pelo mecanismo comum. Não duplicar incremento/reset nos efeitos.
- `atendimento_pos_venda.id_conversa` é PK e FK: relação 1:1 já existente. Nome/CPF continuam globais; produto é exclusivo da conversa e começa nulo no próximo atendimento. Não criar tabela nem coluna redundante em `conversa`.
- Na entrega da etapa 3, o sender abriu a primeira versão da lista de assuntos. A etapa 4 agora processa as cinco opções descritas no roteiro acima.
- Arquitetura: textos em messages, envio no sender, extração pura em `core/validacoes`, validação contextual e decisão no resolver, bloco explícito `ETAPA_PRODUTO` nos efeitos e UPDATE isolado em `core/repositories/atendimento/pos_venda.py`. Nenhum commit/rollback foi transferido.
- Limpeza: substituído o validador Sim/Não de titular/dependente da etapa 3 do Supera; removidos o ramo antigo de repetição e constantes/evento sem consumidores. Migrações históricas permanecem como histórico, sem uso no runtime.
- Novo complemento SQL: `20261122_etapa3_produto_assunto.sql`, após `20261122_etapas_produto_encerramento.sql`. Move assunto de 5 para 4, preserva histórico/conversas e inclui os dois eventos universais faltantes da etapa 3. Não altera DDL nem reinicia bloqueios. Não aplicado em produção.

Validação desta entrega: **102 testes aprovados**, sendo 69 unitários/arquitetura e 33 com PostgreSQL local. Inclui botões/rodapé/lista, negações, bloqueio no quarto turno, reset ao avançar, produto isolado por conversa, rollback, replay e migração reaplicável. Meta e Redis simulados; sem mensagens reais ou alterações em produção. O servidor PostgreSQL local precisou ser iniciado na porta de teste correta antes da execução da integração.
