# Controle de pós-venda

A futura seção **Controle** acompanha o que acontece depois que o Theo encaminha o cliente ao atendimento humano. O operador encontra a última conversa do chat, vê as notas informadas e registra os produtos e quantidades que confirmou com o cliente. O PostgreSQL já guarda as notas e os itens desde a Beta V0.6.0 e a situação e a observação por conversa desde a V0.7.0. A planilha, os filtros, a edição e a janela de histórico fazem parte da proposta do painel.

## Como uma linha representa uma compra

Um chat reúne as conversas entre o cliente e a central. Cada conversa pode ter várias notas. Cada nota pode ter vários produtos, e cada produto vem de um único código do catálogo.

```text
Chat
 └─ Conversa
     ├─ Atendimento do Theo (titular, CPF, produto declarado, assunto)
     └─ Nota da conversa (id_nota, número, filial indicada pelo sufixo)
         └─ Item da nota (id_nota, codigo_produto, qtd)
             └─ Produto do catálogo (código, nome, categoria)
```

A nota tem um identificador interno estável, `id_nota`. Seu número impresso é único dentro da conversa. Se o cliente mencionar a mesma nota em um atendimento futuro, ela terá outro `id_nota` e seus itens poderão ser consultados no histórico da conversa correspondente. A quantidade pertence ao par **nota + código de produto**. Por exemplo, duas unidades do mesmo modelo formam uma linha com quantidade 2. Dois modelos com códigos diferentes formam duas linhas. Produtos com o mesmo nome comercial e códigos diferentes continuam distinguíveis.

## Exemplo de atendimento com “Ambos”

Ana informa “Ambos” e as notas `184.09` e `260.08`. O Theo conhece os números e as filiais. A distribuição de móveis e estofados entre as notas só será conhecida durante o contato humano. Ao abrir o Controle, o operador vê uma linha provisória por nota, com o nome e a quantidade do produto em branco. A coluna **Tipo do produto** pode mostrar “Ambos · informado no atendimento” enquanto o item está pendente. Essas linhas são montadas para exibição. A tabela `nota_produtos` ainda tem zero registros para essas notas.

Depois de conferir as compras, o operador pode chegar a esta planilha ilustrativa:

| Nota | Filial | Tipo do produto confirmado | Nome do produto | Quantidade |
|---|---|---|---|---:|
| 184.09 | Irecê | Estofado | Sofá | 1 |
| 184.09 | Irecê | Móveis | Mesa de jantar | 1 |
| 260.08 | Dias Dávila | Estofado | Poltrona | 2 |

Há uma conversa, duas notas, três itens e quatro unidades. Se a segunda nota também tiver um móvel, **Adicionar produto** nela cria a quarta linha. Se o cliente confirmar outra unidade da mesma poltrona naquela nota, a quantidade passa de 2 para 3. O relato original “Ambos” continua disponível na conversa.

## Situação do atendimento

| Situação | Quando aparece | Quem registra |
|---|---|---|
| Não encaminhado | Desde a abertura, enquanto o cliente está com o Theo. Uma tentativa de envio que falha mantém esta situação. | Banco, na criação da ficha |
| Já encaminhado | O envio dos contatos foi aceito pela Meta e o worker confirmou os destinos no banco, inclusive por tratamento universal. | Banco, na mesma transação do worker |
| Aguardando cliente | O operador enviou uma mensagem e aguarda a resposta do cliente. | Operador |
| Resolvido | O operador confirmou a conclusão do caso. | Operador |

Uma nova conversa recebe sua própria situação e sua própria observação, mesmo quando o chat já tem um atendimento resolvido. A recuperação do worker preserva as alterações do operador. O campo **Observação** guarda o acompanhamento humano. O campo **Detalhes** guarda o relato coletado pelo Theo.

## Geração da planilha e filtros

1. Considerar os chats das centrais que o operador tem permissão para consultar. Selecionar a conversa mais recente de cada chat por início da conversa, com o ID como desempate. Aplicar os filtros a esse resultado, de modo que uma conversa anterior dentro do período só apareça no histórico.
2. Permitir intervalo de datas (inclusive um único dia), filial, tipo do produto e busca no catálogo por nome ou código. A seleção de um produto específico usa o código do ERP. Como regra proposta, a data de referência é o início da conversa no fuso da central.
3. Permitir escolher as colunas visíveis. O conjunto proposto inclui **CPF**, **Nome Completo**, **Telefone**, **Nota**, **Tipo do produto**, **Nome do produto**, **Filial**, **Observação**, **Quantidade** e **Situação do atendimento**.
4. Exibir uma linha por item confirmado. Mostrar também atendimentos sem produto atribuído, inclusive sem nota e com “Perdi a nota”. Se o cliente fornecer a nota depois, o operador poderá registrá-la e vincular o primeiro produto. O filtro por produto específico encontra apenas itens atribuídos ao código escolhido. Para filtrar por tipo, distinguir o **tipo declarado na conversa** do **tipo confirmado no item**, evitando atribuir “Ambos” a todas as notas.
5. Oferecer **Ver histórico** na linha. Uma janela fechável apresenta as conversas daquele chat em ordem cronológica, com datas, dados informados em cada atendimento, notas e itens. Fechar a janela retorna à mesma posição na planilha e mantém os filtros.

## Edição durante o atendimento humano

- **Adicionar produto** abre uma linha vinculada à mesma conversa e nota. A linha reaproveita os valores comuns e começa com tipo e nome do produto em branco. O operador pode filtrar o catálogo por tipo e escolher o código. Ao salvar, a categoria e o nome vêm do produto escolhido. A quantidade inicial sugerida é 1.
- **Editar quantidade** grava o total de unidades confirmado. Para um código já presente na nota, a interface deve apresentar a linha existente e permitir informar o novo total. Isso evita somar duas vezes quando o operador repete um clique após uma falha de conexão.
- **Editar os campos de negócio** deve salvar a mudança no PostgreSQL e atualizar as demais linhas que compartilham aquele dado. Uma correção da nota vale para todos os seus itens. A filial é calculada pelos dois últimos dígitos da nota, de modo que editar a filial requer corrigir e validar o número. Escolher outro código altera o produto daquela compra. Uma correção no cadastro geral do produto teria alcance sobre todas as notas que o referenciam e merece uma ação própria.
- **Titular e contato** devem indicar se a edição vale para o atendimento selecionado ou para o cadastro global do cliente. Como o telefone e o CPF participam da conciliação de identidade, a sugestão é corrigir a ficha do atendimento por padrão e reservar a alteração global a uma ação explícita, com as verificações de identidade do projeto.
- **Situação e observação** pertencem à conversa. Uma alteração do operador é exibida em todas as linhas de notas e produtos daquele atendimento. A observação aceita texto livre e começa em branco.
- **Edição simultânea** deve avisar se outro operador já alterou a linha antes do salvamento. Para a implementação do painel, recomenda-se registrar o operador, o horário e os valores alterados. Datas de conversa, IDs internos e a mensagem original do cliente servem como referência para o histórico.

A contagem de atendimentos usa conversas distintas. A contagem de notas usa IDs de nota distintos e a de unidades soma as quantidades dos itens. Assim, acrescentar uma linha de produto atualiza o total de peças e preserva o total de clientes atendidos.
