# Testes do Baratão na VM Ubuntu

Na raiz da revisão em ensaio, rode `sudo -u chatbot bash deploy/testar_ubuntu.sh`. O script requer Python com as dependências do projeto, PostgreSQL de teste com `pg_virtualenv` e o utilitário `createdb`. Ele cria um cluster descartável e três bancos separados para fluxo, consumo e Admin. O envio à Meta é simulado. Com `BARATAO_TEST_REDIS_SOCKET`, a suíte do Admin exercita o caminho de cache com um Redis de teste. [Ambiente](../AMBIENTE_DESENVOLVIMENTO.md) · [Script](../deploy/testar_ubuntu.sh)

| Verificação | Onde localizar |
| --- | --- |
| Abertura, validação e payload enviado ao WhatsApp | Testes por etapa, de digitação e de remetente em [tests](.) |
| Quarta repetição, avanço e reset, mídia em todas as coletas | [Testes do dispatcher](test_etapa1_pos_venda.py) e [ciclo com PostgreSQL](test_etapa1_pos_venda_postgres.py) |
| BSUID, compartilhamento, conciliação, recuperação e ordem | [Integração do webhook e do worker](test_etapa1_pos_venda_postgres.py) |
| Contador contabilizado após o envio, retomada sem repetir efeito, mapa de transições e migrações reaplicáveis | [Suíte transacional](test_etapa1_pos_venda_postgres.py) |
| Cadastro de central, provisionamento simulado e publicação no cache | [Admin e PostgreSQL](admin_central_postgres.py) |

Para a Beta V0.2.0, o ensaio na VM usou PostgreSQL e Redis descartáveis e executou a descoberta geral e a suíte do Admin. As verificações em produção cobrem a revisão instalada, o catálogo e a disponibilidade dos serviços.
