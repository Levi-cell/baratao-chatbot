-- Estrutura final para instalação limpa. Os dados das sete etapas e das
-- 21 transições vigentes são inseridos por catalogo.sql na mesma transação.
CREATE TABLE chatbot.catalogo (
    codigo_produto integer PRIMARY KEY CHECK (codigo_produto > 0),
    nome_produto text NOT NULL CHECK (btrim(nome_produto) <> ''),
    categoria text NOT NULL CHECK (categoria IN ('moveis', 'estofado'))
);

CREATE TABLE chatbot.central_pos_venda (
    id_central serial PRIMARY KEY,
    nome text NOT NULL CHECK (btrim(nome) <> ''),
    nome_agente text NOT NULL CHECK (btrim(nome_agente) <> ''),
    genero_agente text NOT NULL CHECK (genero_agente IN ('masculino','feminino')),
    ativa boolean NOT NULL DEFAULT true,
    id_fuso int,
    nome_fuso text,
    fuso_verificado_em timestamptz,
    CHECK ((id_fuso IS NULL AND nome_fuso IS NULL) OR
           (id_fuso IS NOT NULL AND id_fuso > 0 AND nome_fuso IS NOT NULL AND btrim(nome_fuso) <> '')),
    waba_id varchar NOT NULL,
    phone_number_id varchar NOT NULL UNIQUE,
    -- Preencher somente com o ID de conta WhatsApp verificado para este número.
    waac_id varchar UNIQUE CHECK (waac_id ~ '^[1-9][0-9]*$' AND waac_id <> phone_number_id),
    telefone varchar NOT NULL UNIQUE,
    telefone_baratao varchar CHECK (telefone_baratao ~ '^[1-9][0-9]{7,14}$'),
    telefone_atacadao varchar CHECK (telefone_atacadao ~ '^[1-9][0-9]{7,14}$'),
    CHECK (NOT ativa OR (telefone_baratao IS NOT NULL AND telefone_atacadao IS NOT NULL)),
    CHECK (telefone_baratao <> telefone_atacadao)
);

CREATE TABLE chatbot.cliente (
    id_cliente serial PRIMARY KEY,
    waid_telefone varchar UNIQUE,
    username text,
    username_observado_em timestamptz,
    nome_titular text CHECK (btrim(nome_titular) <> ''),
    cpf_titular varchar(11) CHECK (cpf_titular ~ '^[0-9]{11}$'),
    cidade_loja_compra text CHECK (cidade_loja_compra ~ '[^[:space:]]')
);

CREATE INDEX cliente_cpf_conciliacao ON chatbot.cliente (cpf_titular, id_cliente) WHERE cpf_titular IS NOT NULL;

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

CREATE TABLE chatbot.chat (
    id_chat bigserial PRIMARY KEY,
    id_cliente int NOT NULL REFERENCES chatbot.cliente,
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    UNIQUE (id_cliente, id_central),
    UNIQUE (id_chat, id_central)
);

CREATE TABLE chatbot.etapa (
    id_etapa int PRIMARY KEY,
    nome_etapa varchar(100) NOT NULL UNIQUE,
    encerra_automaticamente boolean NOT NULL DEFAULT false,
    bloqueio_dias smallint NOT NULL DEFAULT 0 CHECK (bloqueio_dias IN (0, 90)),
    CHECK (encerra_automaticamente OR bloqueio_dias = 0)
);

CREATE TABLE chatbot.etapa_transicao (
    id_transicao serial PRIMARY KEY,
    id_etapa_origem int NOT NULL REFERENCES chatbot.etapa,
    evento varchar(100) NOT NULL CHECK (btrim(evento) <> ''),
    id_etapa_destino int NOT NULL REFERENCES chatbot.etapa,
    UNIQUE (id_etapa_origem, evento),
    CHECK (id_etapa_origem <> id_etapa_destino)
);

CREATE TABLE chatbot.conversa (
    id_conversa serial PRIMARY KEY,
    id_chat bigint NOT NULL,
    id_central int NOT NULL,
    id_etapa_atual int NOT NULL REFERENCES chatbot.etapa,
    iniciou_em timestamptz NOT NULL DEFAULT now(),
    finalizou_em timestamptz,
    status_ativa boolean NOT NULL DEFAULT true,
    motivo_encerramento text CHECK (motivo_encerramento IN
        ('visita_pendente','encaminhamento','encaminhamento_midia',
         'encaminhamento_humano','encaminhamento_sem_avanco')),
    last_interaction_at timestamptz,
    last_message_from varchar CHECK (last_message_from IN ('cliente','bot')),
    processing boolean NOT NULL DEFAULT false,
    processing_started_at timestamptz,
    lock_version int NOT NULL DEFAULT 0 CHECK (lock_version >= 0),
    turnos_sem_avanco int NOT NULL DEFAULT 0 CHECK (turnos_sem_avanco BETWEEN 0 AND 3),
    FOREIGN KEY (id_chat, id_central) REFERENCES chatbot.chat (id_chat, id_central),
    UNIQUE (id_conversa, id_central),
    CHECK (processing = (processing_started_at IS NOT NULL)),
    CHECK (status_ativa = (finalizou_em IS NULL)),
    CHECK (status_ativa = (motivo_encerramento IS NULL)),
    CHECK (finalizou_em >= iniciou_em)
);

CREATE UNIQUE INDEX conversa_ativa ON chatbot.conversa (id_chat) WHERE status_ativa;
CREATE INDEX conversa_painel ON chatbot.conversa (id_central, id_chat, iniciou_em DESC, id_conversa DESC);

CREATE TYPE chatbot.assunto AS ENUM ('entrega','montador','assistencia','outros','misto');

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
    encaminhado_baratao varchar CHECK (encaminhado_baratao ~ '^[1-9][0-9]{7,14}$'),
    encaminhado_atacadao varchar CHECK (encaminhado_atacadao ~ '^[1-9][0-9]{7,14}$'),
    telefone_compartilhado varchar CHECK (telefone_compartilhado ~ '^[1-9][0-9]{0,14}$'),
    CHECK (encaminhado_baratao <> encaminhado_atacadao),
    CHECK (foi_a_loja IS NULL OR assunto IS NOT DISTINCT FROM 'assistencia')
);

CREATE TABLE chatbot.etiqueta_conversa (
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    etiqueta chatbot.assunto NOT NULL,
    PRIMARY KEY (id_conversa, etiqueta)
);

CREATE TABLE chatbot.filial_compra (
    codigo text PRIMARY KEY CHECK (codigo ~ '^[0-9]{2}$'),
    nome text NOT NULL CHECK (btrim(nome) <> ''),
    grupo text NOT NULL CHECK (grupo IN ('Atacadão','Baratão'))
);

CREATE TABLE chatbot.pedido_conversa (
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    numero text NOT NULL CHECK (numero ~ '^[0-9]+[.][0-9]{2}$'),
    codigo_filial text GENERATED ALWAYS AS (right(numero, 2)) STORED,
    CONSTRAINT pedido_filial_fk FOREIGN KEY (codigo_filial) REFERENCES chatbot.filial_compra(codigo),
    PRIMARY KEY (id_conversa, numero)
);

CREATE TABLE chatbot.fila_mensagens (
    id_mensagem serial PRIMARY KEY,
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    id_conversa int,
    cliente_telefone varchar,
    id_cliente int REFERENCES chatbot.cliente,
    user_id_origem text,
    username_origem text,
    CONSTRAINT fila_identidade_presente CHECK (cliente_telefone IS NOT NULL OR (user_id_origem IS NOT NULL AND id_cliente IS NOT NULL)),
    id_hash_msg varchar NOT NULL UNIQUE,
    received_data_hora timestamptz NOT NULL,
    tipo_mensagem varchar NOT NULL,
    conteudo_texto text,
    interativo jsonb,
    status varchar NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','sent','failed')),
    retry_count int NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    processing_started_at timestamptz,
    last_error text,
    FOREIGN KEY (id_conversa, id_central) REFERENCES chatbot.conversa (id_conversa, id_central),
    CHECK (status <> 'processing' OR processing_started_at IS NOT NULL)
);

CREATE INDEX fila_pendente ON chatbot.fila_mensagens (next_attempt_at, id_mensagem) WHERE status = 'pending';
CREATE INDEX fila_abandonada ON chatbot.fila_mensagens (processing_started_at) WHERE status = 'processing';
CREATE INDEX fila_primeira_identidade ON chatbot.fila_mensagens (id_central, id_cliente, id_mensagem);
CREATE INDEX fila_turno ON chatbot.fila_mensagens (id_central, id_cliente, received_data_hora, id_mensagem)
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
    tipo_destinatario text CHECK (tipo_destinatario IN ('wa_id','bsuid')),
    valor_destinatario text,
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

CREATE TABLE chatbot.identidade_bsuid (
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    user_id text NOT NULL CHECK (btrim(user_id) <> ''),
    id_cliente int NOT NULL REFERENCES chatbot.cliente,
    wamid_origem text NOT NULL,
    suspender_telefone boolean NOT NULL DEFAULT false,
    vigente boolean NOT NULL DEFAULT true,
    PRIMARY KEY (id_central, user_id)
);
CREATE UNIQUE INDEX identidade_bsuid_vigente
    ON chatbot.identidade_bsuid (id_central, id_cliente) WHERE vigente;

CREATE TABLE chatbot.solicitacao_contato (
    id_conversa int PRIMARY KEY REFERENCES chatbot.conversa,
    motivo text NOT NULL CHECK (motivo IN ('cadastro', 'reconfirmacao')),
    id_etapa_retomada int NOT NULL REFERENCES chatbot.etapa,
    bsuid_destino text NOT NULL,
    wamid_solicitacao text NOT NULL,
    wamids_aceitos text[] NOT NULL,
    erros_cliente smallint NOT NULL DEFAULT 0 CHECK (erros_cliente BETWEEN 0 AND 3)
);

CREATE TABLE chatbot.fallback_contato (
    id_conversa int NOT NULL REFERENCES chatbot.conversa,
    id_mensagem_fila int NOT NULL REFERENCES chatbot.fila_mensagens,
    wamid_original text UNIQUE,
    estado text NOT NULL CHECK (estado IN
        ('reservado','em_envio','aceito','incerto','cancelado')),
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_conversa, id_mensagem_fila)
);

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

CREATE TABLE chatbot.cache_controle (
    nome varchar PRIMARY KEY,
    versao bigint NOT NULL DEFAULT 1 CHECK (versao > 0),
    atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION chatbot.invalidar_cache_centrais() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO chatbot.cache_controle (nome, versao) VALUES ('centrais_pos_venda', 2)
    ON CONFLICT (nome) DO UPDATE SET versao = chatbot.cache_controle.versao + 1, atualizado_em = now();
    RETURN NULL;
END;
$$;

CREATE TRIGGER central_mudou AFTER INSERT OR UPDATE OR DELETE ON chatbot.central_pos_venda
    FOR EACH STATEMENT EXECUTE FUNCTION chatbot.invalidar_cache_centrais();

CREATE TABLE chatbot.cliente_bloqueado_meta (
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    wa_id_cliente varchar NOT NULL,
    bloqueado_em timestamptz DEFAULT now(),
    PRIMARY KEY (id_central, wa_id_cliente)
);

CREATE TABLE chatbot.webhook_flood_evento (
    id_hash_msg varchar PRIMARY KEY,
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    wa_id_cliente varchar NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX flood_janela ON chatbot.webhook_flood_evento (id_central, wa_id_cliente, received_at DESC);
CREATE INDEX flood_expurgo ON chatbot.webhook_flood_evento (received_at);

CREATE TABLE chatbot.monitoramento_acesso (
    id_usuario_django integer NOT NULL REFERENCES chatbot.auth_user(id) ON DELETE CASCADE,
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    PRIMARY KEY (id_usuario_django, id_central)
);

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
    -- O total antigo permanece auditável enquanto a Meta recompõe a divisão.
    timezone_id integer,
    data_hora_inicio timestamptz,
    data_hora_fim timestamptz,
    qtd_janela_gratuita bigint,
    qtd_franquia_consumida bigint,
    ultimo_sucesso_em timestamptz,
    status_apuracao text NOT NULL DEFAULT 'pendente_detalhamento',
    data_proxima_consolidacao date,
    ultima_decisao_consolidacao_em timestamptz,
    franquia_meta_mensal integer NOT NULL DEFAULT 1000,
    beneficio_esl_mensal integer NOT NULL DEFAULT 1000,
    tarifa_referencia_brl numeric(12,6) NOT NULL DEFAULT 0.035,
    tarifa_vigencia date NOT NULL DEFAULT '2026-10-01',
    atualizado_em timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id_central, mes_referencia),
    CHECK ((valor_meta IS NULL) = (moeda IS NULL)),
    CONSTRAINT consumo_cobertura_valida CHECK (
        franquia_meta_mensal >= 0 AND beneficio_esl_mensal >= 0 AND tarifa_referencia_brl >= 0),
    CONSTRAINT consumo_detalhamento_valido CHECK (
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
    )
);

CREATE INDEX consumo_pendentes ON chatbot.consumo_mensal_meta (id_central, mes_referencia)
    WHERE status_apuracao <> 'consolidado';

CREATE TABLE chatbot.consumo_meta_coletas (
    id_central int NOT NULL REFERENCES chatbot.central_pos_venda,
    periodo varchar NOT NULL CHECK (periodo = 'conta' OR periodo ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
    proxima_consulta_em timestamptz NOT NULL,
    ultima_tentativa_em timestamptz,
    falhas_consecutivas int NOT NULL DEFAULT 0 CHECK (falhas_consecutivas >= 0),
    ultimo_erro text,
    PRIMARY KEY (id_central, periodo)
);

CREATE INDEX consumo_agenda ON chatbot.consumo_meta_coletas (proxima_consulta_em, id_central);
