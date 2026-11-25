-- Complemento da etapa 2: executar após 20261118_etapa1_encaminhamento_90_dias.sql.
-- Não muda colunas nem dados de clientes; acrescenta eventos ao catálogo.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '30s';
SELECT pg_advisory_xact_lock(81024, 1);

DO $precondicoes$
BEGIN
    IF to_regclass('chatbot.central_pos_venda') IS NULL OR NOT EXISTS (
        SELECT FROM information_schema.columns
        WHERE table_schema = 'chatbot' AND table_name = 'etapa' AND column_name = 'bloqueio_dias'
    ) THEN
        RAISE EXCEPTION 'Aplicar primeiro a virada da Baratão e a migração da etapa 1.';
    END IF;
    IF NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa = 2 AND nome_etapa = 'cpf_titular')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa = 10
                      AND nome_etapa = 'encaminhamento' AND encerra_automaticamente AND bloqueio_dias = 90) THEN
        RAISE EXCEPTION 'Catálogo de CPF/encaminhamento incompatível com a etapa 2.';
    END IF;
END
$precondicoes$;

INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino)
VALUES (2, 'humano_solicitado', 10), (2, 'limite_sem_avanco', 10)
ON CONFLICT (id_etapa_origem, evento) DO UPDATE SET id_etapa_destino = EXCLUDED.id_etapa_destino;

COMMIT;

SELECT id_etapa_origem, evento, id_etapa_destino
FROM chatbot.etapa_transicao WHERE id_etapa_origem = 2 ORDER BY evento;
