-- Aplicar DEPOIS de 20261122_etapas_produto_encerramento.sql.
-- Webhook/worker parados; preserva fila, histórico, cadastro e bloqueios.
-- Reaplicável. Instalação limpa usa apenas schema.sql + catalogo.sql atuais.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(81024, 1);
LOCK TABLE chatbot.etapa, chatbot.etapa_transicao, chatbot.conversa,
           chatbot.historico_mensagens, chatbot.fila_mensagens
    IN ACCESS EXCLUSIVE MODE;

DO $migrar$
BEGIN
    IF EXISTS (SELECT FROM chatbot.conversa WHERE processing) THEN
        RAISE EXCEPTION 'Há conversas em processamento. Concluir recuperação e parar serviços.';
    END IF;
    IF NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=3 AND nome_etapa='produto')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=11
                      AND nome_etapa='encaminhamento' AND bloqueio_dias=90)
       OR EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=4 AND nome_etapa<>'assunto')
       OR EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=5 AND nome_etapa<>'assunto')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa IN (4,5) AND nome_etapa='assunto') THEN
        RAISE EXCEPTION 'Catálogo não reconhecido. Aplicar primeiro o complemento de produto/encerramento.';
    END IF;
    IF EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=5 AND nome_etapa='assunto') THEN
        -- O nome é único: liberar antes de criar o destino das referências.
        UPDATE chatbot.etapa SET nome_etapa='assunto_antes_etapa3' WHERE id_etapa=5;
        INSERT INTO chatbot.etapa(id_etapa,nome_etapa,encerra_automaticamente,bloqueio_dias)
        VALUES(4,'assunto',false,0);
        UPDATE chatbot.conversa SET id_etapa_atual=4 WHERE id_etapa_atual=5;
        UPDATE chatbot.historico_mensagens
        SET id_etapa=4, interativo=coalesce(interativo,'{}'::jsonb)
            || '{"_etapa_antes_produto_assunto":5}'::jsonb
        WHERE id_etapa=5;
        UPDATE chatbot.etapa_transicao SET id_etapa_origem=4 WHERE id_etapa_origem=5;
        UPDATE chatbot.etapa_transicao SET id_etapa_destino=4 WHERE id_etapa_destino=5;
        DELETE FROM chatbot.etapa WHERE id_etapa=5;
    END IF;
END
$migrar$;

INSERT INTO chatbot.etapa_transicao(id_etapa_origem,evento,id_etapa_destino) VALUES
    (3,'produto_escolhido',4),
    (3,'midia_recebida',11),
    (3,'humano_solicitado',11),
    (3,'limite_sem_avanco',11)
ON CONFLICT(id_etapa_origem,evento) DO UPDATE SET id_etapa_destino=EXCLUDED.id_etapa_destino;
COMMIT;

SELECT id_etapa_origem,evento,id_etapa_destino FROM chatbot.etapa_transicao
WHERE id_etapa_origem=3 ORDER BY evento;
