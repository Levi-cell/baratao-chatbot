-- Restaura o detalhamento de consumo no schema de varejo já migrado.
-- Executar inteiro, com o worker_consumo_meta parado. Não acessa a Meta.
-- Não apaga totais, valores, moeda, histórico de conversas ou bloqueios.
-- A divisão das gratuitas perdida em 20261116 NÃO pode ser inferida do total.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
-- Mesmo lock do coletor: aborta por timeout se uma coleta estiver em execução.
SELECT pg_advisory_xact_lock(73492601);

ALTER TABLE chatbot.consumo_mensal_meta
    ADD COLUMN IF NOT EXISTS timezone_id integer,
    ADD COLUMN IF NOT EXISTS data_hora_inicio timestamptz,
    ADD COLUMN IF NOT EXISTS data_hora_fim timestamptz,
    ADD COLUMN IF NOT EXISTS qtd_janela_gratuita bigint,
    ADD COLUMN IF NOT EXISTS qtd_franquia_consumida bigint,
    ADD COLUMN IF NOT EXISTS ultimo_sucesso_em timestamptz,
    ADD COLUMN IF NOT EXISTS status_apuracao text NOT NULL DEFAULT 'pendente_detalhamento',
    ADD COLUMN IF NOT EXISTS data_proxima_consolidacao date,
    ADD COLUMN IF NOT EXISTS ultima_decisao_consolidacao_em timestamptz,
    ADD COLUMN IF NOT EXISTS franquia_meta_mensal integer NOT NULL DEFAULT 1000,
    ADD COLUMN IF NOT EXISTS beneficio_esl_mensal integer NOT NULL DEFAULT 1000,
    ADD COLUMN IF NOT EXISTS tarifa_referencia_brl numeric(12,6) NOT NULL DEFAULT 0.035,
    ADD COLUMN IF NOT EXISTS tarifa_vigencia date NOT NULL DEFAULT '2026-10-01',
    ADD COLUMN IF NOT EXISTS atualizado_em timestamptz NOT NULL DEFAULT now();

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_constraint
                   WHERE conrelid = 'chatbot.consumo_mensal_meta'::regclass AND conname = 'consumo_cobertura_valida') THEN
        ALTER TABLE chatbot.consumo_mensal_meta ADD CONSTRAINT consumo_cobertura_valida CHECK (
        franquia_meta_mensal >= 0 AND beneficio_esl_mensal >= 0 AND tarifa_referencia_brl >= 0);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_constraint
                   WHERE conrelid = 'chatbot.consumo_mensal_meta'::regclass AND conname = 'consumo_detalhamento_valido') THEN
        ALTER TABLE chatbot.consumo_mensal_meta ADD CONSTRAINT consumo_detalhamento_valido CHECK (
        (status_apuracao = 'pendente_detalhamento'
            AND timezone_id IS NULL AND data_hora_inicio IS NULL AND data_hora_fim IS NULL
            AND qtd_janela_gratuita IS NULL AND qtd_franquia_consumida IS NULL
            AND ultimo_sucesso_em IS NULL AND data_proxima_consolidacao IS NULL
            AND ultima_decisao_consolidacao_em IS NULL)
        OR (status_apuracao IN ('em_andamento','em_conferencia','consolidado')
            AND timezone_id IS NOT NULL AND timezone_id > 0
            AND data_hora_inicio IS NOT NULL AND data_hora_fim IS NOT NULL
            AND data_hora_inicio < data_hora_fim
            AND consultado_ate > data_hora_inicio AND consultado_ate <= data_hora_fim
            AND ultimo_sucesso_em IS NOT NULL
            AND qtd_janela_gratuita IS NOT NULL AND qtd_janela_gratuita >= 0
            AND qtd_franquia_consumida IS NOT NULL AND qtd_franquia_consumida >= 0
            AND qtd_franquia_consumida <= franquia_meta_mensal
            AND qtd_gratuitas = qtd_janela_gratuita + qtd_franquia_consumida
            AND ((status_apuracao IN ('em_andamento','em_conferencia')
                    AND consolidado_em IS NULL AND data_proxima_consolidacao IS NOT NULL
                    AND extract(day FROM data_proxima_consolidacao) = 25
                    AND data_proxima_consolidacao > mes_referencia)
                OR (status_apuracao = 'consolidado' AND consolidado_em IS NOT NULL
                    AND data_proxima_consolidacao IS NULL
                    AND ultima_decisao_consolidacao_em IS NOT NULL
                    AND consultado_ate = data_hora_fim)))
    );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS consumo_pendentes
    ON chatbot.consumo_mensal_meta (id_central, mes_referencia)
    WHERE status_apuracao <> 'consolidado';

-- Só centrais ativas entram na recoleta. Registros antigos de centrais inativas
-- continuam preservados e não reativam a integração do Supera.
INSERT INTO chatbot.consumo_meta_coletas (id_central, periodo, proxima_consulta_em)
SELECT m.id_central, to_char(m.mes_referencia, 'YYYY-MM'), now()
FROM chatbot.consumo_mensal_meta m
JOIN chatbot.central_pos_venda c USING (id_central)
WHERE c.ativa AND m.status_apuracao = 'pendente_detalhamento'
ON CONFLICT (id_central, periodo) DO UPDATE SET proxima_consulta_em = now();

COMMIT;
