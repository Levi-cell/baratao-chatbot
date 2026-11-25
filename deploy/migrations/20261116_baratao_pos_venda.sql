-- Virada única do Supera para o pós-venda da Baratão. Executar o arquivo inteiro.
-- Parar os serviços do Supera e guardar um backup atualizado do schema chatbot.
-- Requer o schema existente com as migrations do Supera e auth_user do Django.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '120s';
SET LOCAL search_path = pg_catalog, pg_temp;
SELECT pg_advisory_xact_lock(81024, 1);

DO $origem$
BEGIN
    IF to_regclass('chatbot.central_pos_venda') IS NOT NULL THEN
        RAISE EXCEPTION 'A central já existe. Esta migração somente pode ser aplicada uma vez.';
    END IF;
    IF to_regclass('chatbot.auth_user') IS NULL OR to_regclass('chatbot.unidade') IS NULL
       OR to_regclass('chatbot.dependente') IS NULL THEN
        RAISE EXCEPTION 'Origem inesperada. Esperado o schema chatbot do Supera com autenticação Django.';
    END IF;
END
$origem$;

LOCK TABLE
    chatbot.atendimento_customizado,
    chatbot.cache_controle,
    chatbot.chat,
    chatbot.cliente,
    chatbot.cliente_bloqueado_meta,
    chatbot.consulta_fireads,
    chatbot.consumo_mensal_meta,
    chatbot.consumo_meta_coletas,
    chatbot.conversa,
    chatbot.dependente,
    chatbot.endereco_unidade,
    chatbot.envios_dash,
    chatbot.etapa,
    chatbot.etapa_transicao,
    chatbot.fila_mensagens,
    chatbot.followup_envio,
    chatbot.followup_legado,
    chatbot.followup_retomada,
    chatbot.funil_envios,
    chatbot.historico_mensagens,
    chatbot.integracao_fireads,
    chatbot.integracao_funil_unidade,
    chatbot.migracoes_fireads,
    chatbot.pesquisa_satisfacao,
    chatbot.respostas_desafios,
    chatbot.unidade,
    chatbot.webhook_flood_evento
    IN ACCESS EXCLUSIVE MODE;

-- Referências para conferir a migração antes do commit. Todas são temporárias.
CREATE TEMP TABLE unidades_origem ON COMMIT DROP AS
SELECT u.id_unidade, u.phone_number_id, a.nome_agente, a.genero
FROM chatbot.unidade u LEFT JOIN chatbot.atendimento_customizado a USING (id_unidade);
CREATE TEMP TABLE consumo_origem ON COMMIT DROP AS
SELECT id_unidade, mes_referencia, waba_id, phone_number_id, fuso_horario,
       qtd_janela_gratuita + qtd_franquia_consumida AS gratuitas, qtd_cobradas_meta,
       consultado_ate, consolidado_em
FROM chatbot.consumo_mensal_meta;
CREATE TEMP TABLE bloqueios_origem ON COMMIT DROP AS
SELECT id_unidade, wa_id_cliente FROM chatbot.cliente_bloqueado_meta;
CREATE TEMP TABLE agenda_origem ON COMMIT DROP AS
SELECT id_unidade, periodo, proxima_consulta_em, ultima_tentativa_em,
       falhas_consecutivas, ultimo_erro FROM chatbot.consumo_meta_coletas;
CREATE TEMP TABLE flood_origem ON COMMIT DROP AS
SELECT f.id_hash_msg, u.id_unidade, f.wa_id_cliente, f.received_at
FROM chatbot.webhook_flood_evento f LEFT JOIN chatbot.unidade u ON u.phone_number_id=f.phone_id_unidade;

-- Desmontar as dependências nomeadas do modelo antigo. Dependências externas interrompem a virada.
DROP TRIGGER unidade_exige_customizacao ON chatbot.unidade;

ALTER TABLE chatbot.unidade
    DROP CONSTRAINT unidade_id_usuario_monitoramento_fkey;

ALTER TABLE chatbot.chat
    DROP CONSTRAINT chat_id_cliente_fkey,
    DROP CONSTRAINT chat_id_unidade_fkey;

ALTER TABLE chatbot.etapa_transicao
    DROP CONSTRAINT etapa_transicao_destino_fkey,
    DROP CONSTRAINT etapa_transicao_origem_fkey;

ALTER TABLE chatbot.conversa
    DROP CONSTRAINT conversa_id_cliente_fkey,
    DROP CONSTRAINT conversa_id_etapa_atual_fkey,
    DROP CONSTRAINT conversa_id_unidade_fkey,
    DROP CONSTRAINT fk_conversa_chat;

ALTER TABLE chatbot.fila_mensagens
    DROP CONSTRAINT fila_mensagens_id_conversa_fkey;

ALTER TABLE chatbot.cliente_bloqueado_meta
    DROP CONSTRAINT fk_cliente_bloqueado_meta_cliente,
    DROP CONSTRAINT fk_cliente_bloqueado_meta_unidade_phone;

ALTER TABLE chatbot.consumo_mensal_meta
    DROP CONSTRAINT consumo_mensal_meta_id_unidade_fkey;

ALTER TABLE chatbot.consumo_meta_coletas
    DROP CONSTRAINT consumo_meta_coletas_id_unidade_fkey;

DROP TABLE
    chatbot.atendimento_customizado,
    chatbot.consulta_fireads,
    chatbot.dependente,
    chatbot.endereco_unidade,
    chatbot.envios_dash,
    chatbot.followup_envio,
    chatbot.followup_legado,
    chatbot.followup_retomada,
    chatbot.funil_envios,
    chatbot.historico_mensagens,
    chatbot.integracao_fireads,
    chatbot.integracao_funil_unidade,
    chatbot.migracoes_fireads,
    chatbot.pesquisa_satisfacao,
    chatbot.respostas_desafios;

DROP FUNCTION chatbot.verificar_customizacao_unidade(), chatbot.marcar_ativacao_fireads(),
    chatbot.lock_conversa(integer), chatbot.unlock_conversa(integer, integer), chatbot.dequeue_message();

-- Os atendimentos legados ficam no backup. O histórico antigo era particionado.
TRUNCATE TABLE chatbot.chat, chatbot.cliente, chatbot.conversa, chatbot.etapa_transicao,
    chatbot.etapa, chatbot.fila_mensagens, chatbot.cache_controle;

ALTER TABLE chatbot.unidade
    DROP CONSTRAINT ck_unidade_fuso_meta,
    DROP CONSTRAINT ck_unidade_nome_unidade_nao_vazio,
    DROP CONSTRAINT unidade_pkey,
    DROP CONSTRAINT unidade_cnpj_key,
    DROP CONSTRAINT unidade_email_responsavel_key,
    DROP CONSTRAINT unidade_phone_number_id_key,
    DROP CONSTRAINT unidade_telefone_key,
    DROP CONSTRAINT unidade_waba_id_key,
    DROP CONSTRAINT uq_unidade_nome_unidade,
    DROP CONSTRAINT uq_unidade_usuario_monitoramento;

ALTER TABLE chatbot.cliente
    DROP CONSTRAINT cliente_pkey,
    DROP CONSTRAINT cliente_email_key,
    DROP CONSTRAINT cliente_waid_telefone_key;

ALTER TABLE chatbot.chat
    DROP CONSTRAINT chat_pkey,
    DROP CONSTRAINT uq_chat_cliente_unidade,
    DROP CONSTRAINT uq_chat_identidade,
    DROP CONSTRAINT uq_chat_unidade;

ALTER TABLE chatbot.etapa
    DROP CONSTRAINT ck_etapa_bloqueio_dias,
    DROP CONSTRAINT etapa_pkey,
    DROP CONSTRAINT etapa_nome_etapa_key;

ALTER TABLE chatbot.etapa_transicao
    DROP CONSTRAINT etapa_transicao_sem_auto_salto,
    DROP CONSTRAINT etapa_transicao_pkey,
    DROP CONSTRAINT etapa_transicao_origem_destino_unique,
    DROP CONSTRAINT etapa_transicao_origem_evento_unique;

ALTER TABLE chatbot.conversa
    DROP CONSTRAINT ck_conversa_contexto_coleta,
    DROP CONSTRAINT ck_conversa_fireads,
    DROP CONSTRAINT ck_conversa_motivo_encerramento,
    DROP CONSTRAINT ck_conversa_origem_fireads,
    DROP CONSTRAINT ck_conversa_turno,
    DROP CONSTRAINT ck_conversa_turnos_sem_avanco,
    DROP CONSTRAINT conversa_last_message_from_check,
    DROP CONSTRAINT conversa_pkey,
    DROP CONSTRAINT uq_conversa_chat_unidade,
    DROP CONSTRAINT uq_conversa_unidade;

DROP INDEX chatbot.idx_conversa_chat, chatbot.idx_conversa_followup, chatbot.idx_conversa_funil_pendente, chatbot.idx_conversa_processing, chatbot.idx_conversa_ultima_inativa, chatbot.idx_conversa_unica_ativa;

ALTER TABLE chatbot.fila_mensagens
    DROP CONSTRAINT fila_mensagens_status_check,
    DROP CONSTRAINT fila_mensagens_pkey,
    DROP CONSTRAINT fila_mensagens_id_hash_msg_key;

DROP INDEX chatbot.idx_fila_cliente_unidade_aberta, chatbot.idx_fila_cliente_unidade_conversa_aberta, chatbot.idx_fila_conversa_aberta_data, chatbot.idx_fila_pending_next_attempt, chatbot.idx_fila_processing_timeout;

ALTER TABLE chatbot.cache_controle
    DROP CONSTRAINT cache_controle_pkey;

ALTER TABLE chatbot.cliente_bloqueado_meta
    DROP CONSTRAINT cliente_bloqueado_meta_pkey,
    DROP CONSTRAINT uq_cliente_bloqueado_meta_wa_unidade;

DROP INDEX chatbot.idx_cliente_bloqueado_meta_id_cliente, chatbot.idx_cliente_bloqueado_meta_id_unidade, chatbot.idx_cliente_bloqueado_meta_phone_id, chatbot.idx_cliente_bloqueado_meta_wa_id;

ALTER TABLE chatbot.webhook_flood_evento
    DROP CONSTRAINT webhook_flood_evento_pkey,
    DROP CONSTRAINT webhook_flood_evento_id_hash_msg_key;

DROP INDEX chatbot.idx_webhook_flood_evento_janela, chatbot.idx_webhook_flood_evento_limpeza;

ALTER TABLE chatbot.consumo_mensal_meta
    DROP CONSTRAINT ck_consumo_estado,
    DROP CONSTRAINT ck_consumo_franquia,
    DROP CONSTRAINT ck_consumo_fronteiras,
    DROP CONSTRAINT ck_consumo_mes,
    DROP CONSTRAINT consumo_mensal_meta_beneficio_esl_mensal_check,
    DROP CONSTRAINT consumo_mensal_meta_franquia_meta_mensal_check,
    DROP CONSTRAINT consumo_mensal_meta_fuso_horario_check,
    DROP CONSTRAINT consumo_mensal_meta_qtd_cobradas_meta_check,
    DROP CONSTRAINT consumo_mensal_meta_qtd_franquia_consumida_check,
    DROP CONSTRAINT consumo_mensal_meta_qtd_janela_gratuita_check,
    DROP CONSTRAINT consumo_mensal_meta_tarifa_referencia_brl_check,
    DROP CONSTRAINT consumo_mensal_meta_timezone_id_check,
    DROP CONSTRAINT consumo_mensal_meta_pkey,
    DROP CONSTRAINT uq_consumo_unidade_mes;

DROP INDEX chatbot.idx_consumo_meta_pendentes;

ALTER TABLE chatbot.consumo_meta_coletas
    DROP CONSTRAINT consumo_meta_coletas_falhas_consecutivas_check,
    DROP CONSTRAINT consumo_meta_coletas_periodo_check,
    DROP CONSTRAINT consumo_meta_coletas_pkey;

DROP INDEX chatbot.idx_consumo_meta_coletas_agenda;

DROP INDEX chatbot.uq_unidade_id_phone_number_id;

ALTER TABLE chatbot.unidade RENAME TO central_pos_venda;

ALTER SEQUENCE chatbot.unidade_id_unidade_seq RENAME TO central_pos_venda_id_central_seq;

ALTER TABLE chatbot.central_pos_venda RENAME COLUMN id_unidade TO id_central;

ALTER TABLE chatbot.central_pos_venda RENAME COLUMN nome_unidade TO nome;

ALTER TABLE chatbot.central_pos_venda RENAME COLUMN status_pagamento TO ativa;

ALTER TABLE chatbot.consumo_mensal_meta RENAME COLUMN id_unidade TO id_central;

ALTER TABLE chatbot.consumo_mensal_meta RENAME COLUMN qtd_janela_gratuita TO qtd_gratuitas;

ALTER TABLE chatbot.consumo_meta_coletas RENAME COLUMN id_unidade TO id_central;

ALTER TABLE chatbot.cliente_bloqueado_meta RENAME COLUMN id_unidade TO id_central;

ALTER TABLE chatbot.chat RENAME COLUMN id_unidade TO id_central;

ALTER TABLE chatbot.conversa RENAME COLUMN id_unidade TO id_central;

-- Preservar o número empresarial associado ao consumo e aos bloqueios.
-- As centrais anteriores ficam inativas e sem operadores atribuídos.
ALTER TABLE chatbot.central_pos_venda ADD COLUMN nome_agente text, ADD COLUMN genero_agente text;
UPDATE chatbot.central_pos_venda c SET ativa=false, nome_agente=u.nome_agente, genero_agente=u.genero
FROM pg_temp.unidades_origem u WHERE c.id_central=u.id_unidade;

UPDATE chatbot.consumo_mensal_meta SET qtd_gratuitas = qtd_gratuitas + qtd_franquia_consumida;
ALTER TABLE chatbot.webhook_flood_evento ADD COLUMN id_central integer;
UPDATE chatbot.webhook_flood_evento f SET id_central=u.id_unidade
FROM pg_temp.unidades_origem u WHERE u.phone_number_id=f.phone_id_unidade;

ALTER TABLE chatbot.central_pos_venda
    DROP COLUMN cnpj,
    DROP COLUMN email_responsavel,
    DROP COLUMN id_usuario_monitoramento,
    DROP COLUMN horarios_funcionamento,
    ALTER COLUMN nome TYPE text,
    ALTER COLUMN nome_agente SET NOT NULL,
    ALTER COLUMN genero_agente SET NOT NULL,
    ALTER COLUMN ativa SET NOT NULL,
    ALTER COLUMN waba_id TYPE character varying,
    ALTER COLUMN phone_number_id TYPE character varying,
    ALTER COLUMN telefone TYPE character varying,
    ADD COLUMN telefone_moveis character varying,
    ADD COLUMN telefone_sofas character varying;

ALTER TABLE chatbot.cliente
    DROP COLUMN nome,
    DROP COLUMN email,
    DROP COLUMN idade,
    DROP COLUMN profissao,
    ALTER COLUMN waid_telefone TYPE character varying,
    ADD COLUMN nome_titular text,
    ADD COLUMN cpf_titular character varying(11),
    ADD COLUMN cidade_loja_compra text;

ALTER TABLE chatbot.chat
    DROP COLUMN criado_em;

ALTER TABLE chatbot.etapa
    DROP COLUMN bloqueio_dias,
    DROP COLUMN elegivel_funil,
    ALTER COLUMN id_etapa DROP DEFAULT;

ALTER TABLE chatbot.conversa
    DROP COLUMN id_cliente,
    DROP COLUMN status_dependente,
    DROP COLUMN followup_stage,
    DROP COLUMN followup_last_sent_at,
    DROP COLUMN lead_no_funil,
    DROP COLUMN profissao,
    DROP COLUMN turno,
    DROP COLUMN origem_fireads,
    DROP COLUMN contexto_fireads,
    DROP COLUMN lead_no_dash,
    DROP COLUMN contexto_coleta,
    ALTER COLUMN id_etapa_atual SET NOT NULL,
    ALTER COLUMN motivo_encerramento TYPE text,
    ALTER COLUMN last_message_from TYPE character varying,
    ALTER COLUMN processing SET NOT NULL,
    ALTER COLUMN lock_version SET NOT NULL;

ALTER TABLE chatbot.fila_mensagens
    DROP COLUMN id_phone_unidade,
    DROP COLUMN unidade_telefone,
    ADD COLUMN id_central integer NOT NULL,
    ALTER COLUMN cliente_telefone TYPE character varying,
    ALTER COLUMN id_hash_msg TYPE character varying,
    ALTER COLUMN tipo_mensagem TYPE character varying,
    ADD COLUMN interativo jsonb,
    ALTER COLUMN status TYPE character varying,
    ALTER COLUMN retry_count SET NOT NULL,
    ALTER COLUMN next_attempt_at SET NOT NULL;

ALTER TABLE chatbot.cache_controle
    ALTER COLUMN nome TYPE character varying;

ALTER TABLE chatbot.cliente_bloqueado_meta
    DROP COLUMN id_bloqueio,
    DROP COLUMN id_cliente,
    DROP COLUMN phone_id_unidade,
    DROP COLUMN nome,
    ALTER COLUMN wa_id_cliente TYPE character varying,
    ADD COLUMN bloqueado_em timestamp with time zone,
    ALTER COLUMN bloqueado_em SET DEFAULT now();

ALTER TABLE chatbot.webhook_flood_evento
    DROP COLUMN id_evento,
    DROP COLUMN phone_id_unidade,
    ALTER COLUMN id_hash_msg TYPE character varying,
    ALTER COLUMN id_central SET NOT NULL,
    ALTER COLUMN wa_id_cliente TYPE character varying;

ALTER TABLE chatbot.consumo_mensal_meta
    DROP COLUMN id_registro,
    DROP COLUMN timezone_id,
    DROP COLUMN data_hora_inicio,
    DROP COLUMN data_hora_fim,
    DROP COLUMN qtd_franquia_consumida,
    DROP COLUMN franquia_meta_mensal,
    DROP COLUMN beneficio_esl_mensal,
    DROP COLUMN tarifa_referencia_brl,
    DROP COLUMN tarifa_vigencia,
    DROP COLUMN ultimo_sucesso_em,
    DROP COLUMN status_apuracao,
    DROP COLUMN data_proxima_consolidacao,
    DROP COLUMN ultima_decisao_consolidacao_em,
    DROP COLUMN criado_em,
    DROP COLUMN atualizado_em,
    ALTER COLUMN waba_id TYPE character varying,
    ALTER COLUMN phone_number_id TYPE character varying,
    ADD COLUMN valor_meta numeric(14,6),
    ADD COLUMN moeda character varying(3);

ALTER TABLE chatbot.consumo_meta_coletas
    ALTER COLUMN periodo TYPE character varying;

DROP SEQUENCE chatbot.etapa_id_etapa_seq;

-- Repor as chaves e os limites do modelo de pós-venda nas tabelas reaproveitadas.

ALTER TABLE chatbot.central_pos_venda
    ADD CONSTRAINT central_pos_venda_check CHECK ((((id_fuso IS NULL) AND (nome_fuso IS NULL)) OR ((id_fuso IS NOT NULL) AND (id_fuso > 0) AND (nome_fuso IS NOT NULL) AND (btrim(nome_fuso) <> ''::text)))),
    ADD CONSTRAINT central_pos_venda_check1 CHECK (((NOT ativa) OR ((telefone_moveis IS NOT NULL) AND (telefone_sofas IS NOT NULL)))),
    ADD CONSTRAINT central_pos_venda_check2 CHECK (((telefone_moveis)::text <> (telefone_sofas)::text)),
    ADD CONSTRAINT central_pos_venda_genero_agente_check CHECK ((genero_agente = ANY (ARRAY['masculino'::text, 'feminino'::text]))),
    ADD CONSTRAINT central_pos_venda_nome_agente_check CHECK ((btrim(nome_agente) <> ''::text)),
    ADD CONSTRAINT central_pos_venda_nome_check CHECK ((btrim(nome) <> ''::text)),
    ADD CONSTRAINT central_pos_venda_telefone_moveis_check CHECK (((telefone_moveis)::text ~ '^[1-9][0-9]{7,14}$'::text)),
    ADD CONSTRAINT central_pos_venda_telefone_sofas_check CHECK (((telefone_sofas)::text ~ '^[1-9][0-9]{7,14}$'::text)),
    ADD CONSTRAINT central_pos_venda_pkey PRIMARY KEY (id_central),
    ADD CONSTRAINT central_pos_venda_phone_number_id_key UNIQUE (phone_number_id),
    ADD CONSTRAINT central_pos_venda_telefone_key UNIQUE (telefone);

ALTER TABLE chatbot.cliente
    ADD CONSTRAINT cliente_cidade_loja_compra_check CHECK ((cidade_loja_compra ~ '[^[:space:]]'::text)),
    ADD CONSTRAINT cliente_cpf_titular_check CHECK (((cpf_titular)::text ~ '^[0-9]{11}$'::text)),
    ADD CONSTRAINT cliente_nome_titular_check CHECK ((btrim(nome_titular) <> ''::text)),
    ADD CONSTRAINT cliente_pkey PRIMARY KEY (id_cliente),
    ADD CONSTRAINT cliente_waid_telefone_key UNIQUE (waid_telefone);

ALTER TABLE chatbot.chat
    ADD CONSTRAINT chat_pkey PRIMARY KEY (id_chat),
    ADD CONSTRAINT chat_id_chat_id_central_key UNIQUE (id_chat, id_central),
    ADD CONSTRAINT chat_id_cliente_id_central_key UNIQUE (id_cliente, id_central);

ALTER TABLE chatbot.etapa
    ADD CONSTRAINT etapa_pkey PRIMARY KEY (id_etapa),
    ADD CONSTRAINT etapa_nome_etapa_key UNIQUE (nome_etapa);

ALTER TABLE chatbot.etapa_transicao
    ADD CONSTRAINT etapa_transicao_check CHECK ((id_etapa_origem <> id_etapa_destino)),
    ADD CONSTRAINT etapa_transicao_evento_check CHECK ((btrim((evento)::text) <> ''::text)),
    ADD CONSTRAINT etapa_transicao_pkey PRIMARY KEY (id_transicao),
    ADD CONSTRAINT etapa_transicao_id_etapa_origem_evento_key UNIQUE (id_etapa_origem, evento);

ALTER TABLE chatbot.conversa
    ADD CONSTRAINT conversa_check CHECK ((processing = (processing_started_at IS NOT NULL))),
    ADD CONSTRAINT conversa_check1 CHECK ((status_ativa = (finalizou_em IS NULL))),
    ADD CONSTRAINT conversa_check2 CHECK ((status_ativa = (motivo_encerramento IS NULL))),
    ADD CONSTRAINT conversa_check3 CHECK ((finalizou_em >= iniciou_em)),
    ADD CONSTRAINT conversa_last_message_from_check CHECK (last_message_from IN ('cliente','bot')),
    ADD CONSTRAINT conversa_lock_version_check CHECK ((lock_version >= 0)),
    ADD CONSTRAINT conversa_motivo_encerramento_check CHECK ((motivo_encerramento = ANY (ARRAY['visita_pendente'::text, 'encaminhamento'::text, 'encaminhamento_midia'::text]))),
    ADD CONSTRAINT conversa_turnos_sem_avanco_check CHECK (((turnos_sem_avanco >= 0) AND (turnos_sem_avanco <= 12))),
    ADD CONSTRAINT conversa_pkey PRIMARY KEY (id_conversa),
    ADD CONSTRAINT conversa_id_conversa_id_central_key UNIQUE (id_conversa, id_central);

ALTER TABLE chatbot.fila_mensagens
    ADD CONSTRAINT fila_mensagens_check CHECK ((((status)::text <> 'processing'::text) OR (processing_started_at IS NOT NULL))),
    ADD CONSTRAINT fila_mensagens_retry_count_check CHECK ((retry_count >= 0)),
    ADD CONSTRAINT fila_mensagens_status_check CHECK (status IN ('pending','processing','sent','failed')),
    ADD CONSTRAINT fila_mensagens_pkey PRIMARY KEY (id_mensagem),
    ADD CONSTRAINT fila_mensagens_id_hash_msg_key UNIQUE (id_hash_msg);

ALTER TABLE chatbot.cache_controle
    ADD CONSTRAINT cache_controle_versao_check CHECK ((versao > 0)),
    ADD CONSTRAINT cache_controle_pkey PRIMARY KEY (nome);

ALTER TABLE chatbot.cliente_bloqueado_meta
    ADD CONSTRAINT cliente_bloqueado_meta_pkey PRIMARY KEY (id_central, wa_id_cliente);

ALTER TABLE chatbot.webhook_flood_evento
    ADD CONSTRAINT webhook_flood_evento_pkey PRIMARY KEY (id_hash_msg);

ALTER TABLE chatbot.consumo_mensal_meta
    ADD CONSTRAINT consumo_mensal_meta_check CHECK (((valor_meta IS NULL) = (moeda IS NULL))),
    ADD CONSTRAINT consumo_mensal_meta_mes_referencia_check CHECK ((EXTRACT(day FROM mes_referencia) = (1)::numeric)),
    ADD CONSTRAINT consumo_mensal_meta_moeda_check CHECK (((moeda)::text ~ '^[A-Z]{3}$'::text)),
    ADD CONSTRAINT consumo_mensal_meta_qtd_cobradas_meta_check CHECK ((qtd_cobradas_meta >= 0)),
    ADD CONSTRAINT consumo_mensal_meta_qtd_gratuitas_check CHECK ((qtd_gratuitas >= 0)),
    ADD CONSTRAINT consumo_mensal_meta_valor_meta_check CHECK ((valor_meta >= (0)::numeric)),
    ADD CONSTRAINT consumo_mensal_meta_pkey PRIMARY KEY (id_central, mes_referencia);

ALTER TABLE chatbot.consumo_meta_coletas
    ADD CONSTRAINT consumo_meta_coletas_falhas_consecutivas_check CHECK ((falhas_consecutivas >= 0)),
    ADD CONSTRAINT consumo_meta_coletas_periodo_check CHECK ((((periodo)::text = 'conta'::text) OR ((periodo)::text ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'::text))),
    ADD CONSTRAINT consumo_meta_coletas_pkey PRIMARY KEY (id_central, periodo);

ALTER TABLE chatbot.chat
    ADD CONSTRAINT chat_id_central_fkey FOREIGN KEY (id_central) REFERENCES chatbot.central_pos_venda(id_central),
    ADD CONSTRAINT chat_id_cliente_fkey FOREIGN KEY (id_cliente) REFERENCES chatbot.cliente(id_cliente);

ALTER TABLE chatbot.etapa_transicao
    ADD CONSTRAINT etapa_transicao_id_etapa_destino_fkey FOREIGN KEY (id_etapa_destino) REFERENCES chatbot.etapa(id_etapa),
    ADD CONSTRAINT etapa_transicao_id_etapa_origem_fkey FOREIGN KEY (id_etapa_origem) REFERENCES chatbot.etapa(id_etapa);

ALTER TABLE chatbot.conversa
    ADD CONSTRAINT conversa_id_chat_id_central_fkey FOREIGN KEY (id_chat, id_central) REFERENCES chatbot.chat(id_chat, id_central),
    ADD CONSTRAINT conversa_id_etapa_atual_fkey FOREIGN KEY (id_etapa_atual) REFERENCES chatbot.etapa(id_etapa);

ALTER TABLE chatbot.fila_mensagens
    ADD CONSTRAINT fila_mensagens_id_central_fkey FOREIGN KEY (id_central) REFERENCES chatbot.central_pos_venda(id_central),
    ADD CONSTRAINT fila_mensagens_id_conversa_id_central_fkey FOREIGN KEY (id_conversa, id_central) REFERENCES chatbot.conversa(id_conversa, id_central);

ALTER TABLE chatbot.cliente_bloqueado_meta
    ADD CONSTRAINT cliente_bloqueado_meta_id_central_fkey FOREIGN KEY (id_central) REFERENCES chatbot.central_pos_venda(id_central);

ALTER TABLE chatbot.webhook_flood_evento
    ADD CONSTRAINT webhook_flood_evento_id_central_fkey FOREIGN KEY (id_central) REFERENCES chatbot.central_pos_venda(id_central);

ALTER TABLE chatbot.consumo_mensal_meta
    ADD CONSTRAINT consumo_mensal_meta_id_central_fkey FOREIGN KEY (id_central) REFERENCES chatbot.central_pos_venda(id_central);

ALTER TABLE chatbot.consumo_meta_coletas
    ADD CONSTRAINT consumo_meta_coletas_id_central_fkey FOREIGN KEY (id_central) REFERENCES chatbot.central_pos_venda(id_central);

-- Novos objetos e funções iguais aos do DDL de instalação.

CREATE FUNCTION chatbot.preservar_cidade_loja_compra() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'A cidade da loja já foi registrada para este cliente.'
        USING ERRCODE = '23514';
END;
$$;

CREATE TRIGGER cliente_preserva_cidade BEFORE UPDATE OF cidade_loja_compra ON chatbot.cliente
    FOR EACH ROW WHEN (OLD.cidade_loja_compra IS NOT NULL
                       AND NEW.cidade_loja_compra IS DISTINCT FROM OLD.cidade_loja_compra)
    EXECUTE FUNCTION chatbot.preservar_cidade_loja_compra();

CREATE TABLE chatbot.contato_interno (
    waid_telefone varchar PRIMARY KEY
);

CREATE UNIQUE INDEX conversa_ativa ON chatbot.conversa (id_chat) WHERE status_ativa;

CREATE INDEX conversa_painel ON chatbot.conversa (id_central, id_chat, iniciou_em DESC, id_conversa DESC);

CREATE TYPE chatbot.assunto AS ENUM ('entrega','montador','assistencia','outros');

CREATE TABLE chatbot.atendimento_pos_venda (
    id_conversa int PRIMARY KEY REFERENCES chatbot.conversa,
    nome_titular text CHECK (btrim(nome_titular) <> ''),
    cpf_titular varchar(11) CHECK (cpf_titular ~ '^[0-9]{11}$'),
    cidade_loja_compra text CHECK (cidade_loja_compra ~ '[^[:space:]]'),
    produto text CHECK (produto IN ('estofados','moveis','ambos')),
    assunto chatbot.assunto,
    perdeu_nota boolean,
    foi_a_loja boolean,
    detalhes text CHECK (btrim(detalhes) <> ''),
    encaminhado_moveis varchar CHECK (encaminhado_moveis ~ '^[1-9][0-9]{7,14}$'),
    encaminhado_sofas varchar CHECK (encaminhado_sofas ~ '^[1-9][0-9]{7,14}$'),
    CHECK (encaminhado_moveis <> encaminhado_sofas),
    CHECK (CASE coalesce(produto, 'ambos')
        WHEN 'moveis' THEN encaminhado_sofas IS NULL
        WHEN 'estofados' THEN encaminhado_moveis IS NULL
        ELSE (encaminhado_moveis IS NULL) = (encaminhado_sofas IS NULL)
    END),
    CHECK (foi_a_loja IS NULL OR assunto IS NOT DISTINCT FROM 'assistencia')
);

CREATE TABLE chatbot.etiqueta_conversa (
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    etiqueta chatbot.assunto NOT NULL,
    PRIMARY KEY (id_conversa, etiqueta)
);

CREATE TABLE chatbot.pedido_conversa (
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    numero text NOT NULL CHECK (numero ~ '^[0-9]+[.][0-9]{2}$'),
    PRIMARY KEY (id_conversa, numero)
);

CREATE INDEX fila_pendente ON chatbot.fila_mensagens (next_attempt_at, id_mensagem) WHERE status = 'pending';

CREATE INDEX fila_abandonada ON chatbot.fila_mensagens (processing_started_at) WHERE status = 'processing';

CREATE INDEX fila_turno ON chatbot.fila_mensagens (id_central, cliente_telefone, received_data_hora, id_mensagem)
    WHERE status IN ('pending','processing');

CREATE TABLE chatbot.historico_mensagens (
    id_mensagem bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    id_etapa int NOT NULL REFERENCES chatbot.etapa,
    received_data_hora timestamptz NOT NULL,
    quem_enviou varchar NOT NULL CHECK (quem_enviou IN ('cliente','bot')),
    id_hash_msg varchar NOT NULL UNIQUE,
    id_mensagem_fila int REFERENCES chatbot.fila_mensagens ON DELETE SET NULL,
    id_hash_cliente_origem varchar,
    parte_resposta smallint NOT NULL DEFAULT 1 CHECK (parte_resposta IN (1, 2)),
    CHECK (quem_enviou = 'bot' OR parte_resposta = 1),
    tipo_mensagem varchar NOT NULL,
    conteudo_texto text,
    interativo jsonb,
    status_envio varchar,
    UNIQUE (id_conversa, id_hash_msg),
    FOREIGN KEY (id_conversa, id_hash_cliente_origem) REFERENCES chatbot.historico_mensagens (id_conversa, id_hash_msg),
    CHECK ((quem_enviou = 'cliente' AND id_hash_cliente_origem IS NULL AND status_envio IS NULL)
        OR (quem_enviou = 'bot' AND id_hash_cliente_origem IS NOT NULL
            AND status_envio IS NOT NULL AND status_envio IN ('pending','sent','failed')))
);

CREATE UNIQUE INDEX resposta_por_entrada ON chatbot.historico_mensagens (id_hash_cliente_origem, parte_resposta)
    WHERE quem_enviou = 'bot' AND status_envio = 'sent';

CREATE INDEX historico_turno ON chatbot.historico_mensagens (id_conversa, received_data_hora DESC, id_mensagem DESC);

CREATE INDEX historico_fila ON chatbot.historico_mensagens (id_mensagem_fila) WHERE id_mensagem_fila IS NOT NULL;

CREATE FUNCTION chatbot.lock_conversa(p_id_conversa int)
RETURNS TABLE(lock_ok boolean, lock_version_atual int) LANGUAGE sql AS $$
    WITH tomada AS (
        UPDATE chatbot.conversa SET processing = true, processing_started_at = now(), lock_version = lock_version + 1
        WHERE id_conversa = p_id_conversa
          AND (NOT processing OR processing_started_at < now() - interval '110 seconds')
        RETURNING lock_version
    )
    SELECT v IS NOT NULL, v FROM (SELECT (SELECT lock_version FROM tomada) AS v) s;
$$;

CREATE FUNCTION chatbot.unlock_conversa(p_id_conversa int, p_lock_version int)
RETURNS boolean LANGUAGE sql AS $$
    WITH liberada AS (
        UPDATE chatbot.conversa SET processing = false, processing_started_at = NULL
        WHERE id_conversa = p_id_conversa AND processing AND lock_version = p_lock_version
        RETURNING 1
    )
    SELECT EXISTS (SELECT FROM liberada);
$$;

CREATE FUNCTION chatbot.dequeue_message()
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
            WHERE a.id_central = f.id_central AND a.cliente_telefone = f.cliente_telefone
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

CREATE FUNCTION chatbot.invalidar_cache_centrais() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO chatbot.cache_controle (nome, versao) VALUES ('centrais_pos_venda', 2)
    ON CONFLICT (nome) DO UPDATE SET versao = chatbot.cache_controle.versao + 1, atualizado_em = now();
    RETURN NULL;
END;
$$;

CREATE TRIGGER central_mudou AFTER INSERT OR UPDATE OR DELETE ON chatbot.central_pos_venda
    FOR EACH STATEMENT EXECUTE FUNCTION chatbot.invalidar_cache_centrais();

CREATE INDEX flood_janela ON chatbot.webhook_flood_evento (id_central, wa_id_cliente, received_at DESC);

CREATE INDEX flood_expurgo ON chatbot.webhook_flood_evento (received_at);

CREATE TABLE chatbot.monitoramento_acesso (
    id_usuario_django integer NOT NULL REFERENCES chatbot.auth_user(id) ON DELETE CASCADE,
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    PRIMARY KEY (id_usuario_django, id_central)
);

CREATE INDEX consumo_agenda ON chatbot.consumo_meta_coletas (proxima_consulta_em, id_central);

-- Catálogo e versão inicial do cadastro de centrais.

INSERT INTO chatbot.etapa (id_etapa, nome_etapa, encerra_automaticamente) VALUES
    (1, 'nome_titular', false),
    (2, 'cpf_titular', false),
    (3, 'cidade_loja_compra', false),
    (4, 'produto', false),
    (5, 'assunto', false),
    (6, 'pedidos', false),
    (7, 'visita_loja', false),
    (8, 'visita_pendente', true),
    (9, 'detalhes', false),
    (10, 'encaminhamento', true),
    (11, 'abertura', false);

INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino) VALUES
    (11, 'nome_ausente', 1),
    (11, 'nome_presente_falta_cpf', 2),
    (11, 'retorno_cadastro_completo', 4),
    (11, 'identificacao_completa_falta_cidade', 3),
    (11, 'cadastro_completo_primeiro_atendimento', 4),
    (1, 'nome_valido_falta_cpf', 2),
    (1, 'nome_valido_cpf_presente_falta_cidade', 3),
    (1, 'nome_valido_cpf_e_cidade_presentes', 4),
    (2, 'cpf_valido_falta_cidade', 3),
    (2, 'cpf_valido_cidade_presente', 4),
    (3, 'cidade_informada', 4),
    (4, 'produto_escolhido', 5),
    (5, 'assunto_escolhido', 6),
    (6, 'pedidos_assistencia', 7),
    (6, 'nota_perdida_assistencia', 7),
    (6, 'pedidos_demais_assuntos', 9),
    (6, 'nota_perdida_demais_assuntos', 9),
    (7, 'loja_nao_visitada', 8),
    (7, 'loja_visitada', 9),
    (9, 'situacao_informada', 10),
    (11, 'midia_recebida', 10),
    (1, 'midia_recebida', 10),
    (2, 'midia_recebida', 10),
    (3, 'midia_recebida', 10),
    (4, 'midia_recebida', 10),
    (5, 'midia_recebida', 10),
    (6, 'midia_recebida', 10),
    (7, 'midia_recebida', 10),
    (9, 'midia_recebida', 10);

INSERT INTO chatbot.cache_controle (nome) VALUES ('centrais_pos_venda');

-- Comprovar que a troca manteve as identidades e as leituras que interessam à operação.
DO $conferencia$
BEGIN
    IF (SELECT count(*) FROM chatbot.central_pos_venda) <> (SELECT count(*) FROM pg_temp.unidades_origem)
       OR EXISTS (SELECT FROM chatbot.central_pos_venda WHERE ativa)
       OR EXISTS (SELECT id_unidade, phone_number_id FROM pg_temp.unidades_origem
                  EXCEPT SELECT id_central, phone_number_id FROM chatbot.central_pos_venda) THEN
        RAISE EXCEPTION 'Cadastro de números empresariais divergente';
    END IF;
    IF EXISTS (SELECT * FROM pg_temp.consumo_origem EXCEPT
               SELECT id_central, mes_referencia, waba_id, phone_number_id, fuso_horario,
                      qtd_gratuitas, qtd_cobradas_meta, consultado_ate, consolidado_em
               FROM chatbot.consumo_mensal_meta)
       OR EXISTS (SELECT * FROM pg_temp.agenda_origem EXCEPT
                  SELECT id_central, periodo, proxima_consulta_em, ultima_tentativa_em,
                         falhas_consecutivas, ultimo_erro FROM chatbot.consumo_meta_coletas)
       OR EXISTS (SELECT * FROM pg_temp.bloqueios_origem EXCEPT
                  SELECT id_central, wa_id_cliente FROM chatbot.cliente_bloqueado_meta)
       OR EXISTS (SELECT * FROM pg_temp.flood_origem EXCEPT
                  SELECT id_hash_msg, id_central, wa_id_cliente, received_at FROM chatbot.webhook_flood_evento) THEN
        RAISE EXCEPTION 'Consumo, agenda ou proteção contra flood divergente';
    END IF;
    IF (SELECT count(*) FROM chatbot.etapa) <> 11 OR (SELECT count(*) FROM chatbot.etapa_transicao) <> 29 THEN
        RAISE EXCEPTION 'Catálogo de pós-venda incompleto';
    END IF;
END
$conferencia$;
COMMIT;

SELECT (SELECT count(*) FROM chatbot.etapa) AS etapas,
       (SELECT count(*) FROM chatbot.etapa_transicao) AS transicoes,
       (SELECT count(*) FROM chatbot.central_pos_venda WHERE ativa) AS centrais_ativas,
       (SELECT count(*) FROM chatbot.conversa) AS conversas,
       (SELECT count(*) FROM chatbot.consumo_mensal_meta) AS meses_por_central,
       (SELECT count(*) FROM chatbot.cliente_bloqueado_meta) AS bloqueios_meta;
