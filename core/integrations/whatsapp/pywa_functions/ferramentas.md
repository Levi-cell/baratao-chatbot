# Recursos do WhatsApp usados pelo Theo

| Recurso | Uso no atendimento |
| --- | --- |
| Texto | Saudação, CPF, detalhes e correções. Uma mídia recebida gera aviso de texto e a pergunta atual. |
| Botões de resposta e lista | Produto tem três botões. Assunto tem uma lista. A coleta de pedidos oferece o botão “Perdi a nota”. A repetição por mídia reapresenta esses controles. |
| Solicitação de contato | O cliente que precisa comprovar telefone recebe o botão oficial. O worker valida a prova e retoma a pergunta pendente. |
| Indicador de digitação | É acionado uma vez antes da primeira resposta efetiva do turno. Falha do indicador permite prosseguir com o envio. |
| CTA e carrossel | Com um setor identificado, enviar um único CTA de URL. Para os dois setores, enviar dois cartões com imagens e um CTA em cada cartão. O link abre o rascunho da conversa com o consultor. |

Os [senders](pywa_senders) constroem os payloads e devolvem a confirmação externa para persistência. Os [textos](../messages) e [resolvers](../../../../workers/worker_flow/response_flow/etapas) definem o conteúdo e a decisão de fluxo. O worker de consumo utiliza uma consulta separada da API da Meta. [Guia de consumo](../../../../deploy/consumo_mensal_meta.md)
