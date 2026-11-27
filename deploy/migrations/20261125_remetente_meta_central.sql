-- Executar antes de publicar o worker. As centrais existentes continuam com WAAC nulo.
BEGIN;
SET LOCAL lock_timeout = '5s';
ALTER TABLE chatbot.central_pos_venda
    ADD COLUMN IF NOT EXISTS waac_id varchar UNIQUE
        CHECK (waac_id ~ '^[1-9][0-9]*$' AND waac_id <> phone_number_id);
COMMIT;

SELECT id_central, nome, phone_number_id, waba_id AS messaging_account_id, waac_id
FROM chatbot.central_pos_venda
ORDER BY id_central;
