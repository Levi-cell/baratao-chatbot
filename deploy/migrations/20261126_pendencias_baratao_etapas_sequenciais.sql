-- Baratão • 26/11/2026 • executar o arquivo inteiro no DBeaver, conectado a db_chatbot.
-- Base: catálogo varejista de 25/11, com assunto misto e filiais dos pedidos.
-- Parar os processos da aplicação antes de aplicar e iniciar a versão com IDs sequenciais após o COMMIT.
-- As tabelas temporárias existem apenas nesta transação. Um estado divergente provoca rollback.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '2min';

LOCK TABLE chatbot.etapa, chatbot.etapa_transicao, chatbot.conversa,
           chatbot.historico_mensagens IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE etapas_esperadas (
    id integer PRIMARY KEY, nome text UNIQUE, terminal boolean, dias integer
) ON COMMIT DROP;
INSERT INTO etapas_esperadas VALUES
(1, 'nome_titular', false, 0),
    (2, 'cpf_titular', false, 0),
    (3, 'produto', false, 0),
    (4, 'assunto', false, 0),
    (5, 'pedidos', false, 0),
    (6, 'visita_loja', false, 0),
    (7, 'visita_pendente', true, 0),
    (8, 'detalhes', false, 0),
    (9, 'encaminhamento', true, 90);

CREATE TEMP TABLE transicoes_esperadas (
    origem integer, evento text, destino integer, PRIMARY KEY (origem, evento)
) ON COMMIT DROP;
INSERT INTO transicoes_esperadas VALUES
(1, 'nome_valido_falta_cpf', 2),
    (1, 'nome_valido_cpf_presente', 3),
    (2, 'cpf_valido', 3),
    (3, 'produto_escolhido', 4),
    (4, 'assunto_escolhido', 5),
    (5, 'pedidos_assistencia', 6),
    (5, 'nota_perdida_assistencia', 6),
    (5, 'pedidos_demais_assuntos', 8),
    (5, 'nota_perdida_demais_assuntos', 8),
    (6, 'loja_nao_visitada', 7),
    (6, 'loja_visitada', 8),
    (8, 'situacao_informada', 9),
    (1, 'midia_recebida', 9),
    (1, 'humano_solicitado', 9),
    (1, 'limite_sem_avanco', 9),
    (2, 'midia_recebida', 9),
    (2, 'humano_solicitado', 9),
    (2, 'limite_sem_avanco', 9),
    (3, 'midia_recebida', 9),
    (3, 'humano_solicitado', 9),
    (3, 'limite_sem_avanco', 9),
    (4, 'midia_recebida', 9),
    (4, 'humano_solicitado', 9),
    (4, 'limite_sem_avanco', 9),
    (5, 'midia_recebida', 9),
    (5, 'humano_solicitado', 9),
    (5, 'limite_sem_avanco', 9),
    (6, 'midia_recebida', 9),
    (8, 'midia_recebida', 9);

-- O nome estável identifica a etapa mesmo quando o mesmo número muda de significado.
DO $base$
DECLARE
    ids integer[];
BEGIN
    SELECT array_agg(e.id_etapa ORDER BY ref.id) INTO ids
    FROM chatbot.etapa e JOIN etapas_esperadas ref ON e.nome_etapa = ref.nome
        AND e.encerra_automaticamente = ref.terminal AND e.bloqueio_dias = ref.dias;
    IF (SELECT count(*) FROM chatbot.etapa) <> 9 OR ids IS NULL OR
       ids NOT IN (ARRAY[1,2,3,4,6,7,8,9,11], ARRAY[1,2,3,4,5,6,7,8,9]) THEN
        RAISE EXCEPTION 'Catálogo de etapas inesperado. A migração exige a base varejista de 25/11 ou o catálogo sequencial.';
    END IF;
    IF (SELECT count(*) FROM chatbot.etapa_transicao) <> 29 OR EXISTS (
        SELECT ref_o.id, t.evento, ref_d.id
        FROM chatbot.etapa_transicao t
        JOIN chatbot.etapa o ON o.id_etapa = t.id_etapa_origem
        JOIN etapas_esperadas ref_o ON ref_o.nome = o.nome_etapa
        JOIN chatbot.etapa d ON d.id_etapa = t.id_etapa_destino
        JOIN etapas_esperadas ref_d ON ref_d.nome = d.nome_etapa
        EXCEPT SELECT origem, evento, destino FROM transicoes_esperadas
    ) THEN
        RAISE EXCEPTION 'O mapa de transições diverge do catálogo esperado. Confira a base antes de continuar.';
    END IF;
END
$base$;

-- 1. Remetente Meta da central. O WAAC real pode ser cadastrado quando disponível.
ALTER TABLE chatbot.central_pos_venda
    ADD COLUMN IF NOT EXISTS waac_id varchar UNIQUE
        CHECK (waac_id ~ '^[1-9][0-9]*$' AND waac_id <> phone_number_id);

-- 2. Identidade por telefone/BSUID, retomada do contato e fila por cliente e central.
LOCK TABLE chatbot.cliente, chatbot.fila_mensagens IN SHARE ROW EXCLUSIVE MODE;
ALTER TABLE chatbot.cliente
    ALTER COLUMN waid_telefone DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS username text,
    ADD COLUMN IF NOT EXISTS username_observado_em timestamptz;

ALTER TABLE chatbot.fila_mensagens
    ALTER COLUMN cliente_telefone DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS id_cliente int REFERENCES chatbot.cliente,
    ADD COLUMN IF NOT EXISTS user_id_origem text,
    ADD COLUMN IF NOT EXISTS username_origem text;

ALTER TABLE chatbot.historico_mensagens
    ADD COLUMN IF NOT EXISTS tipo_destinatario text
        CHECK (tipo_destinatario IN ('wa_id', 'bsuid')),
    ADD COLUMN IF NOT EXISTS valor_destinatario text;

INSERT INTO chatbot.cliente (waid_telefone)
SELECT DISTINCT cliente_telefone FROM chatbot.fila_mensagens WHERE id_cliente IS NULL AND cliente_telefone IS NOT NULL
ON CONFLICT (waid_telefone) DO NOTHING;

UPDATE chatbot.fila_mensagens AS fila
SET id_cliente = cliente.id_cliente
FROM chatbot.cliente AS cliente
WHERE fila.id_cliente IS NULL AND cliente.waid_telefone = fila.cliente_telefone;

CREATE TABLE IF NOT EXISTS chatbot.identidade_bsuid (
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    user_id text NOT NULL CHECK (btrim(user_id) <> ''),
    id_cliente int NOT NULL REFERENCES chatbot.cliente,
    wamid_origem text NOT NULL,
    suspender_telefone boolean NOT NULL DEFAULT false,
    vigente boolean NOT NULL DEFAULT true,
    PRIMARY KEY (id_central, user_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS identidade_bsuid_vigente
    ON chatbot.identidade_bsuid (id_central, id_cliente) WHERE vigente;

CREATE TABLE IF NOT EXISTS chatbot.solicitacao_contato (
    id_conversa int PRIMARY KEY REFERENCES chatbot.conversa,
    motivo text NOT NULL CHECK (motivo IN ('cadastro', 'reconfirmacao')),
    id_etapa_retomada int NOT NULL REFERENCES chatbot.etapa,
    bsuid_destino text NOT NULL,
    wamid_solicitacao text NOT NULL,
    wamids_aceitos text[] NOT NULL,
    erros_cliente smallint NOT NULL DEFAULT 0 CHECK (erros_cliente BETWEEN 0 AND 3)
);

CREATE TABLE IF NOT EXISTS chatbot.fallback_contato (
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    id_mensagem_fila int NOT NULL REFERENCES chatbot.fila_mensagens,
    wamid_original text UNIQUE,
    estado text NOT NULL CHECK (estado IN
        ('reservado','em_envio','aceito','incerto','cancelado')),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_conversa, id_mensagem_fila)
);
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='chatbot.fila_mensagens'::regclass
                   AND conname='fila_identidade_presente') THEN
        ALTER TABLE chatbot.fila_mensagens ADD CONSTRAINT fila_identidade_presente
            CHECK (cliente_telefone IS NOT NULL OR (user_id_origem IS NOT NULL AND id_cliente IS NOT NULL));
    END IF;
END $$;
DROP INDEX IF EXISTS chatbot.fila_turno;
CREATE INDEX IF NOT EXISTS fila_primeira_identidade ON chatbot.fila_mensagens (id_central, id_cliente, id_mensagem);
CREATE INDEX fila_turno ON chatbot.fila_mensagens (id_central,id_cliente,received_data_hora,id_mensagem)
    WHERE status IN ('pending','processing');
CREATE OR REPLACE FUNCTION chatbot.dequeue_message()
RETURNS TABLE (id_mensagem int, cliente_telefone varchar, conteudo_texto text, tipo_mensagem varchar,
               id_phone_unidade varchar, unidade_telefone varchar, received_data_hora timestamptz,
               id_hash_msg varchar, retry_count int)
LANGUAGE sql AS $$
    WITH proxima AS (
        SELECT f.id_mensagem, b.phone_number_id, b.telefone
        FROM chatbot.fila_mensagens f JOIN chatbot.central_pos_venda b USING (id_central)
        WHERE b.ativa AND (
            (f.status = 'pending' AND f.next_attempt_at <= now()) OR
            (f.status = 'processing' AND f.processing_started_at < now() - interval '2 minutes')
        ) AND NOT EXISTS (
            SELECT FROM chatbot.fila_mensagens a
            WHERE a.id_central = f.id_central AND (a.id_cliente = f.id_cliente OR ((a.id_cliente IS NULL OR f.id_cliente IS NULL) AND a.cliente_telefone = f.cliente_telefone))
              AND a.status IN ('pending','processing')
              AND (a.received_data_hora, a.id_mensagem) < (f.received_data_hora, f.id_mensagem)
        )
        ORDER BY f.received_data_hora, f.id_mensagem
        LIMIT 1 FOR UPDATE OF f SKIP LOCKED
    )
    UPDATE chatbot.fila_mensagens f
    SET status = 'processing', retry_count = f.retry_count + 1, processing_started_at = now()
    FROM proxima p WHERE f.id_mensagem = p.id_mensagem
    RETURNING f.id_mensagem, f.cliente_telefone, f.conteudo_texto, f.tipo_mensagem,
              p.phone_number_id, p.telefone, f.received_data_hora, f.id_hash_msg, f.retry_count;
$$;

-- 3. Cada destino fica livre antes do próximo movimento. Preservar o ID das transições,
-- os históricos, os contadores de turno e as datas usadas no bloqueio de 90 dias.
LOCK TABLE chatbot.solicitacao_contato IN SHARE ROW EXCLUSIVE MODE;

DO $renumerar$
DECLARE
    etapa record;
BEGIN
    FOR etapa IN
        SELECT e.id_etapa AS antigo, ref.id AS novo, ref.nome, ref.terminal, ref.dias
        FROM chatbot.etapa e JOIN etapas_esperadas ref ON e.nome_etapa = ref.nome
        WHERE e.id_etapa <> ref.id ORDER BY ref.id
    LOOP
        UPDATE chatbot.etapa SET nome_etapa = '__renumerar_' || etapa.antigo WHERE id_etapa = etapa.antigo;
        INSERT INTO chatbot.etapa (id_etapa, nome_etapa, encerra_automaticamente, bloqueio_dias)
        VALUES (etapa.novo, etapa.nome, etapa.terminal, etapa.dias);

        UPDATE chatbot.etapa_transicao SET id_etapa_origem = etapa.novo WHERE id_etapa_origem = etapa.antigo;
        UPDATE chatbot.etapa_transicao SET id_etapa_destino = etapa.novo WHERE id_etapa_destino = etapa.antigo;
        UPDATE chatbot.conversa SET id_etapa_atual = etapa.novo WHERE id_etapa_atual = etapa.antigo;
        UPDATE chatbot.historico_mensagens SET id_etapa = etapa.novo WHERE id_etapa = etapa.antigo;
        UPDATE chatbot.solicitacao_contato SET id_etapa_retomada = etapa.novo WHERE id_etapa_retomada = etapa.antigo;
        DELETE FROM chatbot.etapa WHERE id_etapa = etapa.antigo;
    END LOOP;
END
$renumerar$;

DO $conferir$
BEGIN
    IF EXISTS (SELECT id,nome,terminal,dias FROM etapas_esperadas
               EXCEPT SELECT id_etapa,nome_etapa,encerra_automaticamente,bloqueio_dias FROM chatbot.etapa)
       OR EXISTS (SELECT origem,evento,destino FROM transicoes_esperadas
                  EXCEPT SELECT id_etapa_origem,evento,id_etapa_destino FROM chatbot.etapa_transicao)
       OR EXISTS (SELECT FROM chatbot.fila_mensagens WHERE id_cliente IS NULL) THEN
        RAISE EXCEPTION 'A conferência de etapas, transições ou identidade da fila falhou.';
    END IF;
END
$conferir$;
COMMIT;

-- Resultado esperado: 1 a 9, 29, 90, true, true, true, true, 0.
SELECT (SELECT array_agg(id_etapa ORDER BY id_etapa) FROM chatbot.etapa) AS etapas,
       (SELECT count(*) FROM chatbot.etapa_transicao) AS transicoes,
       (SELECT bloqueio_dias FROM chatbot.etapa WHERE nome_etapa = 'encaminhamento') AS bloqueio_dias,
       EXISTS (SELECT FROM information_schema.columns WHERE table_schema = 'chatbot'
               AND table_name = 'central_pos_venda' AND column_name = 'waac_id') AS central_com_waac,
       to_regclass('chatbot.identidade_bsuid') IS NOT NULL AS vinculo_bsuid,
       to_regclass('chatbot.solicitacao_contato') IS NOT NULL AS pedido_contato,
       to_regclass('chatbot.fallback_contato') IS NOT NULL AS fallback_contato,
       (SELECT count(*) FROM chatbot.fila_mensagens WHERE id_cliente IS NULL) AS fila_sem_cliente;
