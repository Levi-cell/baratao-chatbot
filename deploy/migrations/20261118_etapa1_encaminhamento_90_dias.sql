-- Executar depois de 20261116_baratao_pos_venda.sql, com o worker parado.
-- Não recria o banco/schema nem apaga clientes, histórico ou conversas.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(81024, 1);

DO $precondicoes$
BEGIN
    IF to_regclass('chatbot.central_pos_venda') IS NULL
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa = 10 AND nome_etapa = 'encaminhamento') THEN
        RAISE EXCEPTION 'Primeiro aplicar a migração de virada para Baratão.';
    END IF;
END
$precondicoes$;

LOCK TABLE chatbot.etapa, chatbot.etapa_transicao, chatbot.conversa IN ACCESS EXCLUSIVE MODE;

ALTER TABLE chatbot.etapa ADD COLUMN IF NOT EXISTS bloqueio_dias smallint NOT NULL DEFAULT 0;
UPDATE chatbot.etapa SET bloqueio_dias = CASE WHEN id_etapa = 10 THEN 90 ELSE 0 END;
ALTER TABLE chatbot.etapa DROP CONSTRAINT IF EXISTS etapa_bloqueio_dias_check;
ALTER TABLE chatbot.etapa ADD CONSTRAINT etapa_bloqueio_dias_check CHECK (bloqueio_dias IN (0, 90));
ALTER TABLE chatbot.etapa DROP CONSTRAINT IF EXISTS etapa_check;
ALTER TABLE chatbot.etapa ADD CONSTRAINT etapa_check CHECK (encerra_automaticamente OR bloqueio_dias = 0);

-- A virada anterior pode ter conservado os nomes dos CHECKs do legado.
DO $checks$
DECLARE item record;
BEGIN
    FOR item IN
        SELECT c.conname FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.conrelid = 'chatbot.conversa'::regclass AND c.contype = 'c'
          AND cardinality(c.conkey) = 1
          AND a.attname IN ('turnos_sem_avanco', 'motivo_encerramento')
    LOOP
        EXECUTE format('ALTER TABLE chatbot.conversa DROP CONSTRAINT %I', item.conname);
    END LOOP;
END
$checks$;
UPDATE chatbot.conversa SET turnos_sem_avanco = LEAST(turnos_sem_avanco, 3);
ALTER TABLE chatbot.conversa ADD CONSTRAINT conversa_turnos_sem_avanco_check
    CHECK (turnos_sem_avanco BETWEEN 0 AND 3);
ALTER TABLE chatbot.conversa ADD CONSTRAINT conversa_motivo_encerramento_check
    CHECK (motivo_encerramento IN ('visita_pendente','encaminhamento','encaminhamento_midia',
                                  'encaminhamento_humano','encaminhamento_sem_avanco'));

DELETE FROM chatbot.etapa_transicao WHERE id_etapa_origem = 11 AND evento = 'midia_recebida';
INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino)
VALUES (1, 'humano_solicitado', 10), (1, 'limite_sem_avanco', 10)
ON CONFLICT (id_etapa_origem, evento) DO UPDATE SET id_etapa_destino = EXCLUDED.id_etapa_destino;

COMMIT;

SELECT id_etapa, nome_etapa, encerra_automaticamente, bloqueio_dias
FROM chatbot.etapa WHERE id_etapa IN (1, 8, 10, 11) ORDER BY id_etapa;
