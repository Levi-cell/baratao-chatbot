-- Baratão. Complementos pendentes na base de varejo conferida em 25/11/2026.
-- No DBeaver, executar o script inteiro, com webhook, worker_flow e coletor de consumo parados.
-- Uso único, a partir do estado da virada de 16/11. Uma transação para os cinco arquivos.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(81024, 1);
SELECT pg_advisory_xact_lock(73492601);
DO $origem$
BEGIN
    IF to_regclass('chatbot.central_pos_venda') IS NULL
       OR EXISTS (SELECT FROM information_schema.columns WHERE table_schema='chatbot'
                  AND table_name='etapa' AND column_name='bloqueio_dias')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=11 AND nome_etapa='abertura')
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=3 AND nome_etapa='cidade_loja_compra') THEN
        RAISE EXCEPTION 'Este roteiro exige a base da virada de 16/11, anterior aos complementos de etapas.';
    END IF;
END
$origem$;

-- 1/5  20261118_etapa1_encaminhamento_90_dias.sql
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

-- 2/5  20261118_etapa2_cpf.sql
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

-- 3/5  20261122_etapas_produto_encerramento.sql
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(81024, 1);
LOCK TABLE chatbot.etapa, chatbot.etapa_transicao, chatbot.conversa,
           chatbot.historico_mensagens, chatbot.fila_mensagens
    IN ACCESS EXCLUSIVE MODE;

DO $migrar$
DECLARE abertura_antiga boolean;
BEGIN
    IF EXISTS (SELECT FROM chatbot.conversa WHERE processing) THEN
        RAISE EXCEPTION 'Há conversas em processamento. Concluir a recuperação e parar os serviços antes de migrar.';
    END IF;
    SELECT nome_etapa = 'abertura' INTO abertura_antiga
    FROM chatbot.etapa WHERE id_etapa = 11;
    IF abertura_antiga IS NULL OR NOT (
        abertura_antiga OR EXISTS (
            SELECT FROM chatbot.etapa
            WHERE id_etapa = 11 AND nome_etapa = 'encaminhamento'
              AND encerra_automaticamente AND bloqueio_dias = 90
        )
    ) THEN
        RAISE EXCEPTION 'Catálogo não reconhecido; conferir as migrações anteriores.';
    END IF;
    IF EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa NOT IN (1,2,3,4,5,6,7,8,9,10,11)) THEN
        RAISE EXCEPTION 'Há etapas adicionais; revisar o mapa antes de substituir o catálogo.';
    END IF;

    IF abertura_antiga THEN
        IF NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=3 AND nome_etapa='cidade_loja_compra')
           OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=4 AND nome_etapa='produto')
           OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=10 AND nome_etapa='encaminhamento') THEN
            RAISE EXCEPTION 'Catálogo anterior incompleto; migração cancelada.';
        END IF;
        -- Quem aguardava cidade recebe a pergunta de produto no próximo turno.
        -- O marcador é interno e perde efeito quando uma nova resposta é confirmada.
        UPDATE chatbot.historico_mensagens h
        SET interativo = coalesce(h.interativo, '{}'::jsonb)
                         || '{"_migracao_produto_pendente":true}'::jsonb
        WHERE h.id_etapa=3 AND h.quem_enviou='bot' AND h.status_envio='sent'
          AND EXISTS (SELECT FROM chatbot.conversa c
                      WHERE c.id_conversa=h.id_conversa AND c.status_ativa
                        AND c.id_etapa_atual=3);
        UPDATE chatbot.conversa c SET id_etapa_atual =
            CASE c.id_etapa_atual
                WHEN 11 THEN CASE WHEN nullif(btrim(cl.nome_titular),'') IS NULL THEN 1
                                  WHEN cl.cpf_titular IS NULL THEN 2 ELSE 3 END
                WHEN 10 THEN 11 WHEN 4 THEN 3 ELSE c.id_etapa_atual END
        FROM chatbot.chat ch JOIN chatbot.cliente cl ON cl.id_cliente=ch.id_cliente
        WHERE ch.id_chat=c.id_chat AND c.id_etapa_atual IN (4,10,11);
        -- Guardar o ID anterior facilita interpretar as mensagens históricas.
        UPDATE chatbot.historico_mensagens
        SET interativo = coalesce(interativo, '{}'::jsonb)
                         || jsonb_build_object('_etapa_antes_20261122', id_etapa),
            id_etapa = CASE id_etapa
                WHEN 11 THEN coalesce((
                    SELECT c.id_etapa_atual FROM chatbot.conversa c
                    WHERE c.id_conversa=historico_mensagens.id_conversa
                      AND NOT EXISTS (SELECT FROM chatbot.historico_mensagens b
                                      WHERE b.id_conversa=c.id_conversa
                                        AND b.quem_enviou='bot' AND b.status_envio='sent')
                ), 1)
                WHEN 10 THEN 11 WHEN 4 THEN 3 ELSE id_etapa END
        WHERE id_etapa IN (3,4,10,11);
    END IF;
END
$migrar$;

DELETE FROM chatbot.etapa_transicao;
DELETE FROM chatbot.etapa WHERE id_etapa IN (4,10);
UPDATE chatbot.etapa SET nome_etapa='produto', encerra_automaticamente=false, bloqueio_dias=0
WHERE id_etapa=3;
UPDATE chatbot.etapa SET nome_etapa='encaminhamento', encerra_automaticamente=true, bloqueio_dias=90
WHERE id_etapa=11;

-- O bloco INSERT abaixo reproduz o mapa do catálogo canônico.
INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino) VALUES
    (1, 'nome_valido_falta_cpf', 2),
    (1, 'nome_valido_cpf_presente', 3),
    (2, 'cpf_valido', 3),
    (3, 'produto_escolhido', 5),
    (5, 'assunto_escolhido', 6),
    (6, 'pedidos_assistencia', 7),
    (6, 'nota_perdida_assistencia', 7),
    (6, 'pedidos_demais_assuntos', 9),
    (6, 'nota_perdida_demais_assuntos', 9),
    (7, 'loja_nao_visitada', 8),
    (7, 'loja_visitada', 9),
    (9, 'situacao_informada', 11),
    (1, 'midia_recebida', 11),
    (1, 'humano_solicitado', 11),
    (1, 'limite_sem_avanco', 11),
    (2, 'midia_recebida', 11),
    (2, 'humano_solicitado', 11),
    (2, 'limite_sem_avanco', 11),
    (3, 'midia_recebida', 11),
    (5, 'midia_recebida', 11),
    (6, 'midia_recebida', 11),
    (7, 'midia_recebida', 11),
    (9, 'midia_recebida', 11);

-- 4/5  20261122_etapa3_produto_assunto.sql
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

-- 5/5  20261122_consumo_meta_varejo.sql
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

-- Conferir o destino antes de confirmar qualquer alteração.
DO $destino$
BEGIN
    IF (SELECT count(*) FROM chatbot.etapa) <> 9
       OR (SELECT count(*) FROM chatbot.etapa_transicao) <> 25
       OR NOT EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem=3
                      AND evento='produto_escolhido' AND id_etapa_destino=4)
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=11 AND nome_etapa='encaminhamento'
                      AND encerra_automaticamente AND bloqueio_dias=90)
       OR NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='chatbot.consumo_mensal_meta'::regclass
                      AND conname='consumo_detalhamento_valido') THEN
        RAISE EXCEPTION 'A conferência final falhou. A transação não pode ser confirmada.';
    END IF;
END
$destino$;
COMMIT;

SELECT (SELECT count(*) FROM chatbot.etapa) AS etapas,
       (SELECT count(*) FROM chatbot.etapa_transicao) AS transicoes,
       (SELECT bloqueio_dias FROM chatbot.etapa WHERE id_etapa=11) AS bloqueio_dias,
       EXISTS (SELECT FROM pg_constraint WHERE conrelid='chatbot.consumo_mensal_meta'::regclass
               AND conname='consumo_detalhamento_valido') AS consumo_detalhado;
