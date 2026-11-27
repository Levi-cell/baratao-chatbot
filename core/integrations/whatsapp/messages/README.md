# Mensagens do Theo

O [roteiro do pós-venda](<../../../../baratão moveis.md>) define o texto mostrado ao cliente. Os arquivos desta pasta contêm o corpo das mensagens, os rótulos dos botões e as opções da lista. O sender usa esses componentes para montar o envio, o resolver decide a resposta e o worker registra os efeitos.

| Etapa | Conteúdo |
| --- | --- |
| 1 | [Nome completo do titular](etapa1_messages.py) |
| 2 | [CPF do titular](etapa2_messages.py) |
| 3 | [Tipo de produto](etapa3_messages.py) |
| 4 | [Assunto do atendimento](etapa4_messages.py) |
| 5 | [Pedidos ou nota perdida](etapa5_pedidos_messages.py) |
| 6 | [Detalhes da situação](etapa6_detalhes_messages.py) |
| 7 | [Encaminhamento ao pós-venda](encaminhamento_pos_venda.py) |

A [solicitação de compartilhamento de contato](compartilhamento_contato.py) intervém quando o fluxo precisa confirmar o telefone. O tratamento universal usa o mesmo encaminhamento final, com os dados coletados até aquele turno.

O [aviso de mídia](tratamentos/midia.py) acompanha a pergunta da etapa e os controles interativos correspondentes. A quarta resposta consecutiva inválida usa o encaminhamento final.
