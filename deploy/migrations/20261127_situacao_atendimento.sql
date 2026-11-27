-- Aplicar uma vez sobre a Beta V0.6.0, como uma única transação.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE chatbot.atendimento_pos_venda
    ADD COLUMN situacao text NOT NULL DEFAULT 'Não encaminhado'
        CONSTRAINT atendimento_situacao_valida CHECK (situacao IN ('Não encaminhado', 'Já encaminhado', 'Aguardando cliente', 'Resolvido')),
    ADD COLUMN observacao text;

-- Completa também uma eventual conversa histórica que ainda não tenha ficha.
INSERT INTO chatbot.atendimento_pos_venda (id_conversa)
SELECT c.id_conversa FROM chatbot.conversa c
WHERE NOT EXISTS (
    SELECT FROM chatbot.atendimento_pos_venda a WHERE a.id_conversa = c.id_conversa
)
ON CONFLICT (id_conversa) DO NOTHING;

-- Bases anteriores podem ter o motivo confirmado sem os telefones dos destinos.
UPDATE chatbot.atendimento_pos_venda a
SET situacao = 'Já encaminhado'
FROM chatbot.conversa c
WHERE a.id_conversa = c.id_conversa
  AND (a.encaminhado_baratao IS NOT NULL OR a.encaminhado_atacadao IS NOT NULL
       OR c.motivo_encerramento IN ('encaminhamento', 'encaminhamento_midia',
                                    'encaminhamento_humano', 'encaminhamento_sem_avanco'));

-- O worker confirma os destinos na mesma transação do encaminhamento.
CREATE FUNCTION chatbot.sincronizar_situacao_atendimento() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.situacao <> 'Não encaminhado' THEN
        IF NEW.situacao = 'Não encaminhado' THEN
            RAISE EXCEPTION 'O encaminhamento já foi registrado neste atendimento.'
                USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;

    IF NEW.encaminhado_baratao IS NULL AND NEW.encaminhado_atacadao IS NULL THEN
        IF NEW.situacao <> 'Não encaminhado' THEN
            RAISE EXCEPTION 'O atendimento aguarda o encaminhamento ao setor humano.'
                USING ERRCODE = '23514';
        END IF;
    ELSIF NEW.situacao = 'Não encaminhado' THEN
        NEW.situacao := 'Já encaminhado';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER atendimento_sincroniza_situacao
    BEFORE INSERT OR UPDATE OF encaminhado_baratao, encaminhado_atacadao, situacao
    ON chatbot.atendimento_pos_venda
    FOR EACH ROW EXECUTE FUNCTION chatbot.sincronizar_situacao_atendimento();

COMMIT;
