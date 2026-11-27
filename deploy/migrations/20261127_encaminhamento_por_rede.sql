-- V0.3.0 → V0.4.0. Executar inteiro com os três serviços pausados.
-- Os números de teste existentes são reaproveitados sem reescrever mensagens ou históricos.
BEGIN;
SET LOCAL lock_timeout = '8s';
LOCK TABLE chatbot.central_pos_venda, chatbot.atendimento_pos_venda, chatbot.filial_compra
    IN ACCESS EXCLUSIVE MODE;

ALTER TABLE chatbot.filial_compra ADD COLUMN IF NOT EXISTS grupo text;
UPDATE chatbot.filial_compra SET grupo='Baratão'
WHERE grupo IS NULL AND codigo IN ('01','02','03','05','06','07','08','26','27','28','29');
UPDATE chatbot.filial_compra SET grupo='Atacadão'
WHERE grupo IS NULL AND codigo IN ('09','10','11','12','13','14','15','16','17','18','19','21','22','23','25');
-- Uma filial desconhecida precisa de classificação explícita antes de ativar o fluxo.
ALTER TABLE chatbot.filial_compra ALTER COLUMN grupo SET NOT NULL;

DO $migrar$
DECLARE
    regra_produto name;
BEGIN
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='chatbot.filial_compra'::regclass
                   AND conname='filial_compra_grupo_check') THEN
        ALTER TABLE chatbot.filial_compra ADD CONSTRAINT filial_compra_grupo_check
            CHECK (grupo IN ('Atacadão','Baratão'));
    END IF;

    IF EXISTS (SELECT FROM pg_attribute WHERE attrelid='chatbot.atendimento_pos_venda'::regclass
               AND attname='encaminhado_moveis' AND NOT attisdropped) THEN
        -- Só a regra que cruza produto + dois contatos perde a validade.
        SELECT c.conname INTO STRICT regra_produto FROM pg_constraint c
        WHERE c.conrelid='chatbot.atendimento_pos_venda'::regclass AND c.contype='c'
          AND ARRAY(SELECT a.attname::text FROM pg_attribute a
                    WHERE a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey) ORDER BY a.attname)
              = ARRAY['encaminhado_moveis','encaminhado_sofas','produto'];
        EXECUTE format('ALTER TABLE chatbot.atendimento_pos_venda DROP CONSTRAINT %I', regra_produto);
        ALTER TABLE chatbot.atendimento_pos_venda RENAME COLUMN encaminhado_moveis TO encaminhado_baratao;
        ALTER TABLE chatbot.atendimento_pos_venda RENAME COLUMN encaminhado_sofas TO encaminhado_atacadao;
    END IF;

    IF EXISTS (SELECT FROM pg_attribute WHERE attrelid='chatbot.central_pos_venda'::regclass
               AND attname='telefone_moveis' AND NOT attisdropped) THEN
        ALTER TABLE chatbot.central_pos_venda RENAME COLUMN telefone_moveis TO telefone_baratao;
        ALTER TABLE chatbot.central_pos_venda RENAME COLUMN telefone_sofas TO telefone_atacadao;
    END IF;
    -- Estas consultas também detectam uma instalação parcial com colunas ausentes.
    PERFORM telefone_baratao, telefone_atacadao FROM chatbot.central_pos_venda LIMIT 0;
    PERFORM encaminhado_baratao, encaminhado_atacadao FROM chatbot.atendimento_pos_venda LIMIT 0;
END;
$migrar$;
COMMIT;
