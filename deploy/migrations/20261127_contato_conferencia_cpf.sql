-- A prova de contato fica na conversa até o CPF ser informado.
-- Aplicar antes da revisão que lê esta coluna. Atendimentos anteriores ficam com NULL.
BEGIN;
SET LOCAL lock_timeout = '8s';
ALTER TABLE chatbot.atendimento_pos_venda
    ADD COLUMN IF NOT EXISTS telefone_compartilhado varchar
    CHECK (telefone_compartilhado ~ '^[1-9][0-9]{0,14}$');
CREATE INDEX IF NOT EXISTS cliente_cpf_conciliacao
    ON chatbot.cliente (cpf_titular, id_cliente) WHERE cpf_titular IS NOT NULL;
COMMIT;
