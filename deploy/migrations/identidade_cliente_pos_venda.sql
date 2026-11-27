-- Base: DDL varejo e migração do remetente. Executar com os consumidores parados.
BEGIN;
SET LOCAL lock_timeout = '5s';
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
SELECT DISTINCT cliente_telefone FROM chatbot.fila_mensagens WHERE cliente_telefone IS NOT NULL
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
COMMIT;

-- Conferência de leitura após o commit. Resultado esperado: true, true, true, true, 0.
SELECT EXISTS (SELECT FROM information_schema.columns WHERE table_schema='chatbot'
                 AND table_name='central_pos_venda' AND column_name='waac_id') AS central_com_waac,
       to_regclass('chatbot.identidade_bsuid') IS NOT NULL AS vinculo_bsuid,
       to_regclass('chatbot.solicitacao_contato') IS NOT NULL AS pedido_contato,
       to_regclass('chatbot.fallback_contato') IS NOT NULL AS fallback_contato,
       (SELECT count(*) FROM chatbot.fila_mensagens WHERE id_cliente IS NULL) AS fila_sem_cliente;
