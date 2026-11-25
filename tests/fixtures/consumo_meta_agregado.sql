-- Forma anterior do consumo no DDL de varejo, antes de restaurar a divisão.
CREATE TABLE chatbot.consumo_mensal_meta (
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    mes_referencia date NOT NULL CHECK (extract(day FROM mes_referencia) = 1),
    waba_id varchar NOT NULL,
    phone_number_id varchar NOT NULL,
    fuso_horario text NOT NULL,
    qtd_gratuitas bigint NOT NULL CHECK (qtd_gratuitas >= 0),
    qtd_cobradas_meta bigint NOT NULL CHECK (qtd_cobradas_meta >= 0),
    valor_meta numeric(14,6) CHECK (valor_meta >= 0),
    moeda varchar(3) CHECK (moeda ~ '^[A-Z]{3}$'),
    consultado_ate timestamptz NOT NULL,
    consolidado_em timestamptz,
    PRIMARY KEY (id_central, mes_referencia),
    CHECK ((valor_meta IS NULL) = (moeda IS NULL))
);
