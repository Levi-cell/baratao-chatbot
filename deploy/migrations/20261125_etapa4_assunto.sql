-- Complemento após 20261125_complementos_baratao.sql. Executar o script inteiro.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '30s';

DO $precondicoes$
BEGIN
    IF NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa = 4 AND nome_etapa = 'assunto')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa = 6 AND nome_etapa = 'pedidos')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa = 11 AND encerra_automaticamente AND bloqueio_dias = 90)
       OR NOT EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem = 4 AND evento = 'assunto_escolhido' AND id_etapa_destino = 6)
       OR NOT EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem = 4 AND evento = 'midia_recebida' AND id_etapa_destino = 11)
    THEN
        RAISE EXCEPTION 'O catálogo anterior da etapa 4 deve estar aplicado.';
    END IF;
END
$precondicoes$;

ALTER TYPE chatbot.assunto ADD VALUE IF NOT EXISTS 'misto';
INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino)
VALUES (4, 'humano_solicitado', 11), (4, 'limite_sem_avanco', 11)
ON CONFLICT (id_etapa_origem, evento) DO NOTHING;

DO $destinos$
BEGIN
    IF (SELECT count(*) FROM chatbot.etapa_transicao
        WHERE id_etapa_origem = 4 AND id_etapa_destino = 11
          AND evento IN ('humano_solicitado', 'limite_sem_avanco')) <> 2 THEN
        RAISE EXCEPTION 'Destino de encaminhamento divergente para a etapa 4.';
    END IF;
END
$destinos$;
COMMIT;

SELECT evento, id_etapa_destino FROM chatbot.etapa_transicao
WHERE id_etapa_origem = 4 ORDER BY evento;
