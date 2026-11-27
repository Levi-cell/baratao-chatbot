# Identidade WhatsApp do cliente e da central no Baratão

**Beta V0.4.0.** Cada passo reproduz o arquivo completo indicado. Na atualização da V0.2.1, aplicar primeiro a [migração de CPF](../deploy/migrations/20261127_contato_conferencia_cpf.sql). Da V0.3.0, aplicar a [migração das redes](../deploy/migrations/20261127_encaminhamento_por_rede.sql). A identidade escolhe o destinatário das respostas do Theo. A rede das notas escolhe qual contato humano aparecerá no encaminhamento.

## Como usar este plano em outro ambiente

- A Graph API usada pelo cliente de saída vem de META_GRAPH_API_VERSION. O ambiente local usa 27.0. Cada campo do webhook tem a versão escolhida separadamente no painel da Meta.
- Para instalação nova, usar o DDL e o catálogo vigentes. Na base de 25/11 que já contém as filiais, parar webhook e workers e executar o [SQL consolidado](../deploy/migrations/20261126_pendencias_baratao_etapas_sequenciais.sql). Ele inclui os dois complementos de identidade registrados nos passos 2 e 3 e renumera as etapas. Para o fluxo atual, aplicar em seguida o [SQL de sete etapas](../deploy/migrations/20261126_baratao_sete_etapas.sql). Em seguida aplicar a [migração de recoleta do titular](../deploy/migrations/20261126_recoleta_titular.sql). Em toda nova conversa, nome e CPF são confirmados novamente. A solicitação de contato aberta acompanha a renumeração. Partindo do catálogo de 27 transições, aplicar a [migração de repetição por mídia](../deploy/migrations/20261127_midia_repete_etapa.sql). O botão de contato também se repete quando chega mídia.
- A central usa seu WABA ID como Messaging Account ID. Na URL, o Phone Number ID continua disponível durante a transição. Usar um WAAC ID somente após obtê-lo da Meta para aquela central e comprovar acesso do token. O cronograma publicado prevê o novo identificador na fase de 2027 e a transição obrigatória na fase do primeiro semestre de 2028. [Modelo de contas](https://developers.facebook.com/documentation/business-messaging/whatsapp/account-model-evolution/) · [Seleção de conta de mensagens](https://developers.facebook.com/documentation/business-messaging/whatsapp/account-model-evolution/messaging/)
- O atendimento conserva a numeração nome 1, CPF 2 e produto 3. O botão nativo fica entre nome e CPF quando falta o telefone. O quarto erro de compartilhamento encaminha ao pós-venda. Prova válida no quarto turno retoma a etapa. A troca de BSUID assinalada pela Meta suspende a rota telefônica anterior. A próxima interação válida para atendimento permite a reconfirmação dentro da janela. Recibo genérico de falha ou timeout segue a política de erro existente. [Contrato de BSUID e contato](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-scoped-user-ids)
- A origem de cada contato deve vir de webhook autenticado. A confirmação de contato exige a mesma conversa, BSUID, solicitação em aberto e cartão com origem contact_request. Quando o telefone já tem dono, manter a rota pelo BSUID até o CPF. Na etapa 2, priorizar o par CPF e telefone, depois o CPF e por último o telefone confirmado. Desempatar pelo maior ID antigo dentro do grupo. Consolidar os históricos por central e liberar o telefone confirmado para o vencedor após o commit. Quando só o telefone coincide, a ficha vencedora recebe o CPF desta compra e o Theo passa à rota telefônica confirmada. [Critérios e exemplo](conciliacao_cliente_por_cpf.md). O prazo de bloqueio por encaminhamento continua interno e não aciona bloqueio remoto.
- A desativação administrativa usa o campo ativa da central. O worker preserva a mensagem pendente se a central for suspensa durante o turno. O passo do flow_worker documenta a sequência de locks, commits, rollback e recuperação.
- O parâmetro messaging_account_id escolhe a conta de mensagens. A Meta pode determiná-la quando o token só alcança uma conta no número. Se o token alcançar várias, informar a conta explicitamente, inclusive durante o período de transição. O WAAC ID usado no caminho da URL identifica outro recurso.
- O ensaio inclui PostgreSQL local descartável, webhook com HMAC, variação dos três campos de identidade, recuperação do worker e transporte HTTP simulado com Phone Number ID e WAAC. Instalações existentes devem aplicar as migrações correspondentes ao estado do seu catálogo. [Cronograma e critérios de aceite](../CRONOGRAMA_META_2027_2028.md)
- O aceite de produção inclui entrega e clique no aparelho, recebimento no callback e conferência das permissões e dos IDs reais por central. A migração geral do painel varejista e dos relatórios herdados é trabalho separado. Algumas consultas de métricas ainda referenciam estruturas do Supera. As seis etapas de coleta e a etapa 7 de encaminhamento utilizam o contexto do varejo.

## 1. `core/database/deploy_database/schema.sql` (alterar)

```sql
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
    situacao text NOT NULL DEFAULT 'Não encaminhado'
        CONSTRAINT atendimento_situacao_valida CHECK (situacao IN ('Não encaminhado', 'Já encaminhado', 'Aguardando cliente', 'Resolvido')),
    observacao text,
    CHECK (encaminhado_baratao <> encaminhado_atacadao),
    CHECK (foi_a_loja IS NULL OR assunto IS NOT DISTINCT FROM 'assistencia')
);

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
    id_nota bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    CONSTRAINT pedido_filial_fk FOREIGN KEY (codigo_filial) REFERENCES chatbot.filial_compra(codigo),
    CONSTRAINT pedido_conversa_numero_unico UNIQUE (id_conversa, numero)
);

CREATE TABLE chatbot.nota_produtos (
    id_nota bigint NOT NULL REFERENCES chatbot.pedido_conversa(id_nota) ON DELETE RESTRICT,
    codigo_produto integer NOT NULL REFERENCES chatbot.catalogo(codigo_produto) ON DELETE RESTRICT,
    qtd integer NOT NULL DEFAULT 1 CHECK (qtd > 0),
    PRIMARY KEY (id_nota, codigo_produto)
);

CREATE INDEX nota_produtos_por_produto ON chatbot.nota_produtos (codigo_produto, id_nota);

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
```

## 2. `deploy/migrations/20261125_remetente_meta_central.sql` (conservar)

```sql
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
```

## 3. `deploy/migrations/identidade_cliente_pos_venda.sql` (criar)

```sql
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
```

## 4. `core/integrations/whatsapp/remetente.py` (conservar)

```python
"""Identidade empresarial usada pela Messages API durante um turno do pós-venda."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from pywa import WhatsApp
from pywa.api import GraphAPI


from core.database.connection_aws import get_conn
from core.repositories.unidades.consultas import buscar_id_registro_meta


def recurso_registro_meta(phone_number_id):
    with get_conn(application_name="registro_numero_meta") as conn, conn.cursor() as cursor:
        return buscar_id_registro_meta(str(phone_number_id), cursor)


@dataclass(frozen=True)
class RemetenteCentral:
    phone_number_id: str
    messaging_account_id: str
    waac_id: str | None

    @property
    def id_envio(self):
        return self.waac_id or self.phone_number_id


_REMETENTE_DO_TURNO = ContextVar("remetente_do_turno", default=None)


@contextmanager
def usar_remetente_central(central, phone_id_entrada):
    remetente = RemetenteCentral(
        phone_number_id=central["phone_number_id"],
        messaging_account_id=central["messaging_account_id"],
        waac_id=central["waac_id"],
    )
    if remetente.phone_number_id != phone_id_entrada or not remetente.messaging_account_id:
        raise ValueError("Identidade Meta da central incompatível com a entrada da fila.")
    token = _REMETENTE_DO_TURNO.set(remetente)
    try:
        yield
    finally:
        _REMETENTE_DO_TURNO.reset(token)


class _GraphAPICentral(GraphAPI):
    # PyWa 4.5 constrói texto e interativos no mesmo ponto, mas ainda não expõe
    # messaging_account_id. Preserva a serialização, o parsing de erros e os WAMIDs do SDK.
    remetente: RemetenteCentral | None = None

    def _request(self, method, endpoint, **kwargs):
        remetente = self.remetente
        corpo = kwargs.get("json") or {}
        if (remetente and method == "POST" and endpoint.endswith("/messages")
                and ("to" in corpo or "recipient" in corpo)):
            if endpoint != f"/{remetente.id_envio}/messages":
                raise ValueError("O destinatário deve ser atendido pelo remetente da central.")
            kwargs["json"] = {**corpo, "messaging_account_id": remetente.messaging_account_id}
        return super()._request(method, endpoint, **kwargs)


class WhatsAppCentral(WhatsApp):
    _api_cls = _GraphAPICentral

    def __init__(self, *, phone_id, **opcoes):
        remetente = _REMETENTE_DO_TURNO.get()
        if remetente and remetente.phone_number_id != phone_id:
            raise ValueError("O número de envio difere da central do turno.")
        super().__init__(phone_id=remetente.id_envio if remetente else phone_id, **opcoes)
        if remetente:
            self.api.remetente = remetente
```

## 5. `core/integrations/whatsapp/identidade_cliente.py` (criar)

```python
from dataclasses import dataclass
import re

BSUID = re.compile(r"[A-Z]{2}\.[A-Za-z0-9]{1,128}")
TELEFONE = re.compile(r"[1-9][0-9]{0,14}")


def _validar_endereco(valor, padrao):
    if valor is not None and (not isinstance(valor, str) or not padrao.fullmatch(valor)):
        raise ValueError("Identificador de origem inválido")


@dataclass(frozen=True)
class IdentidadeEntrada:
    wa_id: str | None
    user_id: str | None
    username: str | None


def _objetos(valor):
    if isinstance(valor, list):
        yield from (item for item in valor if isinstance(item, dict))


def extrair_identidade(value, mensagem):
    wa, uid = mensagem.get("from"), mensagem.get("from_user_id")
    sistema = mensagem.get("system") or {}
    if mensagem.get("type") == "system":
        if not isinstance(sistema, dict):
            raise ValueError("Evento de identidade inválido")
        uid = uid or sistema.get("user_id") or sistema.get("previous_user_id")
        _validar_endereco(sistema.get("previous_user_id"), BSUID)
        _validar_endereco(sistema.get("user_id"), BSUID)
    _validar_endereco(wa, TELEFONE)
    _validar_endereco(uid, BSUID)
    if not (wa or uid):
        raise ValueError("Mensagem sem identificador de remetente")
    candidatos = []
    for contato in _objetos(value.get("contacts")):
        cw, cu = contato.get("wa_id"), contato.get("user_id")
        if not ((wa and wa == cw) or (uid and uid == cu)):
            continue
        if (wa and cw and wa != cw) or (uid and cu and uid != cu):
            raise ValueError("Identidades divergentes no envelope")
        candidatos.append(contato)
    if len(candidatos) > 1:
        raise ValueError("Contato ambíguo")
    contato = candidatos[0] if candidatos else {}
    wa, uid = wa or contato.get("wa_id"), uid or contato.get("user_id")
    _validar_endereco(wa, TELEFONE)
    _validar_endereco(uid, BSUID)
    perfil = contato.get("profile")
    username = perfil.get("username") if isinstance(perfil, dict) else None
    return IdentidadeEntrada(wa, uid, username if isinstance(username, str) else None)


def eventos_individuais(data):
    """Preserva conta e metadados de cada change e isola o contato do remetente."""
    if not isinstance(data, dict) or data.get("object") != "whatsapp_business_account":
        return
    for entry in _objetos(data.get("entry")):
        for change in _objetos(entry.get("changes")):
            if change.get("field") != "messages":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                continue
            for chave in ("messages", "statuses"):
                for item in _objetos(value.get(chave)):
                    valor = {k: v for k, v in value.items() if k not in {"messages", "statuses"}}
                    valor[chave] = [item]
                    yield {"object": data["object"], "entry": [
                        {**entry, "changes": [{**change, "value": valor}]}
                    ]}


def identificador_entrada(value):
    mensagens=value.get("messages") or []
    if not mensagens:
        return None
    dados=extrair_identidade(value,mensagens[0])
    return dados.wa_id or dados.user_id
```

## 6. `core/repositories/atendimento/identidade_cliente.py` (criar)

```python
def inserir_alias(id_central, user_id, id_cliente, wamid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.identidade_bsuid (id_central, user_id, id_cliente, wamid_origem)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_central, user_id) DO NOTHING
    """, (id_central, user_id, id_cliente, wamid))

def conferir_alias(id_central, user_id, id_cliente, cursor):
    cursor.execute("""
        SELECT id_cliente, vigente FROM chatbot.identidade_bsuid
        WHERE id_central=%s AND user_id=%s FOR UPDATE
    """, (id_central, user_id))
    if cursor.fetchone() != (id_cliente, True):
        raise ValueError("Vínculo de identidade incompatível")

def atualizar_username(id_cliente, username, observado_em, cursor):
    if username:
        cursor.execute("""
            UPDATE chatbot.cliente SET username=%s, username_observado_em=%s
            WHERE id_cliente=%s AND
                  (username_observado_em IS NULL OR username_observado_em < %s)
        """, (username, observado_em, id_cliente, observado_em))


def atualizar_username_por_recibo(central, wamid, uid, telefone, username, observado_em, cursor):
    """Só atualiza um perfil já associado ao destinatário do envio confirmado."""
    cursor.execute("""
        UPDATE chatbot.cliente cl SET username=%s, username_observado_em=%s
        FROM chatbot.historico_mensagens h
        JOIN chatbot.conversa c USING (id_conversa)
        JOIN chatbot.chat ch USING (id_chat)
        WHERE cl.id_cliente=ch.id_cliente AND c.id_central=%s AND h.id_hash_msg=%s
          AND h.quem_enviou='bot' AND h.status_envio='sent'
          AND (cl.username_observado_em IS NULL OR cl.username_observado_em < %s)
          AND ((h.tipo_destinatario='wa_id' AND h.valor_destinatario=%s AND cl.waid_telefone=%s)
              OR (h.tipo_destinatario='bsuid' AND h.valor_destinatario=%s AND EXISTS
                  (SELECT FROM chatbot.identidade_bsuid a WHERE a.id_cliente=cl.id_cliente
                   AND a.id_central=c.id_central AND a.user_id=%s AND a.vigente)))
    """, (username, observado_em, central, wamid, observado_em, telefone, telefone, uid, uid))


def buscar_central(phone_id, conta, cursor, *, incluir_suspensa=False):
    cursor.execute("""
        SELECT id_central FROM chatbot.central_pos_venda
        WHERE phone_number_id=%s AND (ativa OR %s) AND waba_id=%s
    """, (phone_id, incluir_suspensa, conta))
    return cursor.fetchone()


def serializar_chave(chave, cursor):
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (chave,))


def cliente_telefone(wa_id, cursor):
    cursor.execute("SELECT id_cliente FROM chatbot.cliente WHERE waid_telefone=%s FOR UPDATE", (wa_id,))
    linha = cursor.fetchone()
    return linha[0] if linha else None


def buscar_alias(central, uid, cursor):
    cursor.execute("""
        SELECT id_cliente, vigente, suspender_telefone FROM chatbot.identidade_bsuid
        WHERE id_central=%s AND user_id=%s FOR UPDATE
    """, (central, uid))
    return cursor.fetchone()


def alias_vigente_do_cliente(central, cliente, cursor):
    cursor.execute("""
        SELECT user_id FROM chatbot.identidade_bsuid
        WHERE id_central=%s AND id_cliente=%s AND vigente
    """, (central, cliente))
    return cursor.fetchone()


def criar_cliente(telefone, cursor):
    cursor.execute("INSERT INTO chatbot.cliente (waid_telefone) VALUES (%s) RETURNING id_cliente", (telefone,))
    return cursor.fetchone()[0]


def definir_telefone(cliente, telefone, cursor):
    cursor.execute("UPDATE chatbot.cliente SET waid_telefone=%s WHERE id_cliente=%s", (telefone, cliente))


def alias_confirmado(central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET suspender_telefone=false
        WHERE id_central=%s AND user_id=%s AND vigente
    """,(central,uid))


def dados_telefone(cliente, cursor):
    cursor.execute("SELECT waid_telefone FROM chatbot.cliente WHERE id_cliente=%s FOR UPDATE", (cliente,))
    return cursor.fetchone()[0]


def aposentadoria_alias(central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET vigente=false, suspender_telefone=true
        WHERE id_central=%s AND user_id=%s AND vigente
    """, (central,uid))


def preservar_bloqueio_na_rotacao(central, cliente, novo_uid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.cliente_bloqueado_meta (id_central, wa_id_cliente)
        SELECT %s, %s FROM chatbot.cliente cl
        WHERE cl.id_cliente=%s AND EXISTS (
            SELECT FROM chatbot.cliente_bloqueado_meta b WHERE b.id_central=%s
            AND (b.wa_id_cliente=cl.waid_telefone OR b.wa_id_cliente IN (
                SELECT a.user_id FROM chatbot.identidade_bsuid a
                WHERE a.id_cliente=cl.id_cliente AND a.id_central=b.id_central
            )))
        ON CONFLICT DO NOTHING
    """, (central, novo_uid, cliente, central))


def suspender_alias(central, uid, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET suspender_telefone=true
        WHERE id_central=%s AND user_id=%s AND vigente
    """, (central,uid))


def trocar_bsuid_pendente(central, anterior, novo, cursor):
    cursor.execute("""
        DELETE FROM chatbot.solicitacao_contato s USING chatbot.conversa c
        WHERE s.id_conversa=c.id_conversa AND c.id_central=%s AND s.bsuid_destino=%s
        AND %s::text <> s.bsuid_destino
    """, (central,anterior,novo))


def impedimento(central, cliente, identificadores, cursor):
    cursor.execute("""
        SELECT EXISTS (SELECT FROM chatbot.contato_interno WHERE waid_telefone=ANY(%s))
            OR EXISTS (SELECT FROM chatbot.cliente_bloqueado_meta
                       WHERE id_central=%s AND (wa_id_cliente=ANY(%s)
                           OR wa_id_cliente IN (SELECT user_id FROM chatbot.identidade_bsuid
                               WHERE id_cliente=%s AND id_central=%s)))
            OR EXISTS (SELECT FROM chatbot.chat ch JOIN chatbot.conversa c USING(id_chat)
                       JOIN chatbot.etapa e ON e.id_etapa=c.id_etapa_atual
                       WHERE ch.id_cliente=%s AND ch.id_central=%s AND NOT c.status_ativa
                         AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente'
                         AND c.finalizou_em + e.bloqueio_dias * interval '1 day' > now())
    """, (identificadores,central,identificadores,cliente,central,cliente,central))
    return cursor.fetchone()[0]


def falha_da_rota_atual(central, wamid, cursor):
    """Ignora recibo sem correlação, conversa encerrada e resposta já ultrapassada."""
    cursor.execute("""
        SELECT c.id_conversa,h.id_mensagem_fila,a.user_id,a.suspender_telefone
        FROM chatbot.historico_mensagens h JOIN chatbot.conversa c USING(id_conversa)
        JOIN chatbot.chat ch USING(id_chat)
        JOIN chatbot.identidade_bsuid a ON a.id_cliente=ch.id_cliente AND a.id_central=c.id_central AND a.vigente
        WHERE c.id_central=%s AND h.id_hash_msg=%s AND c.status_ativa AND h.tipo_destinatario='wa_id'
          AND h.quem_enviou='bot' AND h.status_envio='sent'
          AND NOT EXISTS(SELECT FROM chatbot.historico_mensagens p WHERE p.id_conversa=c.id_conversa
                         AND (p.received_data_hora,p.id_mensagem)>(h.received_data_hora,h.id_mensagem))
        FOR UPDATE OF c
    """,(central,wamid))
    return cursor.fetchone()
```

## 7. `core/identidade_atendimento.py` (criar)

```python
"""Resolução do cliente sob o lock de cada identificador apresentado pela Meta."""
from dataclasses import dataclass

from core.repositories.atendimento import conciliacao_cliente as conciliacao
from core.repositories.atendimento import identidade_cliente as repo
from core.repositories.seguranca.turno_cliente import avaliar_turno_cliente_para_fila


class IdentidadeDivergente(ValueError):
    pass


def resolver_cliente(dados, central, cursor):
    telefone, uid = dados.get("cliente_telefone"), dados.get("user_id_origem")
    chaves = ([f"wa:{telefone}"] if telefone else []) + ([f"bs:{central}:{uid}"] if uid else [])
    if not chaves:
        raise IdentidadeDivergente("Entrada sem identidade")
    for chave in sorted(chaves):
        repo.serializar_chave(chave,cursor)
    dono = repo.cliente_telefone(telefone,cursor) if telefone else None
    alias = repo.buscar_alias(central,uid,cursor) if uid else None
    if alias and (not alias[1] or (dono and alias[0] != dono)):
        raise IdentidadeDivergente("Identificadores conflitantes ou alias inativo")
    cliente = dono or (alias[0] if alias else None)
    if cliente is None:
        cliente = repo.criar_cliente(telefone,cursor)
    if uid and not alias:
        if repo.alias_vigente_do_cliente(central, cliente, cursor):
            raise IdentidadeDivergente("Cliente já possui outro BSUID vigente nesta central")
        repo.inserir_alias(central,uid,cliente,dados["id_hash_msg"],cursor)
        repo.conferir_alias(central,uid,cliente,cursor)
    if telefone and alias and not alias[2]:
        anterior = repo.dados_telefone(cliente,cursor)
        if anterior and anterior != telefone:
            raise IdentidadeDivergente("Mudança de telefone sem prova de continuidade")
        if anterior is None:
            repo.definir_telefone(cliente,telefone,cursor)
    repo.atualizar_username(cliente,dados.get("username_origem"),dados["received_data_hora"],cursor)
    return cliente


def rotacionar_bsuid(central, sistema, wamid, cursor):
    anterior, novo = sistema.get("previous_user_id"), sistema.get("user_id")
    if not anterior or not novo or anterior == novo:
        return False
    for uid in sorted((anterior,novo)):
        repo.serializar_chave(f"bs:{central}:{uid}",cursor)
    alias = repo.buscar_alias(central,anterior,cursor)
    if not alias or not alias[1]:
        return False
    if repo.buscar_alias(central,novo,cursor):
        raise IdentidadeDivergente("Novo identificador já vinculado")
    # Um telefone abandonado pode ser reatribuído a outra pessoa. A continuação
    # deste cadastro exige o identificador vinculado e um novo contato oficial.
    repo.preservar_bloqueio_na_rotacao(central, alias[0], novo, cursor)
    repo.definir_telefone(alias[0], None, cursor)
    repo.aposentadoria_alias(central,anterior,cursor)
    repo.inserir_alias(central,novo,alias[0],wamid,cursor)
    repo.suspender_alias(central,novo,cursor)
    repo.trocar_bsuid_pendente(central,anterior,novo,cursor)
    return True


@dataclass(frozen=True)
class ResultadoConciliacao:
    # Sem ID global, o CPF é guardado somente no atendimento deste turno.
    cadastro_para_cpf: int | None
    cache: dict | None = None


def escolher_cadastro_vencedor(candidatos, origem, cpf, telefone):
    """Compara dados anteriores à etapa 2. O maior ID desempata cada grupo."""
    prioridades = []
    for cliente, cpf_anterior, wa, tem_historico in candidatos:
        if cliente == origem and cpf_anterior is None and not tem_historico:
            continue  # O provisório não disputa o desempate com as fichas antigas.
        mesmo_cpf = cpf_anterior == cpf
        mesmo_telefone = wa == telefone
        if mesmo_cpf or mesmo_telefone:
            prioridades.append((mesmo_cpf, mesmo_telefone, cliente))
    return max(prioridades)[2] if prioridades else origem


def conciliar_apos_cpf(contexto, cpf, cursor):
    """Decide antes de gravar o CPF novo. Os efeitos usam a transação do worker."""
    origem = contexto["id_cliente"]
    telefone = contexto.get("telefone_compartilhado") or contexto.get("wa_id_confirmado")
    if not telefone:
        return ResultadoConciliacao(origem)

    central = contexto["id_central"]
    conversa = contexto["id_conversa"]
    uid = contexto.get("bsuid_vigente")
    if uid:
        repo.serializar_chave(f"bs:{central}:{uid}", cursor)
    repo.serializar_chave(f"cpf:{cpf}", cursor)
    repo.serializar_chave(f"wa:{telefone}", cursor)
    candidatos = conciliacao.candidatos_para_cpf(origem, cpf, telefone, conversa, cursor)
    vencedor = escolher_cadastro_vencedor(candidatos, origem, cpf, telefone)
    telefones = {cliente: wa for cliente, _, wa, _ in candidatos}
    perdedores = [cliente for cliente in telefones if cliente != vencedor]
    if not perdedores:
        return ResultadoConciliacao(vencedor)

    clientes = list(telefones)
    conciliacao.bloquear_chats(clientes, cursor)
    aliases = conciliacao.bloquear_aliases(clientes, cursor)
    if uid and (central, uid, origem, True, False) not in aliases:
        return ResultadoConciliacao(None)
    if contexto.get("telefone_compartilhado"):
        if conciliacao.telefone_em_conferencia(central, uid, cursor) != telefone:
            return ResultadoConciliacao(None)
    elif telefones.get(origem) != telefone:
        return ResultadoConciliacao(None)

    entrada = contexto["mensagem_cliente_atual"]
    numeros_envolvidos = sorted({wa for wa in telefones.values() if wa} | {telefone})
    if (conciliacao.identificador_bloqueado(numeros_envolvidos, clientes, cursor)
            or conciliacao.ha_bloqueio_temporario(clientes, cursor)
            or conciliacao.ha_trabalho_em_andamento(clientes, numeros_envolvidos, conversa,
                                                   entrada["id_mensagem_fila"], cursor)):
        return ResultadoConciliacao(None)
    for cliente in clientes:
        if cliente != origem:
            turno = avaliar_turno_cliente_para_fila(cursor, cliente, contexto["id_phone_unidade"],
                                                   entrada["received_data_hora"], usar_lock=True)
            if not turno["pode_enfileirar"]:
                return ResultadoConciliacao(None)

    # Um BSUID histórico não pode encaminhar outro remetente ao telefone novo.
    # Conserve vínculos vigentes do vencedor em outras centrais se CPF e telefone coincidem.
    mesmo_titular_e_numero = any(cliente == vencedor and anterior == cpf and wa == telefone
                                 for cliente, anterior, wa, _ in candidatos)
    aposentados = []
    for c, u, dono, ativo, _ in aliases:
        rota_atual = (c, u, dono) == (central, uid, origem)
        outra_central_preservada = c != central and dono == vencedor and mesmo_titular_e_numero
        if ativo and not (rota_atual or outra_central_preservada):
            repo.aposentadoria_alias(c, u, cursor)
            aposentados.append((c, u))

    conciliacao.garantir_chats_do_vencedor(vencedor, perdedores, cursor)
    conciliacao.mover_fila(perdedores, vencedor, cursor)
    conciliacao.mover_conversas(perdedores, vencedor, cursor)
    conciliacao.mover_aliases(perdedores, vencedor, cursor)
    conciliacao.liberar_telefone(perdedores, telefone, cursor)
    conciliacao.atualizar_cadastro_pela_conversa(conversa, vencedor, telefone, cursor)
    conciliacao.guardar_telefone_compartilhado(conversa, None, cursor)
    conciliacao.excluir_chats_vazios(perdedores, cursor)
    conciliacao.excluir_cadastros_redundantes(perdedores, cursor)
    return ResultadoConciliacao(vencedor, {
        "cliente": vencedor, "telefone": telefone, "central": central, "uid": uid,
        "telefones_antigos": [wa for wa in telefones.values() if wa and wa != telefone],
        "aliases_antigos": aposentados,
    })
```

## 8. `callback/monitoramento/apresentacao.py` (alterar)

```python
"""Transformações puras dos dados do painel, sem acesso ao banco."""

import re

from core.etapas_pos_venda import ETAPA_PEDIDOS, ETAPA_PRODUTO
from core.integrations.whatsapp.messages.etapa3_messages import BOTOES_PRODUTO
from core.integrations.whatsapp.messages.etapa5_pedidos_messages import BOTAO_NOTA_PERDIDA


# Ordem e grafia do modelo CSV distribuído pelo Google Contacts.
CABECALHO_CSV_GOOGLE_CONTATOS = (
    'Name Prefix',
    'First Name',
    'Middle Name',
    'Last Name',
    'Name Suffix',
    'Phonetic First Name',
    'Phonetic Middle Name',
    'Phonetic Last Name',
    'Nickname',
    'File As',
    'E-mail 1 - Label',
    'E-mail 1 - Value',
    'Phone 1 - Label',
    'Phone 1 - Value',
    'Address 1 - Label',
    'Address 1 - Country',
    'Address 1 - Street',
    'Address 1 - Extended Address',
    'Address 1 - City',
    'Address 1 - Region',
    'Address 1 - Postal Code',
    'Address 1 - PO Box',
    'Organization Name',
    'Organization Title',
    'Organization Department',
    'Birthday',
    'Event 1 - Label',
    'Event 1 - Value',
    'Relation 1 - Label',
    'Relation 1 - Value',
    'Website 1 - Label',
    'Website 1 - Value',
    'Custom Field 1 - Label',
    'Custom Field 1 - Value',
    'Notes',
    'Labels',
)


def botoes_para_mensagem(mensagem):
    tipo = str(mensagem.get('tipo') or '')
    if mensagem.get('quem_enviou') != 'bot' or not tipo.startswith('interactive'):
        return []
    interativo = mensagem.get('interativo') or {}
    acao = interativo.get('action') or {}
    if acao:
        if acao.get('buttons'):
            return [botao['reply']['title'] for botao in acao['buttons'] if botao.get('reply', {}).get('title')]
        if acao.get('sections'):
            return [linha['title'] for secao in acao['sections'] for linha in secao.get('rows', []) if linha.get('title')]
        if acao.get('parameters', {}).get('display_text'):
            return [acao['parameters']['display_text']]
        if acao.get('cards'):
            rotulos = []
            for card in acao['cards']:
                parametros = card.get('action', {}).get('parameters', {})
                rotulo = parametros.get('display_text') or card.get('body', {}).get('text')
                if rotulo:
                    rotulos.append(rotulo)
            return rotulos
        return []
    # Respostas anteriores à gravação do payload interativo.
    if mensagem.get('id_etapa') == ETAPA_PRODUTO:
        return [titulo for titulo, _ in BOTOES_PRODUTO]
    if mensagem.get('id_etapa') == ETAPA_PEDIDOS:
        return [BOTAO_NOTA_PERDIDA]
    return []


def classificar_faixa(idade):
    if type(idade) is not int or idade <= 0 or idade >= 100:
        return None
    if idade < 18:
        return 'menor'
    if idade < 60:
        return 'adulto'
    return 'idoso'


def _perfil_resumido(status_dependente, faixa):
    if status_dependente is True:
        return f'dependente_{faixa}' if faixa else 'dependente'
    if status_dependente is False:
        return faixa
    return None


def consolidar_conversas(linhas):
    # Defesa adicional para consumidores que não passaram pela seleção SQL.
    representantes = {}
    historico = {}
    for linha in linhas:
        cid = linha['id_cliente']
        historico.setdefault(cid, set()).update(linha.get('ids_conversa_periodo') or [linha['id_conversa']])
        chave = (str(linha.get('iniciou_em') or ''), linha['id_conversa'])
        if cid not in representantes or chave > representantes[cid]:
            representantes[cid] = chave
    linhas = [l for l in linhas if (str(l.get('iniciou_em') or ''), l['id_conversa']) == representantes[l['id_cliente']]]
    clientes = {}
    for linha in linhas:
        cliente = clientes.setdefault(linha['id_cliente'], {
            'id_cliente': linha['id_cliente'],
            'id_conversa_atual': linha['id_conversa'],
            'destinatario': ('dependente' if linha.get('status_dependente') is True else
                             'titular' if linha.get('status_dependente') is False else None),
            'origem': linha.get('origem'),
            'nome': nome_exibido_no_painel(linha.get('nome_cliente'), linha.get('username')),
            'contato': linha.get('waid_telefone') or '',
            'email': linha.get('email') or '',
            'profissao': linha.get('profissao_cliente') or linha.get('profissao_conversa') or '',
            'ids_conversa': [], 'perfis': set(), 'perfis_resumidos': set(),
            'dependentes': set(),
            'foi_funil': False, 'avaliada': False, 'followup_stage': 0,
            'ultima_atividade': None, 'ultima_mensagem': '',
            'ultima_mensagem_id': None, 'turno': None,
        })
        cliente['ids_conversa'].append(linha['id_conversa'])
        cliente['foi_funil'] |= bool(linha.get('foi_funil'))
        cliente['avaliada'] |= bool(linha.get('avaliada'))
        # A consulta já exclui o follow-up de atendimentos substituídos por outro.
        cliente['followup_stage'] = max(
            cliente['followup_stage'], linha.get('followup_stage_atual') or 0,
        )
        status_dependente = linha.get('status_dependente')
        dependente = status_dependente is True
        if dependente:
            cliente['perfis'].add('dependente')
            if linha.get('nome_dependente'):
                cliente['dependentes'].add(str(linha['nome_dependente']))
        idade = (
            linha.get('idade_dependente') if dependente
            else linha.get('idade_titular') if status_dependente is False
            else None
        )
        faixa = classificar_faixa(idade)
        if faixa:
            cliente['perfis'].add(faixa)
        perfil_resumido = _perfil_resumido(status_dependente, faixa)
        if perfil_resumido:
            cliente['perfis_resumidos'].add(perfil_resumido)
        atividade = linha.get('ultima_atividade')
        id_mensagem = linha.get('ultima_mensagem_id') or 0
        if atividade and (
            cliente['ultima_atividade'] is None
            or atividade > cliente['ultima_atividade']
            or (
                atividade == cliente['ultima_atividade']
                and id_mensagem > (cliente['ultima_mensagem_id'] or 0)
            )
        ):
            cliente['turno'] = linha.get('turno')
            cliente['ultima_atividade'] = atividade
            cliente['ultima_mensagem'] = linha.get('ultima_mensagem') or ''
            cliente['ultima_mensagem_id'] = linha.get('ultima_mensagem_id')
    ordem = {'dependente': 0, 'menor': 1, 'adulto': 2, 'idoso': 3}
    ordem_resumida = {
        'dependente_menor': 0,
        'dependente_adulto': 1,
        'dependente_idoso': 2,
        'menor': 3,
        'adulto': 4,
        'idoso': 5,
        'dependente': 6,
    }
    for cliente in clientes.values():
        cliente['ids_conversa'] = sorted(historico[cliente['id_cliente']])
        cliente['perfis'] = sorted(cliente['perfis'], key=lambda item: ordem[item])
        cliente['perfis_resumidos'] = sorted(
            cliente['perfis_resumidos'], key=lambda item: ordem_resumida[item]
        )
        cliente['dependentes'] = sorted(cliente['dependentes'])
    return sorted(clientes.values(), key=lambda item: item['ultima_atividade'] or '', reverse=True)


def normalizar_telefone_google(valor):
    digitos = re.sub(r'\D', '', str(valor or ''))
    if len(digitos) in (10, 11):
        digitos = '55' + digitos
    if not re.fullmatch(r'[1-9]\d{7,14}', digitos):
        return ''
    return '+' + digitos


def separar_nome(valor):
    partes = str(valor or '').strip().split()
    if not partes:
        return '', ''
    return partes[0], ' '.join(partes[1:])


def proteger_celula_csv(valor):
    texto = str(valor or '')
    return "'" + texto if texto.startswith(('=', '+', '-', '@')) else texto


CABECALHO_CSV_ESSENCIAL = ('Nome', 'E-mail', 'Telefone')


def montar_linha_csv_essencial(*, primeiro_nome, sobrenome, email, telefone):
    """Mantém o nome completo em uma coluna, sem acrescentar rótulos comerciais."""
    nome = ' '.join(parte for parte in (primeiro_nome, sobrenome) if parte)
    # O telefone já está normalizado; remove só o código do Brasil, mantendo o DDD.
    telefone_essencial = telefone.removeprefix('+55')
    return [proteger_celula_csv(nome), proteger_celula_csv(email), telefone_essencial]


def montar_linha_csv_google_contatos(
    *,
    primeiro_nome,
    sobrenome,
    email,
    telefone,
    nome_unidade,
):
    """Posiciona os dados nas colunas exatas do modelo do Google Contacts."""
    valores = {
        'First Name': proteger_celula_csv(primeiro_nome),
        'Last Name': proteger_celula_csv(sobrenome),
        'E-mail 1 - Label': 'Work' if email else '',
        'E-mail 1 - Value': proteger_celula_csv(email),
        'Phone 1 - Label': 'Mobile' if telefone else '',
        'Phone 1 - Value': telefone,
        'Notes': 'Contato exportado pelo monitoramento ESL Tech',
        'Labels': proteger_celula_csv(nome_unidade),
    }
    return [valores.get(coluna, '') for coluna in CABECALHO_CSV_GOOGLE_CONTATOS]


def montar_relatorio(
    metricas, anteriores, perfis, satisfacao, etapas, atividade,
):
    def variacao(atual, anterior):
        if atual is None or anterior is None:
            return None
        if anterior == 0:
            return 100.0 if atual else 0.0
        return round((atual - anterior) / anterior * 100, 1)
    tendencias = {}
    for chave in ('leads', 'mensagens', 'funil', 'avaliacoes', 'nota_media'):
        tendencias[chave] = variacao(metricas.get(chave, 0), anteriores.get(chave) if anteriores else None)
    return {
        'metricas': metricas,
        'tendencias': tendencias,
        'perfis': perfis,
        'satisfacao': satisfacao,
        'etapas': etapas,
        'atividade': atividade,
    }


def nome_exibido_no_painel(nome_titular, username):
    if nome_titular:
        return nome_titular
    if username:
        return f"@{username.lstrip('@')}"
    return "Contato não compartilhado"
```

## 9. `callback/webhook/services/flood_guard.py` (alterar)

```python
import logging

from django.http import JsonResponse

from core.cache.runtime.cache_flood_redis import avaliar_flood_redis
from core.cache.cache_flood_memoria import avaliar_flood_memoria
from core.database.connection_aws import get_conn
from core.integrations.whatsapp.tools.usuarios import (
    bloquear_usuario_meta,
)
from core.integrations.whatsapp.identidade_cliente import identificador_entrada
from core.logging_config import short_value
from core.repositories.seguranca.bloqueio_meta import (
    buscar_central_para_bloqueio,
    contar_eventos_flood_banco,
    limpar_eventos_flood_antigos,
    registrar_cliente_bloqueado_meta_banco,
    registrar_evento_flood_banco,
)
from .alerta_flood_memoria import registrar_alerta_flood_memoria


logger = logging.getLogger("webhook.flood_guard")

REGRAS_FLOOD = (
    {
        "nome": "rajada_curta",
        "limite": 15,
        "janela_segundos": 5,
    },
)


def responder_se_flood(data, *, chave_flood=None):
    phone_id_unidade = _extrair_phone_number_id(data)
    wa_id_cliente = _extrair_cliente_telefone(data)
    id_hash_msg = _extrair_id_hash_msg(data)

    flood = bloquear_cliente_se_flood(
        wa_id_cliente,
        phone_id_unidade,
        id_hash_msg,
        chave_flood=chave_flood,
    )

    if not flood["bloqueado"]:
        return None

    logger.warning(
        "mensagem_ignorada | motivo=%s regra=%s "
        "acao=bloqueio_local_nao_enfileirar cliente=%s phone_number_id=%s "
        "total=%s persistencia_ok=%s meta_ok=%s",
        flood["motivo"],
        flood.get("regra"),
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        flood["total"],
        flood.get("persistencia_ok"),
        flood.get("meta_ok"),
    )

    if flood.get("reentregar"):
        return JsonResponse(
            {
                "status": "unavailable",
                "reason": flood["motivo"],
            },
            status=503,
        )

    return JsonResponse({
        "status": "ignored",
        "reason": flood["motivo"],
    })


def bloquear_cliente_se_flood(
    wa_id_cliente,
    phone_id_unidade,
    id_hash_msg,
    nome_cliente=None,
    *, chave_flood=None,
):
    if not wa_id_cliente or not phone_id_unidade or not id_hash_msg:
        return {
            "bloqueado": False,
            "motivo": "dados_invalidos",
            "total": 0,
            "regra": None,
            "meta_ok": None,
        }

    rate_redis = avaliar_flood_redis(
        chave_flood or wa_id_cliente,
        phone_id_unidade,
        id_hash_msg,
        regras=REGRAS_FLOOD,
    )

    if rate_redis["redis_ok"]:
        if rate_redis["flood"]:
            return _bloquear_e_registrar(
                wa_id_cliente,
                phone_id_unidade,
                origem="redis",
                total=rate_redis["total"],
                regra=rate_redis["regra"],
            )

        return {
            "bloqueado": False,
            "motivo": "abaixo_limite_redis",
            "total": rate_redis["total"],
            "regra": None,
            "meta_ok": None,
        }

    rate_banco = _avaliar_flood_banco(
        chave_flood or wa_id_cliente,
        phone_id_unidade,
        id_hash_msg,
    )

    if rate_banco["flood"]:
        return _bloquear_e_registrar(
            wa_id_cliente,
            phone_id_unidade,
            origem="banco",
            total=rate_banco["total"],
            regra=rate_banco["regra"],
        )

    if not rate_banco["banco_ok"]:
        rate_memoria = avaliar_flood_memoria(
            chave_flood or wa_id_cliente,
            phone_id_unidade,
            id_hash_msg,
            regras=REGRAS_FLOOD,
        )

        if rate_memoria["flood"]:
            return _bloquear_via_memoria_e_alertar(
                wa_id_cliente,
                phone_id_unidade,
                total=rate_memoria["total"],
                regra=rate_memoria["regra"],
                id_hash_msg=id_hash_msg,
            )

        return {
            "bloqueado": False,
            "motivo": rate_memoria["motivo"],
            "total": rate_memoria["total"],
            "regra": None,
            "meta_ok": None,
        }

    return {
        "bloqueado": False,
        "motivo": rate_banco["motivo"],
        "total": rate_banco["total"],
        "regra": None,
        "meta_ok": None,
    }


def _avaliar_flood_banco(wa_id_cliente, phone_id_unidade, id_hash_msg):
    conn = None

    try:
        conn = get_conn(application_name="webhook_chatbot")
        cursor = conn.cursor()

        registrar_evento_flood_banco(
            wa_id_cliente,
            phone_id_unidade,
            id_hash_msg,
            cursor,
        )
        maior_total = 0
        total = 0
        regra_estourada = None

        for regra in REGRAS_FLOOD:
            total = contar_eventos_flood_banco(
                wa_id_cliente,
                phone_id_unidade,
                cursor,
                janela_segundos=regra["janela_segundos"],
            )

            maior_total = max(maior_total, total)

            if total >= regra["limite"]:
                regra_estourada = regra
                break

        limpar_eventos_flood_antigos(cursor)

        conn.commit()

        return {
            "banco_ok": True,
            "flood": regra_estourada is not None,
            "total": total if regra_estourada else maior_total,
            "motivo": "banco",
            "regra": regra_estourada["nome"] if regra_estourada else None,
        }

    except Exception as exc:
        if conn:
            conn.rollback()

        logger.warning(
            "rate_limit_banco_falhou | acao=seguir_fluxo wa_id_cliente=%s phone_id_unidade=%s erro=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
            exc,
        )
        return {
            "banco_ok": False,
            "flood": False,
            "total": 0,
            "motivo": "banco_indisponivel",
            "regra": None,
        }

    finally:
        if conn:
            conn.close()


def _bloquear_via_memoria_e_alertar(
    wa_id_cliente,
    phone_id_unidade,
    total,
    regra,
    id_hash_msg,
):
    resultado = _bloquear_e_registrar(
        wa_id_cliente,
        phone_id_unidade,
        origem="memoria",
        total=total,
        regra=regra,
    )

    registrar_alerta_flood_memoria(
        wa_id_cliente=wa_id_cliente,
        phone_id_unidade=phone_id_unidade,
        origem="memoria",
        regra=regra,
        total=total,
        meta_ok=resultado.get("meta_ok"),
        motivo=resultado["motivo"],
        id_hash_msg=id_hash_msg,
        erro_meta=resultado.get("erro_meta"),
    )

    logger.warning(
        "flood_bloqueado_memoria | acao=alertar regra=%s "
        "wa_id_cliente=%s phone_id_unidade=%s total=%s "
        "persistencia_ok=%s meta_ok=%s reentregar=%s",
        regra,
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        total,
        resultado.get("persistencia_ok"),
        resultado.get("meta_ok"),
        resultado.get("reentregar"),
    )
    return resultado


def _bloquear_e_registrar(wa_id_cliente, phone_id_unidade, origem, total, regra):
    resultado = {
        "bloqueado": True,
        "motivo": f"flood_{origem}",
        "total": total,
        "regra": regra,
        "persistencia_ok": False,
        "meta_ok": None,
        "erro_meta": None,
        "reentregar": False,
    }
    central = None
    try:
        with get_conn(application_name="webhook_chatbot") as conn, conn.cursor() as cursor:
            central = buscar_central_para_bloqueio(phone_id_unidade, cursor)
            if central is None:
                resultado["motivo"] += "_unidade_nao_cadastrada"
                return resultado
            registrar_cliente_bloqueado_meta_banco(wa_id_cliente, central["id_central"], cursor)
    except Exception:
        logger.exception("flood_persistencia_falhou | phone_id_unidade=%s", short_value(phone_id_unidade))
        resultado["motivo"] += "_persistencia_local_falhou" if central else "_banco_indisponivel"
        resultado["reentregar"] = True
        return resultado

    # O contexto da conexão psycopg já confirmou a denylist antes do HTTP.
    resultado["persistencia_ok"] = True
    try:
        bloquear_usuario_meta(wa_id_cliente, phone_id_unidade, central=central)
        resultado["meta_ok"] = True
    except Exception as exc:
        resultado["meta_ok"] = False
        resultado["erro_meta"] = str(exc)
        resultado["motivo"] += "_meta_falhou"
        logger.warning(
            "flood_bloqueio_meta_falhou | acao=repetir_em_nova_mensagem id_central=%s erro=%s",
            central["id_central"], type(exc).__name__,
        )
    return resultado


def _extrair_phone_number_id(data):
    value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    metadata = value.get("metadata", {})
    return metadata.get("phone_number_id")


def _extrair_cliente_telefone(data):
    value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    return identificador_entrada(value)


def _extrair_id_hash_msg(data):
    value = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})
    messages = value.get("messages", [{}])
    return messages[0].get("id") if messages else None
```

## 10. `callback/webhook/services/populating_fila_mensagens.py` (alterar)

```python
from core.repositories.atendimento.solicitacao_contato import pendencia_ativa
from core.repositories.atendimento.identidade_cliente import buscar_alias, serializar_chave, cliente_telefone
from core.validacoes.compartilhamento_contato import telefone_compartilhado
from core.integrations.whatsapp.identidade_cliente import extrair_identidade
from core.identidade_atendimento import IdentidadeDivergente, resolver_cliente, rotacionar_bsuid
from core.repositories.atendimento.conciliacao_cliente import telefone_em_conferencia
from core.repositories.atendimento.identidade_cliente import buscar_central, dados_telefone, impedimento
import logging
from datetime import datetime, timezone

from core.logging_config import short_value
from core.repositories.atendimento.entrada_fila import entrada_ja_registrada, inserir_entrada_fila
from core.repositories.seguranca.turno_cliente import (
    avaliar_turno_cliente_para_fila,
)


logger = logging.getLogger("webhook.fila")


def inserir_dados_na_tabela_fila(dados, cursor):
    if not dados or dados.get("erro"):
        logger.warning("fila_insert_ignorado | motivo=dados_invalidos acao=nao_inserir")
        return {
            "status": "ignored",
            "reason": "dados_invalidos",
        }

    linha = buscar_central(dados["id_phone_unidade"], dados.get("conta_origem"), cursor,
                          incluir_suspensa=dados["tipo_mensagem"] == "system")
    if not linha:
        return {"status": "ignored", "reason": "central_incompativel"}
    central = dados["id_central"] = linha[0]
    if dados["tipo_mensagem"] == "system":
        sistema = dados["sistema"]
        if sistema.get("type") in {"user_changed_user_id", "user_changed_number"}:
            rotacionar_bsuid(central, sistema, dados["id_hash_msg"], cursor)
        return {"status": "ignored", "reason": "evento_tecnico"}
    if entrada_ja_registrada(dados["id_hash_msg"], cursor):
        return {"status": "ignored", "reason": "conflito_unico"}
    uid = dados.get("user_id_origem")
    if uid:
        serializar_chave(f"bs:{central}:{uid}", cursor)
    contato, motivo = _prova_solicitada(dados, uid, cursor)
    telefone_da_conversa = telefone_em_conferencia(central, uid, cursor) if uid else None
    telefone_envelope = dados.get("cliente_telefone")
    if (contato or telefone_da_conversa) and not dados.get("assinatura_verificada"):
        return {"status": "ignored", "reason": "contato_exige_assinatura"}
    # Um cartão oficial e as respostas posteriores podem trazer também o WA ID.
    # A conversa continua pelo BSUID até ser possível decidir sobre o cadastro.
    if telefone_da_conversa and telefone_envelope and telefone_envelope != telefone_da_conversa:
        raise IdentidadeDivergente("O telefone mudou durante a conferência do cadastro.")
    segue_por_bsuid = bool(contato or telefone_da_conversa)
    origem = {**dados, "cliente_telefone": None} if segue_por_bsuid else dados
    cliente = dados["id_cliente"] = resolver_cliente(origem, central, cursor)
    ids = [v for v in (dados_telefone(cliente, cursor), uid, contato, telefone_da_conversa) if v]
    if impedimento(central, cliente, ids, cursor):
        return {"status": "ignored", "reason": "cliente_impedido"}

    if contato:
        serializar_chave(f"wa:{contato}", cursor)
        canonica = cliente_telefone(contato, cursor)
        if canonica and canonica != cliente and impedimento(central, canonica, ids, cursor):
            return {"status": "ignored", "reason": "cliente_impedido"}
        dados["interativo"]["_telefone_verificado"] = contato
        if canonica and canonica != cliente:
            if motivo != "cadastro":
                return {"status": "ignored", "reason": "contato_exige_conciliacao"}
            dados["interativo"]["_telefone_em_outro_cadastro"] = True
            dados["cliente_telefone"] = None
    elif segue_por_bsuid:
        # Evita publicar no cache do telefone ou bloquear o outro dono ao encerrar.
        dados["cliente_telefone"] = None

    turno = avaliar_turno_cliente_para_fila(
        cursor=cursor,
        id_cliente=cliente,
        id_phone_unidade=dados["id_phone_unidade"],
        received_data_hora=dados["received_data_hora"],
        usar_lock=True,
    )

    if not turno["pode_enfileirar"]:
        if turno["motivo"] == "fila_aberta_sem_resposta_bot":
            logger.info(
                "mensagem_ignorada | motivo=fila_aberta_pending_processing acao=nao_enfileirar cliente=%s phone_number_id=%s detalhe=ja_existe_mensagem_pending_ou_processing",
                short_value(dados["cliente_telefone"]),
                short_value(dados["id_phone_unidade"]),
            )
        elif turno["motivo"] == "mensagem_reentregue_fora_de_ordem":
            logger.info(
                "mensagem_ignorada | motivo=mensagem_reentregue_fora_de_ordem acao=nao_enfileirar cliente=%s phone_number_id=%s received_data_hora=%s",
                short_value(dados["cliente_telefone"]),
                short_value(dados["id_phone_unidade"]),
                dados["received_data_hora"],
            )
        else:
            logger.info(
                "fila_insert_ignorado | motivo=%s acao=nao_inserir_turno cliente=%s phone_number_id=%s",
                turno["motivo"],
                short_value(dados["cliente_telefone"]),
                short_value(dados["id_phone_unidade"]),
            )

        return {
            "status": "ignored",
            "reason": turno["motivo"],
        }

    id_mensagem = inserir_entrada_fila(dados, cursor)

    if id_mensagem is None:
        logger.info(
            "fila_insert_ignorado | motivo=conflito_unico acao=nao_inserir id_msg=%s cliente=%s phone_number_id=%s",
            short_value(dados["id_hash_msg"]),
            short_value(dados["cliente_telefone"]),
            short_value(dados["id_phone_unidade"]),
        )
        return {
            "status": "ignored",
            "reason": "conflito_unico",
        }

    return {
        "status": "inserted",
        "reason": None,
        "id_mensagem": id_mensagem,
    }


def _prova_solicitada(dados, uid, cursor):
    if not uid or dados["tipo_mensagem"] != "contacts":
        return None, None
    central = dados["id_central"]
    alias = buscar_alias(central, uid, cursor)
    if not alias or not alias[1]:
        return None, None
    pendencia = pendencia_ativa(central, alias[0], uid, cursor)
    if not pendencia:
        return None, None
    prova = telefone_compartilhado(dados["interativo"] or {}, uid, pendencia[0])
    if prova and dados.get("cliente_telefone") not in (None, prova):
        raise IdentidadeDivergente("O telefone do envelope diverge do cartão solicitado.")
    return prova, pendencia[1]


def extrair_dados_whatsapp(data):
    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        if not value.get("messages"):
            return {
                "erro": "evento_sem_mensagem",
                "raw": data,
            }

        metadata = value.get("metadata", {})
        unidade_telefone = metadata.get("display_phone_number")
        id_phone_unidade = metadata.get("phone_number_id")

        message = value.get("messages", [{}])[0]
        identidade = extrair_identidade(value, message)
        cliente_telefone = identidade.wa_id
        message_id = message.get("id")
        timestamp = message.get("timestamp")
        tipo = message.get("type")
        conteudo_texto = extrair_conteudo_texto_mensagem(message, tipo)

        # O timestamp da Meta representa um instante Unix em UTC. Mantemos o
        # fuso explícito para o PostgreSQL não reinterpretar um datetime
        # ingênuo conforme o timezone configurado na role da aplicação.
        received_data_hora = datetime.fromtimestamp(
            int(timestamp),
            tz=timezone.utc,
        )

        if not all([
            cliente_telefone or identidade.user_id,
            message_id,
            id_phone_unidade,
            unidade_telefone,
            tipo,
        ]):
            return {
                "erro": "dados_incompletos",
                "raw": data,
            }

        return {
            "user_id_origem": identidade.user_id, "username_origem": identidade.username,
            "conta_origem": entry.get("id"), "sistema": message.get("system", {}),
            "interativo": ({k: message[k] for k in ("type","from_user_id","context","contacts") if k in message}
                           if tipo == "contacts" else message.get("interactive")),
            "status": "pending",
            "retry_count": 0,
            "next_attempt_at": received_data_hora,
            "processing_started_at": None,
            "received_data_hora": received_data_hora,
            "cliente_telefone": cliente_telefone,
            "conteudo_texto": conteudo_texto,
            "tipo_mensagem": tipo,
            "id_hash_msg": message_id,
            "id_phone_unidade": id_phone_unidade,
            "unidade_telefone": unidade_telefone,
        }

    except (IndexError, KeyError, TypeError, ValueError) as erro:
        return {
            "erro": "exception",
            "detalhe": str(erro),
            "raw": data,
        }


def extrair_conteudo_texto_mensagem(message, tipo):
    if tipo == "text":
        return message.get("text", {}).get("body")

    if tipo in {"interactive", "interactive_button"}:
        # A Meta envia interactive; aceitamos também o alias interactive_button.
        # O worker recebe apenas a resposta selecionada, nunca o texto citado
        # da mensagem anterior (que pode mencionar os três turnos).
        interactive = message.get("interactive") or message.get("interactive_button", {})
        return extrair_conteudo_interactive(interactive)

    if tipo == "button":
        return extrair_conteudo_button(message.get("button", {}))

    return None


def extrair_conteudo_interactive(interactive):
    if not isinstance(interactive, dict):
        return None
    tipo_interactive = interactive.get("type")

    if tipo_interactive == "button_reply":
        button_reply = interactive.get("button_reply", {})
        return _extrair_texto_opcao(button_reply, "title", "id")

    if tipo_interactive == "list_reply":
        list_reply = interactive.get("list_reply", {})
        return _extrair_texto_opcao(list_reply, "title", "id")

    return None


def extrair_conteudo_button(button):
    return _extrair_texto_opcao(button, "text", "payload")


def _extrair_texto_opcao(opcao, campo_texto, campo_identificador):
    """Prioriza o rótulo; sem ele, aceita o callback textual já usado pelo bot."""
    if not isinstance(opcao, dict):
        return None
    for campo in (campo_texto, campo_identificador):
        valor = opcao.get(campo)
        if isinstance(valor, str) and valor.strip():
            return valor.strip()
    return None


def preparar_dados_fila(data):
    dados = extrair_dados_whatsapp(data)

    if dados.get("erro"):
        logger.warning(
            "fila_extracao_falhou | motivo=%s acao=nao_enfileirar",
            dados.get("erro"),
        )
        return {
            "status": "ignored",
            "reason": dados.get("erro"),
            "dados": None,
        }

    logger.info(
        "fila_recebida | acao=preparar_insert id_msg=%s cliente=%s phone_number_id=%s tipo=%s",
        short_value(dados["id_hash_msg"]),
        short_value(dados["cliente_telefone"]),
        short_value(dados["id_phone_unidade"]),
        dados["tipo_mensagem"],
    )
    return {
        "status": "ready",
        "reason": None,
        "dados": dados,
    }


def povoando_fila(dados, cursor):
    return inserir_dados_na_tabela_fila(dados, cursor)
```

## 11. `callback/webhook/services/post_flow.py` (alterar)

```python
from core.integrations.whatsapp.identidade_cliente import eventos_individuais, extrair_identidade
from core.identidade_atendimento import IdentidadeDivergente
import json
import logging
from datetime import datetime, timezone

from django.conf import settings
from django.http import JsonResponse

from core.cache.runtime.cache_conversas_bloqueadas import (
    ValidacaoBloqueioConversaIndisponivel,
    conversa_esta_bloqueada_cache,
)
from core.cache.runtime.cache_webhook_erro_inesperado import (
    MAX_RESPOSTAS_503_POR_WAMID,
    registrar_tentativa_erro_inesperado,
)
from core.cache.cache_unidade import (
    ValidacaoUnidadeIndisponivel,
    unidade_esta_ativa,
)
from core.database.connection_aws import get_conn
from core.logging_config import referencia_wamid, short_value
from .bloqueio_meta_guard import (
    verificar_protecao_remetente,
)
from .flood_guard import responder_se_flood
from .meta_signature import validar_assinatura_meta
from .populating_fila_mensagens import preparar_dados_fila, povoando_fila


logger = logging.getLogger("webhook.post_flow")
fila_logger = logging.getLogger("webhook.fila")

TIPO_EVENTO_MENSAGEM = "messages"
TIPO_EVENTO_STATUS = "statuses"
TIPO_EVENTO_DESCONHECIDO = "unknown"


def responder_post_webhook(request):
    if resposta := _validar_content_type(request):
        return resposta

    if resposta := _validar_tamanho_body(request):
        return resposta

    if not validar_assinatura_meta(request):
        logger.warning(
            "mensagem_ignorada | motivo=assinatura_meta_invalida acao=retornar_403 path=%s",
            request.path,
        )
        return JsonResponse({"status": "forbidden"}, status=403)

    try:
        data = json.loads(request.body.decode("utf-8"))

    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "mensagem_ignorada | motivo=json_invalido acao=nao_enfileirar erro=%s",
            exc,
        )
        return JsonResponse({
            "status": "ignored",
            "reason": "invalid_json",
        })

    resposta = None
    for evento in eventos_individuais(data):
        resposta = _processar_evento(request, evento)
        if resposta.status_code >= 400:
            return resposta
    return resposta if resposta is not None else JsonResponse({"status": "ok"})


def _processar_evento(request,data):
    phone_number_id = None
    cliente_telefone = None

    try:
        tipo_evento = _classificar_evento_meta(data)

        if tipo_evento == TIPO_EVENTO_STATUS:
            return _registrar_status_identidade(data)

        if tipo_evento != TIPO_EVENTO_MENSAGEM:
            logger.info(
                "evento_meta_ignorado | motivo=evento_sem_messages_ou_statuses acao=retornar_200",
            )
            return JsonResponse({"status": "ok"})

        phone_number_id = _extrair_phone_number_id(data)
        try:
            valor = _extrair_value(data)
            identidade = extrair_identidade(valor, valor["messages"][0])
            cliente_telefone = identidade.wa_id or identidade.user_id
        except ValueError:
            logger.info("mensagem_ignorada | motivo=identidade_ausente_ou_invalida")
            return JsonResponse({"status": "ignored", "reason": "identidade_ausente_ou_invalida"})
        if _extrair_value(data)["messages"][0].get("type") == "system":
            resultado = preparar_dados_fila(data)
            if resultado["status"]=="ready":
                gravado = _executar_transacao_fila(resultado["dados"])
                if gravado["status"] == "error":
                    return JsonResponse({"status":"unavailable"},status=503)
            return JsonResponse({"status":"ok"})

        resposta_bloqueio, chave_flood = verificar_protecao_remetente(
            cliente_telefone,
            phone_number_id,
            identificadores=[v for v in (identidade.wa_id, identidade.user_id) if v],
            conta_origem=data["entry"][0].get("id"),
        )
        if resposta_bloqueio is not None:
            return resposta_bloqueio

        if resposta_flood := responder_se_flood(data, chave_flood=chave_flood):
            return resposta_flood

        if not unidade_esta_ativa(phone_number_id):
            logger.info(
                "mensagem_ignorada | motivo=unidade_inativa acao=nao_enfileirar cliente=%s phone_number_id=%s",
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )
            return JsonResponse({"status": "ignored"})

        if cliente_telefone and conversa_esta_bloqueada_cache(
            cliente_telefone,
            phone_number_id,
        ):
            logger.info(
                "mensagem_ignorada | motivo=conversa_bloqueada acao=nao_enfileirar cliente=%s phone_number_id=%s",
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )
            return JsonResponse({
                "status": "ignored",
                "reason": "blocked_conversation",
            })

        preparacao_fila = preparar_dados_fila(data)

        if preparacao_fila["status"] == "ready":
            preparacao_fila["dados"]["assinatura_verificada"] = settings.META_WEBHOOK_SIGNATURE_REQUIRED
            resultado_fila = _executar_transacao_fila(preparacao_fila["dados"])

        else:
            resultado_fila = {
                "status": "ignored",
                "reason": preparacao_fila["reason"],
            }

        if resultado_fila["status"] == "ignored":
            logger.info(
                "mensagem_ignorada | motivo=%s acao=nao_enfileirar cliente=%s phone_number_id=%s",
                resultado_fila["reason"],
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )

        elif resultado_fila["status"] != "inserted":
            logger.error(
                "request_indisponivel | motivo=%s acao=retornar_503_para_reentrega cliente=%s phone_number_id=%s",
                resultado_fila["reason"],
                short_value(cliente_telefone),
                short_value(phone_number_id),
            )
            return JsonResponse({
                "status": "unavailable",
                "reason": resultado_fila["reason"],
            }, status=503)

    except ValidacaoUnidadeIndisponivel as exc:
        logger.error(
            "request_indisponivel | motivo=validacao_unidade_indisponivel acao=retornar_503_para_reentrega cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(phone_number_id),
            exc,
        )
        return JsonResponse({
            "status": "unavailable",
            "reason": "unit_validation_unavailable",
        }, status=503)

    except ValidacaoBloqueioConversaIndisponivel as exc:
        logger.error(
            "request_indisponivel | motivo=validacao_bloqueio_conversa_indisponivel acao=retornar_503_para_reentrega cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(phone_number_id),
            exc,
        )
        return JsonResponse({
            "status": "unavailable",
            "reason": "conversation_block_validation_unavailable",
        }, status=503)

    except Exception as exc:
        id_hash_msg = _extrair_id_hash_msg_seguro(data)
        tentativa = registrar_tentativa_erro_inesperado(
            id_hash_msg,
        )

        if tentativa["retornar_503"]:
            logger.exception(
                "request_erro | "
                "acao=retornar_503_para_reentrega "
                "metodo=%s path=%s id_hash_msg=%s "
                "tentativa=%s limite_503=%s",
                request.method,
                request.path,
                short_value(id_hash_msg),
                tentativa["tentativa"],
                MAX_RESPOSTAS_503_POR_WAMID,
            )
            return JsonResponse(
                {
                    "status": "unavailable",
                    "reason": "unexpected_error_retry",
                    "attempt": tentativa["tentativa"],
                },
                status=503,
            )

        logger.error(
            "request_erro | "
            "acao=retornar_200_e_ignorar "
            "metodo=%s path=%s id_hash_msg=%s "
            "tentativa=%s motivo=%s",
            request.method,
            request.path,
            short_value(id_hash_msg),
            tentativa["tentativa"],
            tentativa["motivo"],
            exc_info=(
                type(exc),
                exc,
                exc.__traceback__,
            ),
        )
        reason = (
            "unexpected_error_retry_exhausted"
            if tentativa["motivo"]
            == "limite_503_esgotado"
            else "unexpected_error_retry_unavailable"
        )
        return JsonResponse({
            "status": "ignored",
            "reason": reason,
        })

    return JsonResponse({"status": "ok"})


def _classificar_evento_meta(data):
    value = _extrair_value(data)
    possui_mensagens = bool(value.get("messages"))
    possui_statuses = bool(value.get("statuses"))

    if possui_mensagens and not possui_statuses:
        return TIPO_EVENTO_MENSAGEM

    if possui_statuses and not possui_mensagens:
        return TIPO_EVENTO_STATUS

    return TIPO_EVENTO_DESCONHECIDO


def _registrar_status_identidade(data):
    from core.repositories.atendimento.identidade_cliente import atualizar_username_por_recibo, buscar_central
    valor = _extrair_value(data)
    status = valor["statuses"][0]
    tipo = status.get("status")
    if tipo not in {"delivered", "read", "failed"} or not status.get("id"):
        return JsonResponse({"status":"ok"})
    if tipo == "failed":
        _registrar_falha_entrega(data, status)
        return JsonResponse({"status": "ok"})

    logger.debug("recibo_meta | status=%s ref_envio=%s", tipo, referencia_wamid(status["id"]))
    try:
        identidade = extrair_identidade(valor, {"from": status.get("recipient_id"),
                                                "from_user_id": status.get("recipient_user_id")})
        observado_em = datetime.fromtimestamp(int(status["timestamp"]), timezone.utc)
    except (KeyError, ValueError, TypeError, OverflowError, OSError):
        return JsonResponse({"status": "ignored"})
    if not identidade.username:
        return JsonResponse({"status": "ok"})
    with get_conn(application_name="webhook_status") as conn, conn.cursor() as cursor:
        central = buscar_central(_extrair_phone_number_id(data), data["entry"][0].get("id"), cursor)
        if central:
            atualizar_username_por_recibo(central[0], status["id"], identidade.user_id,
                                          identidade.wa_id, identidade.username, observado_em, cursor)
    return JsonResponse({"status": "ok"})


def _registrar_falha_entrega(data, status):
    from core.repositories.atendimento.identidade_cliente import buscar_central, falha_da_rota_atual
    from core.repositories.atendimento.fallback_contato import reservar_reconfirmacao

    central = tentativa = None
    recuperacao = "verificacao_inconclusiva"
    try:
        with get_conn(application_name="webhook_status") as conn, conn.cursor() as cursor:
            central = buscar_central(_extrair_phone_number_id(data), data["entry"][0].get("id"), cursor)
            tentativa = falha_da_rota_atual(central[0], status["id"], cursor) if central else None
            resultado = "nao_aplicavel"
            # Só a suspensão confirmada da rota autoriza a reconfirmação.
            if tentativa and tentativa[3]:
                nova = reservar_reconfirmacao(tentativa[0], tentativa[1], status["id"], cursor)
                resultado = "reservada" if nova else "ja_reservada"
        recuperacao = resultado  # O contexto da conexão já confirmou a transação.
    finally:
        erros = status.get("errors")
        codigos = []
        if isinstance(erros, list):
            for erro in erros:
                codigo = str(erro.get("code", "")) if isinstance(erro, dict) else ""
                if codigo.isascii() and codigo.isdecimal():
                    codigos.append(codigo)
        logger.warning(
            "entrega_meta_falhou | ref_envio=%s codigos_meta=%s id_central=%s "
            "id_mensagem=%s id_conversa=%s recuperacao=%s",
            referencia_wamid(status["id"]), ",".join(codigos) or "-",
            central[0] if central else "-", tentativa[1] if tentativa else "-",
            tentativa[0] if tentativa else "-", recuperacao,
        )


def _executar_transacao_fila(dados):
    conn_webhook = None

    try:
        conn_webhook = get_conn(application_name="webhook_chatbot")
        cursor_webhook = conn_webhook.cursor()
        resultado = povoando_fila(dados, cursor_webhook)
        conn_webhook.commit()

        if resultado["status"] == "inserted":
            fila_logger.info(
                "fila_insert_ok | status=enfileirado id_mensagem=%s id_central=%s tipo=%s",
                resultado["id_mensagem"], dados["id_central"],
                dados["tipo_mensagem"],
            )

        return resultado

    except IdentidadeDivergente:
        conn_webhook.rollback()
        fila_logger.warning("mensagem_ignorada | motivo=identidade_divergente")
        return {"status": "ignored", "reason": "identidade_divergente"}
    except Exception:
        if conn_webhook:
            conn_webhook.rollback()

        fila_logger.exception(
            "fila_insert_erro | acao=rollback id_msg=%s",
            short_value(dados.get("id_hash_msg") if dados else None),
        )
        return {
            "status": "error",
            "reason": "insert_exception",
        }

    finally:
        if conn_webhook:
            conn_webhook.close()


def _validar_content_type(request):
    content_type = (request.content_type or "").lower()

    if content_type.startswith("application/json"):
        return None

    logger.warning(
        "mensagem_ignorada | motivo=content_type_invalido acao=retornar_415 content_type=%s",
        content_type or None,
    )
    return JsonResponse({"status": "unsupported_media_type"}, status=415)


def _validar_tamanho_body(request):
    limite_bytes = settings.WEBHOOK_MAX_BODY_BYTES
    tamanho_header = request.headers.get("Content-Length")

    if tamanho_header:
        try:
            tamanho_bytes = int(tamanho_header)

        except ValueError:
            logger.warning(
                "mensagem_ignorada | motivo=content_length_invalido acao=retornar_400 content_length=%s",
                tamanho_header,
            )
            return JsonResponse({"status": "bad_request"}, status=400)

        if tamanho_bytes > limite_bytes:
            logger.warning(
                "mensagem_ignorada | motivo=body_muito_grande acao=retornar_413 tamanho_bytes=%s limite_bytes=%s origem=content_length",
                tamanho_bytes,
                limite_bytes,
            )
            return JsonResponse({"status": "payload_too_large"}, status=413)

    tamanho_real = len(request.body)

    if tamanho_real > limite_bytes:
        logger.warning(
            "mensagem_ignorada | motivo=body_muito_grande acao=retornar_413 tamanho_bytes=%s limite_bytes=%s origem=request_body",
            tamanho_real,
            limite_bytes,
        )
        return JsonResponse({"status": "payload_too_large"}, status=413)

    return None


def _extrair_value(data):
    return (
        data.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
    )


def _extrair_phone_number_id(data):
    metadata = _extrair_value(data).get("metadata", {})
    return metadata.get("phone_number_id")





def _extrair_id_hash_msg_seguro(data):
    try:
        value = _extrair_value(data)
        messages = value.get("messages")

        if (
            not isinstance(messages, list)
            or not messages
            or not isinstance(messages[0], dict)
        ):
            return None

        id_hash_msg = messages[0].get("id")

        if id_hash_msg is None:
            return None

        id_hash_msg = str(id_hash_msg).strip()
        return id_hash_msg or None

    except Exception:
        return None
```

## 12. `core/cache/runtime/cache_cliente.py` (alterar)

```python
import logging

from core.cache.redis_client import get_redis_safe
from core.logging_config import short_value


logger = logging.getLogger("cache.cliente")

REDIS_PREFIX = "baratao:cliente_cache:"
CLIENTE_CACHE_TTL_SEGUNDOS = 60 * 60 * 24 * 180


def buscar_cliente_cache(waid_telefone):
    key = _montar_key_cliente(waid_telefone)

    if key is None:
        return None

    try:
        r = get_redis_safe(retries=1, delay=0, validate=False)
        id_cliente = r.get(key)

        if id_cliente is None:
            logger.debug(
                "cliente_cache_miss | acao=fallback_banco cliente=%s",
                short_value(waid_telefone),
            )
            return None

        id_cliente = int(id_cliente)

        if id_cliente <= 0:
            logger.warning(
                "cliente_cache_valor_invalido | acao=fallback_banco cliente=%s valor=%s",
                short_value(waid_telefone),
                id_cliente,
            )
            remover_cliente_cache(waid_telefone)
            return None

        logger.debug(
            "cliente_cache_hit | acao=usar_cache cliente=%s id_cliente=%s",
            short_value(waid_telefone),
            id_cliente,
        )
        return id_cliente

    except (TypeError, ValueError) as exc:
        logger.warning(
            "cliente_cache_parse_falhou | acao=fallback_banco cliente=%s erro=%s",
            short_value(waid_telefone),
            exc,
        )
        remover_cliente_cache(waid_telefone)
        return None

    except Exception as exc:
        logger.warning(
            "cliente_cache_indisponivel | acao=fallback_banco cliente=%s erro=%s",
            short_value(waid_telefone),
            exc,
        )
        return None


def salvar_cliente_cache(waid_telefone, id_cliente, *, id_central=None, tipo="wa_id"):
    key = chave_lookup_cliente(id_central,tipo,waid_telefone)

    if key is None or not _id_cliente_valido(id_cliente):
        logger.warning(
            "cliente_cache_salvar_ignorado | motivo=dados_invalidos acao=seguir_sem_cache cliente=%s id_cliente=%s",
            short_value(waid_telefone),
            id_cliente,
        )
        return False

    try:
        r = get_redis_safe(retries=1, delay=0, validate=False)
        r.setex(key, CLIENTE_CACHE_TTL_SEGUNDOS, int(id_cliente))

        logger.debug(
            "cliente_cache_salvo | acao=salvar_redis cliente=%s id_cliente=%s ttl=%s",
            short_value(waid_telefone),
            id_cliente,
            CLIENTE_CACHE_TTL_SEGUNDOS,
        )
        return True

    except Exception as exc:
        logger.warning(
            "cliente_cache_salvar_falhou | acao=seguir_sem_cache cliente=%s id_cliente=%s erro=%s",
            short_value(waid_telefone),
            id_cliente,
            exc,
        )
        return False


def remover_cliente_cache(waid_telefone, *, id_central=None, tipo="wa_id"):
    key = chave_lookup_cliente(id_central, tipo, waid_telefone)

    if key is None:
        return False

    try:
        r = get_redis_safe(retries=1, delay=0, validate=False)
        r.delete(key)

        logger.debug(
            "cliente_cache_removido | acao=remover_redis cliente=%s",
            short_value(waid_telefone),
        )
        return True

    except Exception as exc:
        logger.warning(
            "cliente_cache_remover_falhou | acao=ignorar cliente=%s erro=%s",
            short_value(waid_telefone),
            exc,
        )
        return False


def _montar_key_cliente(waid_telefone):
    if waid_telefone is None:
        return None

    telefone = str(waid_telefone).strip()

    if not telefone:
        return None

    return f"{REDIS_PREFIX}{telefone}"


def _id_cliente_valido(id_cliente):
    try:
        return int(id_cliente) > 0
    except (TypeError, ValueError):
        return False


def chave_lookup_cliente(id_central, tipo, valor):
    if tipo == "wa_id":
        return _montar_key_cliente(valor)
    if tipo == "bsuid" and valor:
        return f"{REDIS_PREFIX}bsuid:{id_central}:{valor}"
    raise ValueError("Identidade de cache ausente ou desconhecida")
```

## 13. `core/cache/runtime/cache_conversas_bloqueadas.py` (conservar)

```python
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from core.database.connection_aws import get_conn
from core.cache.redis_client import get_redis_safe
from core.logging_config import short_value
from core.repositories.fluxo.politicas import (
    buscar_bloqueio_ativo_por_cliente_unidade,
)


logger = logging.getLogger("cache.bloqueia_conversa")

REDIS_PREFIX = "baratao:conversa_bloqueada"


class ValidacaoBloqueioConversaIndisponivel(Exception):
    pass


def conversa_esta_bloqueada_cache(cliente_telefone, id_phone_unidade):
    key = _cache_key(cliente_telefone, id_phone_unidade)

    if key is None:
        return False

    try:
        r = get_redis_safe(retries=1, delay=0, validate=False)
        if r.exists(key):
            return True
        # Um cache vazio não apaga um bloqueio confirmado no PostgreSQL.

    except Exception as exc:
        logger.warning(
            "cache_bloqueio_indisponivel | acao=fallback_banco cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(id_phone_unidade),
            exc,
        )

    return _conversa_esta_bloqueada_banco_e_repara_cache(
        cliente_telefone,
        id_phone_unidade,
    )


def registrar_bloqueio_conversa_cache(
    cliente_telefone,
    id_phone_unidade,
    finalizou_em,
    bloqueio_dias,
    redis_retries=1,
    redis_delay=0,
):
    key = _cache_key(cliente_telefone, id_phone_unidade)

    if key is None:
        return False

    ttl = _calcular_ttl(finalizou_em, bloqueio_dias)

    if ttl <= 0:
        logger.info(
            "cache_bloqueio_ignorado | motivo=ttl_expirado acao=nao_registrar cliente=%s phone_number_id=%s",
            short_value(cliente_telefone),
            short_value(id_phone_unidade),
        )
        return False

    payload = {
        "cliente_telefone": str(cliente_telefone),
        "id_phone_unidade": str(id_phone_unidade),
        "finalizou_em": str(finalizou_em) if finalizou_em else "",
        "bloqueio_dias": str(bloqueio_dias),
    }

    try:
        r = get_redis_safe(retries=redis_retries, delay=redis_delay, validate=False)
        with r.pipeline(transaction=True) as pipe:
            pipe.hset(key, mapping=payload)
            pipe.expire(key, ttl)
            pipe.execute()

        logger.info(
            "cache_bloqueio_registrado | acao=registrar cliente=%s phone_number_id=%s ttl=%s",
            short_value(cliente_telefone),
            short_value(id_phone_unidade),
            ttl,
        )
        return True

    except Exception as exc:
        logger.warning(
            "cache_bloqueio_registrar_falhou | acao=ignorar cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(id_phone_unidade),
            exc,
        )
        return False


def remover_bloqueio_conversa_cache(
    cliente_telefone,
    id_phone_unidade,
    redis_retries=1,
    redis_delay=0,
):
    key = _cache_key(cliente_telefone, id_phone_unidade)

    if key is None:
        return False

    try:
        r = get_redis_safe(retries=redis_retries, delay=redis_delay, validate=False)
        return bool(r.delete(key))

    except Exception as exc:
        logger.warning(
            "cache_bloqueio_remover_falhou | acao=ignorar cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(id_phone_unidade),
            exc,
        )
        return False


def _conversa_esta_bloqueada_banco_e_repara_cache(
    cliente_telefone,
    id_phone_unidade,
):
    conn = None

    try:
        conn = get_conn(application_name="webhook_chatbot")
        cursor = conn.cursor()

        bloqueio = buscar_bloqueio_ativo_por_cliente_unidade(
            cliente_telefone,
            id_phone_unidade,
            cursor,
        )

        if bloqueio is None:
            remover_bloqueio_conversa_cache(
                cliente_telefone,
                id_phone_unidade,
                redis_retries=1,
                redis_delay=0,
            )
            return False

        registrar_bloqueio_conversa_cache(
            cliente_telefone,
            id_phone_unidade,
            bloqueio.finalizou_em,
            bloqueio.bloqueio_dias,
            redis_retries=1,
            redis_delay=0,
        )

        return True

    except Exception as exc:
        logger.exception(
            "fallback_banco_bloqueio_falhou | acao=levantar_indisponibilidade cliente=%s phone_number_id=%s erro=%s",
            short_value(cliente_telefone),
            short_value(id_phone_unidade),
            exc,
        )
        raise ValidacaoBloqueioConversaIndisponivel(
            "Nao foi possivel validar o bloqueio da conversa no Redis nem no banco"
        ) from exc

    finally:
        if conn:
            conn.close()


def _cache_key(cliente_telefone, id_phone_unidade):
    cliente = _normalizar(cliente_telefone)
    unidade = _normalizar(id_phone_unidade)

    if not cliente or not unidade:
        return None

    raw = f"{unidade}:{cliente}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    return f"{REDIS_PREFIX}:{digest}"


def _normalizar(valor):
    if valor is None:
        return None

    texto = str(valor).strip()
    return texto or None


def _calcular_ttl(finalizou_em, bloqueio_dias):
    if bloqueio_dias <= 0:
        return 0

    if finalizou_em is None:
        return 0

    if isinstance(finalizou_em, str):
        finalizou_em = datetime.fromisoformat(finalizou_em)

    if finalizou_em.tzinfo is None:
        finalizou_em = finalizou_em.replace(tzinfo=timezone.utc)

    bloqueado_ate = finalizou_em + timedelta(days=bloqueio_dias)
    agora = datetime.now(timezone.utc)

    return int((bloqueado_ate - agora).total_seconds())
```

## 14. `core/integrations/whatsapp/messages/compartilhamento_contato.py` (criar)

```python
from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario

def primeiro_nome(nome_titular):
    partes = (nome_titular or "").split(maxsplit=1)
    return partes[0] if partes else ""

def mensagem_contato(nome_titular, *, repeticao=False, reconfirmacao=False,
                     abertura=False, agora=None):
    if repeticao:
        return "Para seguir com o atendimento, toque no botão abaixo e compartilhe seu número de WhatsApp."
    nome = primeiro_nome(nome_titular)
    inicio = f"{nome}, preciso" if nome else "Preciso"
    verbo = "reconfirmar" if reconfirmacao else "confirmar"
    texto = (f"{inicio} {verbo} seu número de WhatsApp para continuar o atendimento. "
             "Toque no botão abaixo para compartilhá-lo comigo.")
    if abertura:
        return f"{obter_saudacao_por_horario(agora)}! Sou o Theo, assistente do pós-venda.\n\n{texto}"
    return texto
```

## 15. `core/integrations/whatsapp/messages/etapa1_messages.py` (alterar)

```python
"""Mensagens da etapa 1 do pós-venda Baratão."""

from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario


MENSAGEM_PADRAO_ETAPA1 = (
    "{saudacao}, eu sou o Theo, assistente do pós-venda do Baratão e Atacadão! 😁\n\n"
    "Olha antes de começarmos peço que envie somente mensagens de texto!  "
    "Caso você não seja o titular da compra, recomendamos que direcione esse atendimento "
    "para o titular, caso foi você que fez a compra ignore este aviso.\n\n"
    "Antes de te encaminhar para um atendimento humano, preciso coletar algumas informações "
    "suas tá ? vai levar apenas alguns minutos, para começar, me informe o nome completo "
    "do titular da compra."
)
MENSAGEM_NOME_INVALIDO = (
    "Desculpa, não consegui entender, em uma única mensagem me informe "
    "apenas seu nome completo"
)


def montar_mensagem_etapa1(agora=None):
    return MENSAGEM_PADRAO_ETAPA1.format(saudacao=obter_saudacao_por_horario(agora))
```

## 16. `core/integrations/whatsapp/messages/etapa2_messages.py` (alterar)

```python
from core.integrations.whatsapp.messages.compartilhamento_contato import primeiro_nome


"""Pergunta e correção do CPF do titular na etapa 2."""

MENSAGEM_PADRAO_ETAPA2 = "Em uma única mensagem, me informe o CPF do titular da compra."

MENSAGEM_CPF_INVALIDO = (
    "Olha você esqueceu de digitar algum digito ou colocou um digito a mais "
    "no CPF, por favor em uma única mensagem informe seu CPF novamente"
)


def montar_mensagem_etapa2(nome_titular=None, *, contato_confirmado=False,
                          abertura=False, agora=None):
    nome = primeiro_nome(nome_titular)
    if contato_confirmado:
        inicio = f"Obrigado por compartilhar seu contato {nome}!" if nome else "Obrigado por compartilhar seu contato!"
    # A migração de 22/11/2026 podia colocar cadastros com nome e sem CPF
    # diretamente nesta etapa, antes da primeira resposta do Theo. A base
    # começou vazia. Hoje a saudação acontece na etapa 1, ao pedir o nome.
    # elif abertura:
    #     from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario
    #     saudacao = obter_saudacao_por_horario(agora)
    #     inicio = f"{saudacao}, {nome}!" if nome else f"{saudacao}!"
    #     inicio += " Sou o Theo, assistente do pós-venda."
    else:
        inicio = f"Certo {nome}." if nome else "Certo."
    return f"{inicio} {MENSAGEM_PADRAO_ETAPA2}"
```

## 17. `core/integrations/whatsapp/messages/etapa3_messages.py` (alterar)

```python
"""Pergunta de produto para a primeira compra informada ou uma nova conversa."""

MENSAGEM_PRODUTO = "Sobre qual tipo de produto você quer falar?"
MENSAGEM_PRODUTO_INVALIDO = "Não entendi, sobre qual tipo de produto você quer falar?"
RODAPE_PRODUTO = "Selecione apenas uma opção abaixo."
BOTOES_PRODUTO = (
    ("Apenas Estofados", "produto:estofados"),
    ("Apenas Móveis", "produto:moveis"),
    ("Estofados e Móveis", "produto:ambos"),
)


from core.integrations.whatsapp.messages.compartilhamento_contato import primeiro_nome
from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario


def montar_mensagem_etapa3(nome_titular=None):
    if nome_titular:
        return f"{obter_saudacao_por_horario()}, {primeiro_nome(nome_titular)}! {MENSAGEM_PRODUTO}"
    return MENSAGEM_PRODUTO
```

## 18. `core/integrations/whatsapp/pywa_functions/pywa_senders/compartilhamento_contato.py` (criar)

```python
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot
from core.integrations.whatsapp.exceptions import ErroEnvioMeta

def enviar_solicitacao(bsuid, phone_id, texto, etapa):
    try:
        resposta = conta_wa(phone_id).request_contact_info(to=bsuid, text=texto)
        wamid = extrair_id_hash_msg_bot(resposta)
    except Exception as exc:
        raise ErroEnvioMeta("Falha ao solicitar contato", id_etapa=etapa,
                            cliente_telefone=None, phone_id_unidade=phone_id) from exc
    return {"enviou": True, "resposta_ja_existia": False, "id_hash_msg_bot": wamid,
            "id_etapa_resultante": etapa, "tipo_mensagem": "interactive",
            "mensagem_bot": texto, "interativo": {"type": "request_contact_info",
                "body": {"text": texto}, "action": {"name": "request_contact_info"}},
            "canal": "meta_whatsapp", "atualizar_conversa": True, "atualizar_last_from_bot": True,
            "tipo_destinatario": "bsuid", "valor_destinatario": bsuid}
```

## 19. `core/integrations/whatsapp/pywa_functions/pywa_senders/encaminhamento_pos_venda.py` (alterar)

```python
"""Encaminhamento por rede das filiais das notas desta conversa."""

import os
import re
from urllib.parse import quote, urlsplit

from pywa.types import ImageCarouselCard, URLButton

from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO, EVENTO_SITUACAO_INFORMADA
from core.integrations.whatsapp.messages.encaminhamento_pos_venda import (
    MENSAGEM_DUAS_REDES, MENSAGEM_SEM_NOTA, MENSAGEM_NOTA_PERDIDA, MENSAGEM_POR_GRUPO,
    ROTULOS_POS_VENDA, mensagem_de_contato, montar_resumo_encaminhamento,
)
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.pywa_functions.resposta_envio import extrair_id_hash_msg_bot
from core.validacoes.encaminhamento_pos_venda import grupos_encaminhamento
from .texto_pos_venda import enviar_texto_pos_venda


def _resumo_do_atendimento(contexto):
    return montar_resumo_encaminhamento(
        contexto.get("cadastro") or {}, contexto.get("produto"), contexto.get("assunto"),
        pedidos_com_filial=contexto.get("pedidos_com_filial", ()), perdeu_nota=contexto.get("perdeu_nota"),
        detalhes=contexto.get("detalhes"),
    )


def _botao_contato(central, grupo, resumo):
    numero = central.get(f"telefone_{grupo}")
    if not re.fullmatch(r"[1-9][0-9]{7,14}", str(numero or "")):
        raise ValueError("Telefone de pós-venda inválido.")
    return URLButton(
        title=ROTULOS_POS_VENDA[grupo],
        url=f"https://wa.me/{numero}?text={quote(resumo, safe='')}",
    )


def montar_cartoes(contexto):
    central = contexto["central"]
    base = os.getenv("WHATSAPP_MIDIAS_BASE_URL", "").strip().rstrip("/")
    url = urlsplit(base)
    if url.scheme != "https" or not url.netloc or url.query or url.fragment or url.username:
        raise ValueError("Configure WHATSAPP_MIDIAS_BASE_URL com a URL HTTPS pública das imagens.")
    if central.get("telefone_atacadao") == central.get("telefone_baratao"):
        raise ValueError("A central precisa dos dois contatos distintos de pós-venda.")
    resumo = _resumo_do_atendimento(contexto)
    return [
        ImageCarouselCard(
            image=f"{base}/{arquivo}.png",
            buttons=_botao_contato(central, grupo, resumo),
        )
        for arquivo, grupo in (("estofados", "atacadao"), ("moveis", "baratao"))
    ]


def enviar_encaminhamento(contexto, evento):
    mensagem = contexto["mensagem_cliente_atual"]
    phone = mensagem["id_phone_unidade"]
    telefone = contexto.get("destinatario_envio", mensagem.get("cliente_telefone"))
    grupos = grupos_encaminhamento(contexto)
    conclusao = evento == EVENTO_SITUACAO_INFORMADA
    if len(grupos) == 1:
        grupo = grupos[0]
        texto = MENSAGEM_POR_GRUPO[grupo]
        envio = enviar_texto_pos_venda(
            telefone, phone, mensagem_de_contato(texto, contexto.get("assunto")),
            ETAPA_ENCAMINHAMENTO, botoes=_botao_contato(contexto["central"], grupo, _resumo_do_atendimento(contexto)),
        )
        if not conclusao:
            envio["tipo_tratamento"] = evento
        envio[f"encaminhado_{grupo}"] = contexto["central"][f"telefone_{grupo}"]
        return envio

    if contexto.get("perdeu_nota"):
        texto = MENSAGEM_NOTA_PERDIDA
    elif contexto.get("grupos_das_notas"):
        texto = MENSAGEM_DUAS_REDES
    else:
        texto = MENSAGEM_SEM_NOTA
    texto = mensagem_de_contato(texto, contexto.get("assunto"))
    cartoes = montar_cartoes(contexto)
    try:
        resposta = conta_wa(phone).send_carousel(to=telefone, body=texto, cards=cartoes)
        wamid = extrair_id_hash_msg_bot(resposta)
    except Exception as exc:
        raise ErroEnvioMeta(
            "Falha ao enviar contatos do pós-venda", id_etapa=ETAPA_ENCAMINHAMENTO,
            cliente_telefone=telefone, phone_id_unidade=phone,
        ) from exc
    envio = {
        "enviou": True, "resposta_ja_existia": False, "id_hash_msg_bot": wamid,
        "mensagem_bot": texto, "tipo_mensagem": "interactive",
        "interativo": {"type": "carousel", "body": {"text": texto},
                       "action": {"cards": [card.to_dict(i) for i, card in enumerate(cartoes)]}},
        "id_etapa_resultante": ETAPA_ENCAMINHAMENTO,
        "encaminhado_atacadao": contexto["central"]["telefone_atacadao"],
        "encaminhado_baratao": contexto["central"]["telefone_baratao"],
    }
    if not conclusao:
        envio["tipo_tratamento"] = evento
    return envio
```

## 20. `core/integrations/whatsapp/pywa_functions/pywa_senders/etapa2.py` (alterar)

```python
"""Envio da pergunta ou correção do CPF, sem decidir a próxima etapa."""

from core.etapas_pos_venda import ETAPA_CPF
from core.integrations.whatsapp.messages.etapa2_messages import (
    montar_mensagem_etapa2, MENSAGEM_CPF_INVALIDO,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa2(cliente_telefone, phone_id_unidade, *, nome_titular=None, abertura=False):
    return enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, montar_mensagem_etapa2(nome_titular, abertura=abertura), ETAPA_CPF,
    )


def enviar_cpf_invalido(cliente_telefone, phone_id_unidade):
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, MENSAGEM_CPF_INVALIDO, ETAPA_CPF,
    )
    return dict(envio, tratamento=True, tipo_tratamento="cpf_invalido")
```

## 21. `core/repositories/atendimento/entrada_fila.py` (alterar)

```python
"""Grava a entrada deduplicada para a central e o canal de origem."""
from psycopg.types.json import Jsonb


def entrada_ja_registrada(wamid, cursor):
    cursor.execute("SELECT 1 FROM chatbot.fila_mensagens WHERE id_hash_msg=%s", (wamid,))
    return cursor.fetchone() is not None


def inserir_entrada_fila(dados, cursor):
    cursor.execute("""
        INSERT INTO chatbot.fila_mensagens (id_central,id_cliente,cliente_telefone,
            user_id_origem,username_origem,id_hash_msg,received_data_hora,tipo_mensagem,
            conteudo_texto,interativo,status,retry_count,next_attempt_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id_hash_msg) DO NOTHING RETURNING id_mensagem
    """,(dados["id_central"],dados["id_cliente"],dados["cliente_telefone"],
         dados.get("user_id_origem"),dados.get("username_origem"),dados["id_hash_msg"],
         dados["received_data_hora"],dados["tipo_mensagem"],dados["conteudo_texto"],
         Jsonb(dados["interativo"]) if dados.get("interativo") else None,
         dados["status"],dados["retry_count"],dados["next_attempt_at"]))
    linha = cursor.fetchone()
    return linha[0] if linha else None
```

## 22. `core/repositories/atendimento/fallback_contato.py` (criar)

```python
def reservar_reconfirmacao(id_conversa, id_fila, wamid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.fallback_contato
            (id_conversa, id_mensagem_fila, wamid_original, estado)
        VALUES (%s,%s,%s,'reservado')
        ON CONFLICT DO NOTHING RETURNING id_conversa
    """, (id_conversa, id_fila, wamid))
    return cursor.fetchone() is not None


def concluir_reservas(conversa, cursor):
    cursor.execute("""
        UPDATE chatbot.fallback_contato SET estado='aceito', atualizado_em=now()
        WHERE id_conversa=%s AND estado='reservado'
    """,(conversa,))
```

## 23. `core/repositories/atendimento/fila.py` (alterar)

```python
import logging


logger = logging.getLogger("db.atendimento.fila")


def pegar_mensagens_da_fila(cursor):
    cursor.execute("SELECT * FROM chatbot.dequeue_message();")
    registro = cursor.fetchone()
    if registro:
        logger.debug(
            "fila_dequeue | acao=reservar id_mensagem=%s",
            registro[0],
        )
    return registro


def existe_mensagem_anterior_aberta_atendimento(
    cliente_telefone,
    id_phone_unidade,
    id_mensagem_atual,
    received_data_hora,
    cursor,
):
    cursor.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM chatbot.fila_mensagens f
            JOIN chatbot.central_pos_venda b USING (id_central)
            WHERE (f.id_cliente = (SELECT id_cliente FROM chatbot.fila_mensagens WHERE id_mensagem=%s)
                    OR (f.id_cliente IS NULL AND f.cliente_telefone=%s))
              AND b.phone_number_id = %s
              AND id_mensagem <> %s
              AND status IN ('pending', 'processing')
              AND (
                  received_data_hora < %s
                  OR (
                      received_data_hora = %s
                      AND id_mensagem < %s
                  )
              )
            LIMIT 1
        );
    """, (
        id_mensagem_atual,
        cliente_telefone,
        id_phone_unidade,
        id_mensagem_atual,
        received_data_hora,
        received_data_hora,
        id_mensagem_atual,
    ))

    resultado = bool(cursor.fetchone()[0])
    logger.debug(
        "fila_ordem_consultada | acao=verificar_anterior "
        "cliente=%s phone_number_id=%s id_mensagem=%s existe_anterior=%s",
        cliente_telefone,
        id_phone_unidade,
        id_mensagem_atual,
        resultado,
    )
    return resultado


def marcar_mensagem_como_enviada(id_mensagem, cursor):
    cursor.execute("""
        UPDATE chatbot.fila_mensagens
        SET status = 'sent',
            processing_started_at = NULL,
            last_error = NULL
        WHERE id_mensagem = %s
    """, (id_mensagem,))
    logger.debug(
        "fila_update | acao=marcar_sent id_mensagem=%s linhas=%s",
        id_mensagem,
        cursor.rowcount,
    )


def vincular_mensagem_fila_a_conversa(
    id_mensagem,
    id_conversa,
    cursor,
):
    cursor.execute("""
        UPDATE chatbot.fila_mensagens
        SET id_conversa = %s
        WHERE id_mensagem = %s
          AND status = 'processing'
          AND (
              id_conversa IS NULL
              OR id_conversa = %s
          );
    """, (id_conversa, id_mensagem, id_conversa))

    linhas = cursor.rowcount
    vinculo_reparado = False

    if linhas == 0:
        cursor.execute("""
            UPDATE chatbot.fila_mensagens AS fila
            SET id_conversa = %s
            WHERE fila.id_mensagem = %s
              AND fila.status = 'processing'
              AND fila.id_conversa IS DISTINCT FROM %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM chatbot.historico_mensagens AS historico
                  WHERE historico.id_mensagem_fila = fila.id_mensagem
              );
        """, (id_conversa, id_mensagem, id_conversa))
        linhas = cursor.rowcount
        vinculo_reparado = linhas == 1

        if vinculo_reparado:
            logger.warning(
                "fila_vinculo_reparado | "
                "motivo=vinculo_legado_sem_historico "
                "id_mensagem=%s id_conversa=%s",
                id_mensagem,
                id_conversa,
            )

    logger.debug(
        "fila_update | acao=vincular_conversa id_mensagem=%s "
        "id_conversa=%s linhas=%s vinculo_reparado=%s",
        id_mensagem,
        id_conversa,
        linhas,
        vinculo_reparado,
    )
    return linhas


def reagendar_mensagem_sem_erro(
    id_mensagem,
    cursor,
    delay_seconds=30,
    *,
    retry_esperado=None,
):
    # A suspensão pode ser detectada após HTTP. Não devolver à fila uma
    # mensagem já confirmada ou reservada por outro ciclo nesse intervalo.
    filtro_posse = ""
    parametros = (delay_seconds, id_mensagem)
    if retry_esperado is not None:
        filtro_posse = " AND status = 'processing' AND retry_count = %s"
        parametros += (retry_esperado,)
    cursor.execute("""
        UPDATE chatbot.fila_mensagens
        SET
            status = 'pending',
            next_attempt_at = NOW() + (%s * INTERVAL '1 second'),
            processing_started_at = NULL,
            retry_count = GREATEST(COALESCE(retry_count, 0) - 1, 0),
            last_error = NULL
        WHERE id_mensagem = %s
    """ + filtro_posse, parametros)
    logger.debug(
        "fila_update | acao=reagendar_sem_erro id_mensagem=%s delay=%s linhas=%s",
        id_mensagem,
        delay_seconds,
        cursor.rowcount,
    )
    return cursor.rowcount


def reagendar_mensagem(id_mensagem, erro, max_retry, cursor):
    cursor.execute("""
        UPDATE chatbot.fila_mensagens
        SET
            status = 'pending',
            next_attempt_at = NOW() + INTERVAL '2 minutes',
            processing_started_at = NULL,
            last_error = %s
        WHERE id_mensagem = %s AND retry_count < %s;
    """, (str(erro), id_mensagem, max_retry))
    logger.debug(
        "fila_update | acao=reagendar_com_erro id_mensagem=%s max_retry=%s linhas=%s",
        id_mensagem,
        max_retry,
        cursor.rowcount,
    )
    return cursor.rowcount


def deletar_mensagem_por_id(id_mensagem, cursor):
    """Remove uma linha da fila pelo id."""
    cursor.execute("""
        DELETE FROM chatbot.fila_mensagens
        WHERE id_mensagem = %s;
    """, (id_mensagem,))
    logger.debug(
        "fila_delete | acao=delete_por_id id_mensagem=%s linhas=%s",
        id_mensagem,
        cursor.rowcount,
    )
    return cursor.rowcount


def deletar_mensagem_se_max_retry(id_mensagem, max_retry, cursor):
    cursor.execute("""
        DELETE FROM chatbot.fila_mensagens
        WHERE id_mensagem = %s AND retry_count >= %s;
    """, (id_mensagem, max_retry))
    logger.debug(
        "fila_delete | acao=delete_max_retry id_mensagem=%s max_retry=%s linhas=%s",
        id_mensagem,
        max_retry,
        cursor.rowcount,
    )
    return cursor.rowcount


def ler_identidade_fila(id_fila, cursor):
    cursor.execute("""
        SELECT id_cliente, user_id_origem, interativo, id_central
        FROM chatbot.fila_mensagens WHERE id_mensagem=%s
    """, (id_fila,))
    return cursor.fetchone()
```

## 24. `core/repositories/atendimento/historico.py` (alterar)

```python
"""Histórico vinculado à conversa, fila e WAMID de origem."""
from psycopg.types.json import Jsonb


def buscar_resposta_bot_por_mensagem_cliente(id_conversa, id_mensagem_fila, id_hash_cliente_origem, cursor):
    cursor.execute("""
        SELECT id_mensagem, id_etapa, received_data_hora, id_hash_msg, conteudo_texto, tipo_mensagem, interativo
        FROM chatbot.historico_mensagens
        WHERE id_conversa = %s AND id_mensagem_fila = %s AND id_hash_cliente_origem = %s
          AND quem_enviou = 'bot' AND status_envio = 'sent' AND parte_resposta = 1;
    """, (id_conversa, id_mensagem_fila, id_hash_cliente_origem))
    row = cursor.fetchone()
    return dict(zip(("id_mensagem", "id_etapa", "received_data_hora", "id_hash_msg",
                     "conteudo_texto", "tipo_mensagem", "interativo"), row)) if row else None


def inserir_historico_mensagem_cliente(mensagem, id_conversa, id_etapa, cursor):
    cursor.execute("""
        INSERT INTO chatbot.historico_mensagens
            (id_conversa, id_etapa, received_data_hora, quem_enviou, id_hash_msg,
             id_mensagem_fila, tipo_mensagem, conteudo_texto, interativo)
        SELECT %s, %s, %s, 'cliente', %s, f.id_mensagem, f.tipo_mensagem, f.conteudo_texto, CASE WHEN f.tipo_mensagem='contacts' THEN NULL ELSE f.interativo END
        FROM chatbot.fila_mensagens f WHERE f.id_mensagem = %s AND f.id_conversa = %s
        ON CONFLICT (id_hash_msg) DO NOTHING
        RETURNING id_mensagem, received_data_hora, id_etapa;
    """, (id_conversa, id_etapa, mensagem["data_recebimento"], mensagem["id_hash"],
          mensagem["id_mensagem"], id_conversa))
    row = cursor.fetchone()
    if row:
        return (*row, True)
    cursor.execute("""
        SELECT id_mensagem, received_data_hora, id_etapa FROM chatbot.historico_mensagens
        WHERE id_conversa = %s AND id_mensagem_fila = %s AND id_hash_msg = %s AND quem_enviou = 'cliente';
    """, (id_conversa, mensagem["id_mensagem"], mensagem["id_hash"]))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Histórico da entrada ausente ou pertencente a outra conversa/fila.")
    return (*row, False)


def inserir_historico_mensagem_bot(contexto, envio, cursor):
    entrada = contexto["mensagem_cliente_atual"]
    existente = buscar_resposta_bot_por_mensagem_cliente(
        contexto["id_conversa"], entrada["id_mensagem_fila"], entrada["id_hash_msg"], cursor)
    if existente:
        return existente["id_mensagem"], existente["received_data_hora"], False
    if not envio.get("id_hash_msg_bot"):
        raise ValueError("Meta não retornou o WAMID da resposta.")
    primeira = _inserir_parte_resposta(contexto["id_conversa"], entrada, envio, 1, cursor)
    if envio.get("segunda_resposta"):
        segunda = {**envio, **envio["segunda_resposta"]}
        _inserir_parte_resposta(contexto["id_conversa"], entrada, segunda, 2, cursor)
    return (*primeira, True)


def _inserir_parte_resposta(id_conversa, entrada, envio, parte, cursor):
    interativo = dict(envio.get("interativo") or {})
    # Metadado interno de recuperação; não é enviado como parte do payload Meta.
    interativo["_fluxo"] = {"evento": envio.get("evento_transicao")}
    cursor.execute("""
        INSERT INTO chatbot.historico_mensagens
            (id_conversa, id_etapa, received_data_hora, quem_enviou, id_hash_msg,
             id_mensagem_fila, id_hash_cliente_origem, tipo_mensagem, conteudo_texto, interativo, status_envio, tipo_destinatario, valor_destinatario, parte_resposta)
        VALUES (%s, %s, clock_timestamp(), 'bot', %s, %s, %s, %s, %s, %s, 'sent', %s, %s, %s)
        RETURNING id_mensagem, received_data_hora;
    """, (id_conversa, envio["id_etapa_resultante"], envio["id_hash_msg_bot"],
          entrada["id_mensagem_fila"], entrada["id_hash_msg"], envio["tipo_mensagem"],
          envio["mensagem_bot"], Jsonb(interativo), envio.get("tipo_destinatario"), envio.get("valor_destinatario"), parte))
    return cursor.fetchone()
```

## 25. `core/repositories/atendimento/solicitacao_contato.py` (criar)

```python
def abrir_solicitacao(id_conversa, motivo, etapa, bsuid, wamid, cursor):
    cursor.execute("""
        INSERT INTO chatbot.solicitacao_contato
            (id_conversa, motivo, id_etapa_retomada, bsuid_destino, wamid_solicitacao, wamids_aceitos)
        VALUES (%s,%s,%s,%s,%s,ARRAY[%s]::text[])
    """, (id_conversa, motivo, etapa, bsuid, wamid, wamid))

def ler_solicitacao_para_confirmar(id_conversa, bsuid, cursor):
    cursor.execute("""
        SELECT id_etapa_retomada, motivo, wamid_solicitacao FROM chatbot.solicitacao_contato
        WHERE id_conversa=%s AND bsuid_destino=%s FOR UPDATE
    """, (id_conversa, bsuid))
    return cursor.fetchone()

def encerrar_solicitacao(id_conversa, cursor):
    cursor.execute("DELETE FROM chatbot.solicitacao_contato WHERE id_conversa=%s", (id_conversa,))


def repetir_solicitacao(conversa, uid, wamid, cursor):
    cursor.execute("""
        UPDATE chatbot.solicitacao_contato SET erros_cliente=least(3,erros_cliente+1),
            wamids_aceitos=array_append(wamids_aceitos,%s)
        WHERE id_conversa=%s AND bsuid_destino=%s AND NOT (%s=ANY(wamids_aceitos))
    """, (wamid,conversa,uid,wamid))


def pendencia_ativa(central,cliente,uid,cursor):
    cursor.execute("""
        SELECT s.wamids_aceitos, s.motivo FROM chatbot.solicitacao_contato s
        JOIN chatbot.conversa c USING(id_conversa) JOIN chatbot.chat ch USING(id_chat)
        WHERE c.status_ativa AND c.id_central=%s AND ch.id_cliente=%s AND s.bsuid_destino=%s
        FOR UPDATE OF s
    """,(central,cliente,uid))
    return cursor.fetchone()
```

## 26. `core/repositories/fluxo/contextos/pos_venda.py` (alterar)

```python
"""Cadastro, contatos e apresentação pendente derivados do histórico confirmado."""

from core.etapas_pos_venda import ETAPA_DETALHES, ETAPA_PEDIDOS, ETAPA_PRODUTO


def buscar_contexto_pos_venda(id_conversa, cursor):
    cursor.execute("""
        SELECT b.telefone_atacadao, b.telefone_baratao, a.nome_titular,
               a.cpf_titular, a.cidade_loja_compra,
               (ultima.id_mensagem IS NULL OR
                (c.id_etapa_atual = %s AND
                 ultima.interativo->>'_migracao_produto_pendente' = 'true') OR
                (c.id_etapa_atual = %s AND ultima.interativo->>'_reapresentar_detalhes' = 'true')),
               a.produto, a.assunto::text,
               CASE WHEN c.id_etapa_atual = %s THEN ARRAY(SELECT codigo FROM chatbot.filial_compra) END,
               b.phone_number_id, b.waba_id AS messaging_account_id, b.waac_id,
               ARRAY(SELECT ARRAY[p.numero, f.nome, f.grupo] FROM chatbot.pedido_conversa p
                     LEFT JOIN chatbot.filial_compra f ON f.codigo = p.codigo_filial
                     WHERE p.id_conversa = c.id_conversa ORDER BY p.numero),
               a.perdeu_nota, a.detalhes, a.telefone_compartilhado
        FROM chatbot.conversa c
        JOIN chatbot.central_pos_venda b ON b.id_central = c.id_central
        JOIN chatbot.atendimento_pos_venda a ON a.id_conversa = c.id_conversa
        LEFT JOIN LATERAL (
            SELECT h.id_mensagem, h.interativo
            FROM chatbot.historico_mensagens h
            WHERE h.id_conversa = c.id_conversa
              AND h.quem_enviou = 'bot' AND h.status_envio = 'sent'
            ORDER BY h.received_data_hora DESC, h.id_mensagem DESC LIMIT 1
        ) ultima ON true
        WHERE c.id_conversa = %s;
    """, (ETAPA_PRODUTO, ETAPA_DETALHES, ETAPA_PEDIDOS, id_conversa))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Cadastro/central ausente para a conversa.")
    telefone, uid, motivo, etapa, wamids, erros, suspenso = ler_rota_contato(id_conversa,cursor)
    return {
        "wa_id_confirmado": None if suspenso or row[15] else telefone, "bsuid_vigente": uid,
        "reconfirmar_telefone": bool(suspenso),
        "solicitacao_contato": {"motivo": motivo, "etapa": etapa, "wamids": wamids, "erros": erros}
                              if motivo else None,
        "central": {
            "telefone_atacadao": row[0], "telefone_baratao": row[1],
            "phone_number_id": row[9], "messaging_account_id": row[10], "waac_id": row[11],
        },
        "cadastro": dict(zip(
            ("nome_titular", "cpf_titular", "cidade_loja_compra"), row[2:5],
        )),
        "apresentacao_pendente": bool(row[5]),
        "produto": row[6],
        "assunto": row[7],
        "pedidos_com_filial": [(numero, filial) for numero, filial, _ in row[12]],
        "grupos_das_notas": frozenset(grupo for _, _, grupo in row[12]),
        "telefone_compartilhado": row[15],
        "perdeu_nota": row[13],
        "detalhes": row[14],
        "codigos_filiais": frozenset(row[8] or ()),
    }


def ler_rota_contato(id_conversa, cursor):
    cursor.execute("""
        SELECT cl.waid_telefone, a.user_id, s.motivo, s.id_etapa_retomada,
               s.wamids_aceitos, s.erros_cliente, a.suspender_telefone
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat=c.id_chat
        JOIN chatbot.cliente cl ON cl.id_cliente=ch.id_cliente
        LEFT JOIN chatbot.identidade_bsuid a
          ON a.id_cliente=cl.id_cliente AND a.id_central=c.id_central AND a.vigente
        LEFT JOIN chatbot.solicitacao_contato s ON s.id_conversa=c.id_conversa
        WHERE c.id_conversa=%s
    """, (id_conversa,))
    return cursor.fetchone()
```

## 27. `core/repositories/fluxo/politicas.py` (alterar)

```python
"""Políticas de encerramento e bloqueio temporário por cliente/central."""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PoliticaEtapa:
    id_etapa: int
    encerra_automaticamente: bool
    bloqueio_dias: int


@dataclass(frozen=True)
class BloqueioConversa:
    finalizou_em: datetime
    bloqueio_dias: int


def buscar_politica_etapa(id_etapa, cursor):
    cursor.execute("""
        SELECT id_etapa, encerra_automaticamente, bloqueio_dias
        FROM chatbot.etapa WHERE id_etapa = %s;
    """, (id_etapa,))
    row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Política da etapa {id_etapa} não encontrada")
    return PoliticaEtapa(*row)


def buscar_bloqueio_conversa_por_id(id_conversa, cursor):
    cursor.execute("""
        SELECT c.finalizou_em, e.bloqueio_dias
        FROM chatbot.conversa c JOIN chatbot.etapa e ON e.id_etapa = c.id_etapa_atual
        WHERE c.id_conversa = %s AND NOT c.status_ativa
          AND c.finalizou_em IS NOT NULL AND e.bloqueio_dias > 0 AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente';
    """, (id_conversa,))
    return _montar_bloqueio(cursor.fetchone())


def buscar_bloqueio_ativo_por_cliente_unidade(cliente_telefone, id_phone_unidade, cursor):
    # Nome da função preservado para os pontos de entrada do webhook/cache.
    cursor.execute("""
        SELECT c.finalizou_em, e.bloqueio_dias
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat = c.id_chat
        JOIN chatbot.cliente cl ON cl.id_cliente = ch.id_cliente
        JOIN chatbot.central_pos_venda b ON b.id_central = c.id_central
        JOIN chatbot.etapa e ON e.id_etapa = c.id_etapa_atual
        WHERE (cl.waid_telefone = %s OR EXISTS (
              SELECT FROM chatbot.identidade_bsuid a WHERE a.id_central=b.id_central
                AND a.id_cliente=cl.id_cliente AND a.user_id=%s
          )) AND b.phone_number_id = %s
          AND NOT c.status_ativa AND e.bloqueio_dias > 0 AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente'
          AND c.finalizou_em > CURRENT_TIMESTAMP - e.bloqueio_dias * INTERVAL '1 day'
        ORDER BY c.finalizou_em DESC LIMIT 1;
    """, (cliente_telefone, cliente_telefone, id_phone_unidade))
    return _montar_bloqueio(cursor.fetchone())


def _montar_bloqueio(row):
    return BloqueioConversa(*row) if row else None
```

## 28. `core/repositories/monitoramento/painel.py` (alterar)

```python
"""Consultas somente leitura do painel, sempre limitadas à unidade autorizada."""

import json


def _objeto_json(valor):
    """Normaliza JSONB do cursor Django (texto) ou psycopg (dict).

    Contexto ausente ou fora do contrato permanece desconhecido no painel.
    A conversão é local à leitura; não altera o JSON persistido no banco.
    """
    if isinstance(valor, str):
        try:
            valor = json.loads(valor)
        except json.JSONDecodeError:
            return None
    return valor if isinstance(valor, dict) else None


def _linhas(cursor):
    colunas = [item[0] for item in cursor.description]
    linhas = [dict(zip(colunas, linha)) for linha in cursor.fetchall()]
    for linha in linhas:
        for campo in ('contexto_fireads', 'dados_consulta'):
            if campo in linha:
                linha[campo] = _objeto_json(linha[campo])
    return linhas


def _linha(cursor):
    colunas = [item[0] for item in cursor.description]
    valor = cursor.fetchone()
    return dict(zip(colunas, valor)) if valor else None


def _periodo(coluna, inicio, fim, parametros):
    trecho = f' AND {coluna} < %s'
    if inicio is not None:
        trecho = f' AND {coluna} >= %s' + trecho
        parametros.extend((inicio, fim))
    else:
        parametros.append(fim)
    return trecho


def buscar_unidade(id_unidade, cursor):
    cursor.execute("""
        SELECT u.id_unidade, u.nome_unidade, ac.nome_agente, ac.idade_minima_suporte,
               ac.email_obrigatorio, ac.bpa_ativo,
               EXISTS (SELECT 1 FROM chatbot.integracao_fireads i
                       WHERE i.id_unidade=u.id_unidade AND i.integracao_ativa AND i.contrato_validado) AS fireads_habilitada,
               MIN(CASE WHEN h.quem_enviou = 'cliente' THEN h.received_data_hora END) AS inicio_historico
          FROM chatbot.unidade u
          JOIN chatbot.atendimento_customizado ac ON ac.id_unidade = u.id_unidade
          LEFT JOIN chatbot.conversa c ON c.id_unidade = u.id_unidade
          LEFT JOIN chatbot.historico_mensagens h ON h.id_conversa = c.id_conversa
         WHERE u.id_unidade = %s
         GROUP BY u.id_unidade, u.nome_unidade, ac.nome_agente,
                  ac.idade_minima_suporte, ac.email_obrigatorio, ac.bpa_ativo
    """, (id_unidade,))
    return _linha(cursor)


def listar_conversas(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    periodo = _periodo("h.received_data_hora", inicio, fim, parametros)
    cursor.execute(f"""
        WITH atividade AS (
            SELECT DISTINCT ON (c.id_conversa)
                ch.id_cliente,c.id_conversa,c.iniciou_em,c.id_etapa_atual,
                h.received_data_hora AS ultima_atividade,h.conteudo_texto AS ultima_mensagem,
                h.id_mensagem AS ultima_mensagem_id
            FROM chatbot.conversa c JOIN chatbot.chat ch USING(id_chat)
            JOIN chatbot.historico_mensagens h USING(id_conversa)
            WHERE c.id_central=%s {periodo} AND (h.quem_enviou='cliente' OR h.status_envio='sent')
            ORDER BY c.id_conversa,h.received_data_hora DESC,h.id_mensagem DESC
        )
        SELECT a.*, atendimento.nome_titular AS nome_cliente,cl.waid_telefone,cl.username
        FROM atividade a JOIN chatbot.cliente cl USING(id_cliente)
        LEFT JOIN chatbot.atendimento_pos_venda atendimento USING(id_conversa)
        ORDER BY a.ultima_atividade DESC, a.id_conversa DESC
    """, tuple(parametros))
    return _linhas(cursor)


def buscar_mensagens(id_unidade, id_cliente, inicio, fim, cursor):
    parametros = [id_unidade, id_cliente]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    cursor.execute(f"""
        SELECT h.id_mensagem, h.id_conversa, h.id_etapa,
               h.received_data_hora AS data, h.quem_enviou,
               h.tipo_mensagem AS tipo, h.conteudo_texto AS texto, h.interativo
          FROM chatbot.historico_mensagens h
          JOIN chatbot.conversa c ON c.id_conversa = h.id_conversa
         JOIN chatbot.chat ch ON ch.id_chat=c.id_chat
         WHERE c.id_central = %s AND ch.id_cliente = %s {filtro}
           AND (h.quem_enviou = 'cliente' OR (h.quem_enviou = 'bot' AND h.status_envio = 'sent'))
         ORDER BY h.received_data_hora, h.id_mensagem
    """, tuple(parametros))
    return _linhas(cursor)


def buscar_metricas(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    p_msg = []
    f_msg = _periodo('h.received_data_hora', inicio, fim, p_msg)
    p_funil = []
    f_funil = _periodo('f.enviado_em', inicio, fim, p_funil)
    p_nota = []
    f_nota = _periodo('p.criado_em', inicio, fim, p_nota)
    cursor.execute(f"""
        WITH contatos AS (
          SELECT DISTINCT c.id_cliente
            FROM chatbot.conversa c JOIN chatbot.historico_mensagens h ON h.id_conversa=c.id_conversa
           WHERE c.id_unidade=%s AND h.quem_enviou='cliente' {filtro}
        )
        SELECT (SELECT COUNT(*) FROM contatos) AS leads,
               (SELECT COUNT(*) FROM chatbot.historico_mensagens h
                 JOIN chatbot.conversa c ON c.id_conversa=h.id_conversa
                WHERE c.id_unidade=%s AND c.id_cliente IN (SELECT id_cliente FROM contatos)
                  {f_msg} AND (h.quem_enviou='cliente' OR (h.quem_enviou='bot' AND h.status_envio='sent'))) AS mensagens,
               (SELECT COUNT(DISTINCT c.id_cliente) FROM chatbot.funil_envios f
                 JOIN chatbot.conversa c ON c.id_conversa=f.id_conversa
                WHERE c.id_unidade=%s AND c.id_cliente IN (SELECT id_cliente FROM contatos)
                  AND f.status='sent' {f_funil}) AS funil,
               (SELECT COUNT(DISTINCT c.id_cliente) FROM chatbot.pesquisa_satisfacao p
                 JOIN chatbot.conversa c ON c.id_conversa=p.id_conversa
                WHERE c.id_unidade=%s AND c.id_cliente IN (SELECT id_cliente FROM contatos)
                  AND p.nota IS NOT NULL {f_nota}) AS avaliacoes,
               (SELECT ROUND(AVG(p.nota)::numeric,2) FROM chatbot.pesquisa_satisfacao p
                 JOIN chatbot.conversa c ON c.id_conversa=p.id_conversa
                WHERE c.id_unidade=%s AND c.id_cliente IN (SELECT id_cliente FROM contatos)
                  AND p.nota IS NOT NULL {f_nota}) AS nota_media
    """, tuple(parametros + [id_unidade] + p_msg + [id_unidade] + p_funil + [id_unidade] + p_nota + [id_unidade] + p_nota))
    return _linha(cursor)


def contar_encaminhados_comercial_por_idade(id_unidade, inicio, fim, cursor):
    """Conta o fato concluído, pela data de encerramento, sem inferir pela idade."""
    parametros = [id_unidade]
    filtro = _periodo('c.finalizou_em', inicio, fim, parametros)
    cursor.execute(f"""
        SELECT COUNT(DISTINCT c.id_cliente)
          FROM chatbot.conversa c
         WHERE c.id_unidade = %s
           AND c.status_ativa = FALSE
           AND c.motivo_encerramento = 'encaminhado_suporte_idoso'
           AND c.finalizou_em IS NOT NULL {filtro}
    """, tuple(parametros))
    return int(cursor.fetchone()[0])


def buscar_perfis(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    parametros_funil = []
    filtro_funil = _periodo('f.enviado_em', inicio, fim, parametros_funil)
    cursor.execute(f"""
        SELECT DISTINCT c.id_cliente, c.id_conversa, c.status_dependente,
               cl.idade AS idade_titular, d.idade AS idade_dependente,
               d.id_dependente, d.nome_dependente,
               EXISTS (SELECT 1 FROM chatbot.funil_envios f
                        WHERE f.id_conversa=c.id_conversa AND f.status='sent'
                        {filtro_funil}) AS foi_funil
          FROM chatbot.conversa c JOIN chatbot.cliente cl ON cl.id_cliente=c.id_cliente
          LEFT JOIN chatbot.dependente d ON d.id_conversa=c.id_conversa
         WHERE c.id_unidade=%s AND EXISTS (
               SELECT 1 FROM chatbot.historico_mensagens h
                WHERE h.id_conversa=c.id_conversa AND h.quem_enviou='cliente' {filtro})
    """, tuple(parametros_funil + parametros))
    return _linhas(cursor)


def buscar_satisfacao(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    filtro = _periodo('p.criado_em', inicio, fim, parametros)
    cursor.execute(f"""
        SELECT p.nota, COUNT(*) AS quantidade
          FROM chatbot.pesquisa_satisfacao p
          JOIN chatbot.conversa c ON c.id_conversa=p.id_conversa
         WHERE c.id_unidade=%s AND p.nota IS NOT NULL {filtro}
         GROUP BY p.nota ORDER BY p.nota
    """, tuple(parametros))
    return _linhas(cursor)


def buscar_etapas(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    cursor.execute(f"""
        WITH conversas_periodo AS (
            SELECT c.id_conversa, c.id_etapa_atual FROM chatbot.conversa c
             WHERE c.id_unidade=%s AND EXISTS (
                 SELECT 1 FROM chatbot.historico_mensagens h WHERE h.id_conversa=c.id_conversa
                   AND h.quem_enviou='cliente' {filtro})
        )
        SELECT e.id_etapa, e.nome_etapa, COUNT(c.id_conversa) AS quantidade
          FROM chatbot.etapa e LEFT JOIN conversas_periodo c ON c.id_etapa_atual=e.id_etapa
         WHERE e.id_etapa BETWEEN 1 AND 24
         GROUP BY e.id_etapa,e.nome_etapa ORDER BY e.id_etapa
    """, tuple(parametros))
    return _linhas(cursor)


def buscar_origens(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    p_funil = []
    f_funil = _periodo('f.enviado_em', inicio, fim, p_funil)
    cursor.execute(f"""
        SELECT c.id_conversa,c.id_cliente,c.contexto_fireads,
               CASE WHEN c.status_dependente IS TRUE OR c.id_etapa_atual >= 4
                    OR c.contexto_coleta #>> '{{campos,destinatario,status}}' = 'aceito'
                    THEN c.status_dependente ELSE NULL END AS status_dependente,
               cl.idade AS idade_titular, d.idade AS idade_dependente,
               CASE WHEN c.contexto_fireads ? 'atribuicao_monitoramento' THEN NULL ELSE q.dados END AS dados_consulta,
               EXISTS (SELECT 1 FROM chatbot.funil_envios f WHERE f.id_conversa=c.id_conversa
                       AND f.status='sent' {f_funil}) AS foi_funil
          FROM chatbot.conversa c LEFT JOIN chatbot.consulta_fireads q ON q.id_conversa=c.id_conversa
          JOIN chatbot.cliente cl ON cl.id_cliente=c.id_cliente
          LEFT JOIN LATERAL (
              SELECT dp.idade FROM chatbot.dependente dp WHERE dp.id_conversa=c.id_conversa
              ORDER BY dp.id_dependente LIMIT 1
          ) d ON TRUE
         WHERE c.id_unidade=%s AND EXISTS (
             SELECT 1 FROM chatbot.historico_mensagens h WHERE h.id_conversa=c.id_conversa
               AND h.quem_enviou='cliente' {filtro})
    """, tuple(p_funil + parametros))
    return _linhas(cursor)


def buscar_atividade(id_unidade, inicio, fim, cursor, granularidade):
    unidade_tempo = {'dia': 'day', 'semana': 'week', 'mes': 'month'}[granularidade]
    parametros = [id_unidade]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    cursor.execute(f"""
        SELECT DATE_TRUNC('{unidade_tempo}', h.received_data_hora AT TIME ZONE 'America/Sao_Paulo') AS periodo,
               COUNT(*) FILTER (WHERE h.quem_enviou='cliente' OR (h.quem_enviou='bot' AND h.status_envio='sent')) AS mensagens,
               COUNT(DISTINCT c.id_cliente) FILTER (WHERE h.quem_enviou='cliente') AS leads
          FROM chatbot.historico_mensagens h JOIN chatbot.conversa c ON c.id_conversa=h.id_conversa
         WHERE c.id_unidade=%s {filtro}
         GROUP BY 1 ORDER BY 1
    """, tuple(parametros))
    return _linhas(cursor)


def listar_contatos(id_unidade, inicio, fim, cursor):
    parametros = [id_unidade]
    filtro = _periodo('h.received_data_hora', inicio, fim, parametros)
    cursor.execute(f"""
        SELECT cl.id_cliente, cl.nome, cl.email, cl.waid_telefone
          FROM chatbot.cliente cl
         WHERE EXISTS (
             SELECT 1 FROM chatbot.conversa c
             JOIN chatbot.historico_mensagens h ON h.id_conversa=c.id_conversa
              WHERE c.id_cliente=cl.id_cliente AND c.id_unidade=%s
                AND h.quem_enviou='cliente' {filtro})
         ORDER BY cl.nome NULLS LAST, cl.id_cliente
    """, tuple(parametros))
    return _linhas(cursor)
```

## 29. `core/repositories/seguranca/bloqueio_meta.py` (alterar)

```python
import logging

from core.logging_config import short_value


logger = logging.getLogger("db.bloqueio_meta")


def registrar_evento_flood_banco(
    wa_id_cliente,
    phone_id_unidade,
    id_hash_msg,
    cursor,
):
    cursor.execute("""
        INSERT INTO chatbot.webhook_flood_evento (
            wa_id_cliente,
            id_central,
            id_hash_msg
        )
        SELECT %s, id_central, %s
        FROM chatbot.central_pos_venda
        WHERE phone_number_id = %s
        ON CONFLICT (id_hash_msg) DO NOTHING;
    """, (wa_id_cliente, id_hash_msg, phone_id_unidade))
    logger.debug(
        "flood_evento_insert | acao=registrar wa_id_cliente=%s phone_id_unidade=%s id_hash_msg=%s linhas=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        short_value(id_hash_msg),
        cursor.rowcount,
    )


def contar_eventos_flood_banco(
    wa_id_cliente,
    phone_id_unidade,
    cursor,
    janela_segundos=60,
):
    cursor.execute("""
        SELECT COUNT(*)
        FROM chatbot.webhook_flood_evento
        JOIN chatbot.central_pos_venda b USING (id_central)
        WHERE wa_id_cliente = %s
          AND b.phone_number_id = %s
          AND received_at >= NOW() - (%s * INTERVAL '1 second');
    """, (wa_id_cliente, phone_id_unidade, janela_segundos))

    resultado = cursor.fetchone()
    total = int(resultado[0]) if resultado else 0
    logger.debug(
        "flood_evento_count | acao=contar wa_id_cliente=%s phone_id_unidade=%s janela=%s total=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        janela_segundos,
        total,
    )
    return total


def limpar_eventos_flood_antigos(cursor, horas=2):
    cursor.execute("""
        DELETE FROM chatbot.webhook_flood_evento
        WHERE received_at < NOW() - (%s * INTERVAL '1 hour');
    """, (horas,))

    logger.debug(
        "flood_evento_limpeza | acao=limpar_antigos horas=%s linhas=%s",
        horas,
        cursor.rowcount,
    )
    return cursor.rowcount


def buscar_central_para_bloqueio(phone_number_id, cursor):
    """Fixa o vínculo com o número até o commit da intenção de bloqueio."""
    cursor.execute("""
        SELECT id_central, phone_number_id, waba_id, waac_id
        FROM chatbot.central_pos_venda
        WHERE phone_number_id = %s
        FOR SHARE;
    """, (phone_number_id,))
    return _central_do_registro(cursor.fetchone())


def consultar_protecao_remetente(identificadores, phone_number_id, conta_origem, cursor):
    """Relaciona o remetente às rotas conhecidas dentro da central antes do flood."""
    cursor.execute("""
        WITH central AS (
            SELECT id_central, phone_number_id, waba_id, waac_id
            FROM chatbot.central_pos_venda WHERE phone_number_id=%s AND waba_id=%s
        ), clientes AS (
            SELECT id_cliente FROM chatbot.cliente WHERE waid_telefone=ANY(%s)
            UNION
            SELECT a.id_cliente FROM chatbot.identidade_bsuid a JOIN central USING(id_central)
            WHERE a.user_id=ANY(%s)
        ), rotas AS (
            SELECT unnest(%s::text[]) AS chave
            UNION SELECT waid_telefone FROM chatbot.cliente JOIN clientes USING(id_cliente)
            UNION SELECT user_id FROM chatbot.identidade_bsuid JOIN central USING(id_central)
                  JOIN clientes USING(id_cliente)
        )
        SELECT b.*, EXISTS (
            SELECT FROM chatbot.cliente_bloqueado_meta m WHERE m.id_central=b.id_central
            AND m.wa_id_cliente IN (SELECT chave FROM rotas)
        ), (
            SELECT coalesce(f.cliente_telefone, f.user_id_origem)
            FROM chatbot.fila_mensagens f JOIN clientes USING(id_cliente)
            WHERE f.id_central=b.id_central ORDER BY f.id_mensagem LIMIT 1
        )
        FROM central b
    """, (phone_number_id, conta_origem, identificadores, identificadores, identificadores))
    row = cursor.fetchone()
    if not row:
        return None
    return _central_do_registro(row) if row[4] else None, row[5]


def _central_do_registro(row):
    if row is None:
        return None
    return {
        "id_central": row[0], "phone_number_id": row[1],
        "messaging_account_id": row[2], "waac_id": row[3],
    }


def registrar_cliente_bloqueado_meta_banco(wa_id_cliente, id_central, cursor):
    cursor.execute("""
        INSERT INTO chatbot.cliente_bloqueado_meta (id_central, wa_id_cliente)
        VALUES (%s, %s)
        ON CONFLICT (id_central, wa_id_cliente) DO NOTHING;
    """, (id_central, wa_id_cliente))
```

## 30. `core/repositories/seguranca/turno_cliente.py` (alterar)

```python
import logging

from core.logging_config import short_value


logger = logging.getLogger("db.turno_cliente")


def avaliar_turno_cliente_para_fila(
    cursor,
    id_cliente,
    id_phone_unidade,
    received_data_hora=None,
    usar_lock=False,
):
    if not id_cliente or not id_phone_unidade:
        logger.warning(
            "turno_cliente_invalido | motivo=dados_invalidos acao=bloquear_turno cliente=%s phone_number_id=%s",
            short_value(id_cliente),
            short_value(id_phone_unidade),
        )
        return {
            "pode_enfileirar": False,
            "motivo": "dados_invalidos",
        }

    if usar_lock:
        adquirir_lock_turno_cliente(cursor, id_cliente, id_phone_unidade)

    if received_data_hora is not None:
        interacao_posterior = buscar_interacao_posterior_a_mensagem(
            cursor,
            id_cliente,
            id_phone_unidade,
            received_data_hora,
        )

        if interacao_posterior is not None:
            logger.info(
                "turno_cliente_bloqueado | motivo=mensagem_reentregue_fora_de_ordem acao=nao_enfileirar cliente=%s phone_number_id=%s mensagem_em=%s ultima_interacao=%s",
                short_value(id_cliente),
                short_value(id_phone_unidade),
                received_data_hora,
                interacao_posterior,
            )
            return {
                "pode_enfileirar": False,
                "motivo": "mensagem_reentregue_fora_de_ordem",
            }

    turno = avaliar_filas_abertas_turno(
        cursor,
        id_cliente,
        id_phone_unidade,
    )

    if not turno["existe_fila_aberta"]:
        logger.debug(
            "turno_cliente_liberado | motivo=sem_fila_aberta acao=enfileirar cliente=%s phone_number_id=%s",
            short_value(id_cliente),
            short_value(id_phone_unidade),
        )
        return {
            "pode_enfileirar": True,
            "motivo": "sem_fila_aberta",
        }

    if turno["todas_abertas_respondidas"]:
        logger.info(
            "turno_cliente_liberado | motivo=fila_aberta_respondida_bot acao=enfileirar_recuperacao cliente=%s phone_number_id=%s total_abertas=%s",
            short_value(id_cliente),
            short_value(id_phone_unidade),
            turno["total_abertas"],
        )
        return {
            "pode_enfileirar": True,
            "motivo": "fila_aberta_respondida_bot",
        }

    logger.info(
        "turno_cliente_bloqueado | motivo=fila_aberta_sem_resposta_bot acao=nao_enfileirar cliente=%s phone_number_id=%s total_abertas=%s id_mensagem_bloqueadora=%s",
        short_value(id_cliente),
        short_value(id_phone_unidade),
        turno["total_abertas"],
        turno["id_mensagem_bloqueadora"],
    )
    return {
        "pode_enfileirar": False,
        "motivo": "fila_aberta_sem_resposta_bot",
    }


def adquirir_lock_turno_cliente(cursor, id_cliente, id_phone_unidade):
    cursor.execute("""
        SELECT pg_advisory_xact_lock(hashtext(%s), hashtext(%s));
    """, (str(id_phone_unidade), str(id_cliente)))

    logger.debug(
        "turno_cliente_lock | acao=advisory_xact_lock cliente=%s phone_number_id=%s",
        short_value(id_cliente),
        short_value(id_phone_unidade),
    )


def buscar_interacao_posterior_a_mensagem(
    cursor,
    id_cliente,
    id_phone_unidade,
    received_data_hora,
):
    cursor.execute("""
        SELECT c.last_interaction_at
        FROM chatbot.conversa c
        INNER JOIN chatbot.chat ch ON ch.id_chat=c.id_chat
        INNER JOIN chatbot.central_pos_venda u ON u.id_central=c.id_central
        WHERE ch.id_cliente = %s
          AND u.phone_number_id = %s
          AND c.last_interaction_at IS NOT NULL
          -- A Meta informa segundos inteiros; o histórico local tem microssegundos.
          -- O WAMID e a regra de fila aberta ainda se aplicam dentro do mesmo segundo.
          AND %s < date_trunc('second', c.last_interaction_at)
        ORDER BY c.last_interaction_at DESC, c.id_conversa DESC
        LIMIT 1;
    """, (
        id_cliente,
        id_phone_unidade,
        received_data_hora,
    ))

    resultado = cursor.fetchone()
    return resultado[0] if resultado else None


def avaliar_filas_abertas_turno(cursor, id_cliente, id_phone_unidade):
    cursor.execute("""
        WITH filas_abertas AS (
            SELECT
                f.id_mensagem,
                f.id_conversa,
                f.id_hash_msg,
                f.status,
                f.received_data_hora
            FROM chatbot.fila_mensagens f
            JOIN chatbot.central_pos_venda b ON b.id_central=f.id_central
            WHERE f.id_cliente = %s
              AND b.phone_number_id = %s
              AND f.status IN ('pending', 'processing')
        ),
        filas_sem_resposta_bot AS (
            SELECT
                f.id_mensagem
            FROM filas_abertas f
            LEFT JOIN chatbot.historico_mensagens h
              ON h.id_conversa = f.id_conversa
             AND h.quem_enviou = 'bot'
             AND h.status_envio = 'sent'
             AND h.id_mensagem_fila = f.id_mensagem
             AND h.id_hash_cliente_origem = f.id_hash_msg
            WHERE h.id_mensagem IS NULL
            ORDER BY f.received_data_hora, f.id_mensagem
            LIMIT 1
        )
        SELECT
            EXISTS (SELECT 1 FROM filas_abertas) AS existe_fila_aberta,
            NOT EXISTS (SELECT 1 FROM filas_sem_resposta_bot) AS todas_abertas_respondidas,
            (SELECT COUNT(*) FROM filas_abertas) AS total_abertas,
            (SELECT id_mensagem FROM filas_sem_resposta_bot LIMIT 1) AS id_mensagem_bloqueadora;
    """, (id_cliente, id_phone_unidade))

    resultado = cursor.fetchone()

    existe_fila_aberta = bool(resultado[0]) if resultado else False
    todas_abertas_respondidas = bool(resultado[1]) if resultado else False
    total_abertas = int(resultado[2] or 0) if resultado else 0
    id_mensagem_bloqueadora = resultado[3] if resultado else None

    logger.debug(
        "turno_cliente_fila_consultada | acao=avaliar_abertas cliente=%s phone_number_id=%s existe=%s todas_respondidas=%s total=%s bloqueadora=%s",
        short_value(id_cliente),
        short_value(id_phone_unidade),
        existe_fila_aberta,
        todas_abertas_respondidas,
        total_abertas,
        id_mensagem_bloqueadora,
    )

    return {
        "existe_fila_aberta": existe_fila_aberta,
        "todas_abertas_respondidas": todas_abertas_respondidas,
        "total_abertas": total_abertas,
        "id_mensagem_bloqueadora": id_mensagem_bloqueadora,
    }
```

## 31. `core/validacoes/compartilhamento_contato.py` (criar)

```python
import re

def telefone_compartilhado(mensagem, bsuid_esperado, wamids_pendentes):
    if not isinstance(mensagem, dict) or not bsuid_esperado or mensagem.get("from_user_id") != bsuid_esperado:
        return None
    if mensagem.get("type") != "contacts":
        return None
    contexto = mensagem.get("context") or {}
    if not isinstance(contexto, dict):
        return None
    resposta_a = contexto.get("id")
    if resposta_a and resposta_a not in wamids_pendentes:
        return None
    cartoes = mensagem.get("contacts") or []
    if not isinstance(cartoes, list) or len(cartoes) != 1 or not isinstance(cartoes[0], dict):
        return None
    if cartoes[0].get("origin") != "contact_request":
        return None
    telefones = cartoes[0].get("phones") or []
    if not isinstance(telefones, list) or len(telefones) != 1 or not isinstance(telefones[0], dict):
        return None
    wa_id = telefones[0].get("wa_id")
    return wa_id if isinstance(wa_id, str) and re.fullmatch(r"[1-9][0-9]{0,14}", wa_id) else None
```

## 32. `core/validacoes/destinatario_whatsapp.py` (criar)

```python
def escolher_destinatario(wa_id_confirmado, bsuid_vigente, contato_pendente):
    if wa_id_confirmado and not contato_pendente:
        return "wa_id", wa_id_confirmado
    if bsuid_vigente:
        return "bsuid", bsuid_vigente
    raise ValueError("Sem destinatário comprovado para o turno")
```

## 33. `workers/worker_flow/response_flow/etapas/resolver_compartilhamento.py` (criar)

```python
from core.validacoes.encaminhamento_pos_venda import LIMITE_TURNOS_SEM_AVANCO, pediu_humano

def acao_contato(*, solicitacao_enviada, telefone_provado, tipo, texto, erros_cliente):
    if not solicitacao_enviada:
        return "solicitar"
    if telefone_provado:
        return "confirmar_e_retomar"
    if pediu_humano(tipo, texto):
        return "humano_solicitado"
    if erros_cliente >= LIMITE_TURNOS_SEM_AVANCO:
        return "limite_sem_avanco"
    if tipo not in {"text", "interactive", "button"}:
        return "repetir_por_midia"
    return "repetir_botao"


from core.etapas_pos_venda import ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS, ETAPA_DETALHES, ETAPA_NOME, ETAPA_ENCAMINHAMENTO
from core.integrations.whatsapp.messages.tratamentos.midia import avisar_sobre_midia
from core.integrations.whatsapp.messages.compartilhamento_contato import mensagem_contato, primeiro_nome
from core.integrations.whatsapp.messages.etapa2_messages import montar_mensagem_etapa2
from core.integrations.whatsapp.pywa_functions.pywa_senders.compartilhamento_contato import enviar_solicitacao
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa1 import enviar_etapa1
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa4 import enviar_etapa4
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa5_pedidos import enviar_etapa5_pedidos
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa6_detalhes import enviar_etapa6_detalhes
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from workers.worker_flow.response_flow.transicoes.resolver_transicao import resolver_destino_transicao, anexar_transicao_ao_contexto_envio
from core.validacoes.compartilhamento_contato import telefone_compartilhado


def pedir(contexto, etapa, nome, *, repetir=False, reconfirmar=False, midia=False):
    uid = contexto["bsuid_vigente"]
    phone = contexto["central"]["phone_number_id"]
    texto = mensagem_contato(nome, repeticao=repetir, reconfirmacao=reconfirmar,
                             abertura=contexto.get("apresentacao_pendente", False))
    if midia:
        texto = avisar_sobre_midia(texto)
    envio = enviar_solicitacao(uid, phone, texto, etapa)
    return dict(envio, operacao_contato="repetir" if repetir else "abrir",
                motivo_contato="reconfirmacao" if reconfirmar else "cadastro",
                bsuid_contato=uid, tipo_destinatario="bsuid", valor_destinatario=uid)


def resolver_turno_contato(ctx):
    entrada = ctx["mensagem_cliente_atual"]
    etapa, pendente = ctx["id_etapa_atual"], ctx["solicitacao_contato"]
    nome = ctx["cadastro"].get("nome_titular")
    uid = ctx["bsuid_vigente"]
    prova = telefone_compartilhado(entrada.get("estrutura_compartilhamento") or {}, uid, pendente["wamids"])
    acao = acao_contato(solicitacao_enviada=True, telefone_provado=prova,
                        tipo=entrada["tipo_mensagem"], texto=entrada.get("conteudo_texto"),
                        erros_cliente=pendente["erros"])
    if acao == "confirmar_e_retomar":
        # A pergunta que contém dados cadastrais só é enviada depois da verificação no ingresso.
        if not ctx.get("telefone_compartilhado_apto") or ctx["telefone_compartilhado_apto"] != prova:
            raise ValueError("Prova conflitante ou sem autorização no ingresso")
        phone = ctx["central"]["phone_number_id"]
        em_outro_cadastro = bool(entrada["estrutura_compartilhamento"].get("_telefone_em_outro_cadastro"))
        destinatario = uid if em_outro_cadastro else prova
        if etapa == ETAPA_CPF:
            texto = montar_mensagem_etapa2(nome, contato_confirmado=True)
            envio = enviar_texto_pos_venda(destinatario, phone, texto, etapa)
        else:
            senders = {ETAPA_NOME: enviar_etapa1, ETAPA_PRODUTO: enviar_etapa3,
                       ETAPA_ASSUNTO: enviar_etapa4, ETAPA_PEDIDOS: enviar_etapa5_pedidos,
                        ETAPA_DETALHES: enviar_etapa6_detalhes}
            from core.integrations.whatsapp.pywa_functions.cliente import usar_prefixo_mensagem_bot
            with usar_prefixo_mensagem_bot("Obrigado por compartilhar seu contato!"):
                envio = senders[etapa](destinatario, phone)
        return dict(envio, operacao_contato="confirmar", bsuid_contato=uid, telefone_provado=prova,
                    telefone_em_outro_cadastro=em_outro_cadastro,
                    tipo_destinatario="bsuid" if em_outro_cadastro else "wa_id", valor_destinatario=destinatario)
    if acao in {"repetir_botao", "repetir_por_midia"}:
        return pedir(ctx, etapa, nome, repetir=True, midia=acao == "repetir_por_midia")
    destino = resolver_destino_transicao(ctx, acao, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento(ctx, acao)
    envio["operacao_contato"] = "encerrar"
    return anexar_transicao_ao_contexto_envio(ctx, envio, acao, destino)
```

## 34. `workers/worker_flow/response_flow/etapas/resolver_etapa1.py` (alterar)

```python
"""Saudação na própria etapa 1, coleta de nome e encaminhamento universal."""

from core.etapas_pos_venda import ETAPA_CPF
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa1 import enviar_etapa1, enviar_nome_invalido
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa2 import enviar_etapa2
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa1 import validar_contexto_etapa1
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


from workers.worker_flow.response_flow.etapas.resolver_compartilhamento import pedir
from core.integrations.whatsapp.messages.compartilhamento_contato import primeiro_nome


def resolve_etapa1(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = contexto_historico.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]

    # Histórico confirmado diferencia saudação de resposta ao nome, sem etapa artificial.
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa1(destinatario, remetente)

    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa1(contexto_historico)
    if validacao is None:
        return repetir_etapa(contexto_historico, enviar_nome_invalido, destinatario, remetente)

    evento = validacao["evento"]
    destino = resolver_destino_transicao(contexto_historico, evento, destinos_esperados={ETAPA_CPF})
    nome = validacao["nome_titular"]
    uid = contexto_historico.get("bsuid_vigente")
    if uid and (not mensagem.get("cliente_telefone") or not contexto_historico.get("wa_id_confirmado")):
        envio = pedir(contexto_historico, destino, nome)
    else:
        envio = enviar_etapa2(destinatario, remetente, nome_titular=primeiro_nome(nome))
    envio["nome_titular"] = nome
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
```

## 35. `workers/worker_flow/response_flow/etapas/resolver_etapa2.py` (alterar)

```python
"""Coleta do CPF e apresentação do produto, sem consulta ou coleta de cidade."""

from core.etapas_pos_venda import ETAPA_PRODUTO
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa2 import (
    enviar_cpf_invalido, enviar_etapa2,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa2 import validar_contexto_etapa2
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa2(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = contexto_historico.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]
    # Cadastro parcial: uma nova conversa pergunta o CPF antes de interpretar sua entrada.
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa2(
            destinatario, remetente,
            nome_titular=(contexto_historico.get("cadastro") or {}).get("nome_titular"), abertura=True,
        )
    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa2(contexto_historico)
    if validacao is None:
        return repetir_etapa(contexto_historico, enviar_cpf_invalido, destinatario, remetente)

    evento = validacao["evento"]
    destino = resolver_destino_transicao(
        contexto_historico, evento, destinos_esperados={ETAPA_PRODUTO},
    )
    envio = enviar_etapa3(destinatario, remetente)
    envio["cpf_titular"] = validacao["cpf_titular"]
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
```

## 36. `workers/worker_flow/response_flow/etapas/resolver_etapa3.py` (alterar)

```python
"""Produto: apresentação, tratamento universal, correção e avanço para assunto."""
from core.etapas_pos_venda import ETAPA_ASSUNTO
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa4 import enviar_etapa4
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa3 import validar_contexto_etapa3
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa3(contexto_historico):
    mensagem = contexto_historico["mensagem_cliente_atual"]
    destinatario, remetente = contexto_historico.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]
    if contexto_historico.get("apresentacao_pendente"):
        return enviar_etapa3(
            destinatario, remetente,
            nome_titular=(contexto_historico.get("cadastro") or {}).get("nome_titular"),
        )
    tratamento = resolver_tratamento_universal(contexto_historico)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa3(contexto_historico)
    if validacao is None:
        return repetir_etapa(contexto_historico, enviar_etapa3, destinatario, remetente, invalido=True)
    evento = validacao["evento"]
    destino = resolver_destino_transicao(contexto_historico, evento, destinos_esperados={ETAPA_ASSUNTO})
    envio = enviar_etapa4(destinatario, remetente)
    envio["produto"] = validacao["produto"]
    return anexar_transicao_ao_contexto_envio(contexto_historico, envio, evento, destino)
```

## 37. `workers/worker_flow/response_flow/etapas/resolver_etapa4.py` (alterar)

```python
"""Assunto do atendimento: repetir a lista, encaminhar ou apresentar os pedidos."""
from core.etapas_pos_venda import ETAPA_PEDIDOS
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa4 import enviar_etapa4
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa5_pedidos import enviar_etapa5_pedidos
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_etapa4 import validar_contexto_etapa4
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    anexar_transicao_ao_contexto_envio, resolver_destino_transicao,
)


def resolve_etapa4(contexto):
    mensagem = contexto["mensagem_cliente_atual"]
    destinatario, remetente = contexto.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]
    if contexto.get("apresentacao_pendente"):
        return enviar_etapa4(destinatario, remetente)
    tratamento = resolver_tratamento_universal(contexto)
    if tratamento is not None:
        return tratamento
    validacao = validar_contexto_etapa4(contexto)
    if validacao is None:
        return repetir_etapa(contexto, enviar_etapa4, destinatario, remetente, invalido=True)
    evento = validacao["evento"]
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_PEDIDOS})
    envio = enviar_etapa5_pedidos(destinatario, remetente)
    envio["assunto"] = validacao["assunto"]
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
```

## 38. `workers/worker_flow/response_flow/etapas/resolver_etapa5_pedidos.py` (alterar)

```python
"""Coleta os pedidos do varejo e apresenta a pergunta definida no mapa de transição."""
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa5_pedidos import enviar_etapa5_pedidos
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa6_detalhes import enviar_etapa6_detalhes
from core.validacoes.pedidos_pos_venda import transicao_dos_pedidos
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_pedidos_etapa5 import validar_contexto_pedidos
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa5_pedidos(contexto):
    mensagem = contexto["mensagem_cliente_atual"]
    destinatario, remetente = contexto.get("destinatario_envio", mensagem.get("cliente_telefone")), mensagem["id_phone_unidade"]
    if contexto.get("apresentacao_pendente"):
        return enviar_etapa5_pedidos(destinatario, remetente)
    tratamento = resolver_tratamento_universal(contexto)
    if tratamento is not None:
        return tratamento
    numeros, quantidade_informada = validar_contexto_pedidos(contexto)
    if numeros is None:
        return repetir_etapa(contexto, enviar_etapa5_pedidos, destinatario, remetente, quantidade_para_correcao=quantidade_informada)
    evento, esperado = transicao_dos_pedidos(contexto["assunto"], perdeu_nota=not numeros)
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={esperado})
    envio = enviar_etapa6_detalhes(destinatario, remetente)
    envio["numeros_pedido"] = numeros
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
```

## 39. `workers/worker_flow/response_flow/flow_sender.py` (alterar)

```python
"""Despacho das etapas de pós-venda já portadas, com barreira de replay."""
from core.etapas_pos_venda import ETAPA_NOME, ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS, ETAPA_DETALHES
from core.integrations.whatsapp.remetente import usar_remetente_central
from workers.worker_flow.response_flow.etapas.resolver_etapa1 import resolve_etapa1
from workers.worker_flow.response_flow.etapas.resolver_etapa2 import resolve_etapa2
from workers.worker_flow.response_flow.etapas.resolver_etapa3 import resolve_etapa3
from workers.worker_flow.response_flow.etapas.resolver_etapa4 import resolve_etapa4
from workers.worker_flow.response_flow.etapas.resolver_etapa5_pedidos import resolve_etapa5_pedidos


from workers.worker_flow.response_flow.etapas.resolver_etapa6_detalhes import resolve_etapa6_detalhes
from core.validacoes.destinatario_whatsapp import escolher_destinatario
from workers.worker_flow.response_flow.etapas.resolver_compartilhamento import pedir, resolver_turno_contato


def flow_sender(contexto_historico):
    resposta = contexto_historico.get("resposta_bot_para_mensagem_atual")
    if resposta:
        if contexto_historico["id_etapa_atual"] != resposta["id_etapa"]:
            raise ValueError("Resposta confirmada não corresponde à etapa persistida.")
        evento = ((resposta.get("interativo") or {}).get("_fluxo") or {}).get("evento")
        return {
            "enviou": False, "resposta_ja_existia": True,
            "id_hash_msg_bot": resposta["id_hash_msg"], "id_etapa_resultante": resposta["id_etapa"],
            "evento_transicao": evento,
        }
    with usar_remetente_central(
        contexto_historico["central"], contexto_historico["mensagem_cliente_atual"]["id_phone_unidade"],
    ):
        mensagem = contexto_historico["mensagem_cliente_atual"]
        telefone = contexto_historico.get("wa_id_confirmado", mensagem.get("cliente_telefone"))
        uid = contexto_historico.get("bsuid_vigente")
        pendencia = contexto_historico.get("solicitacao_contato")
        tipo, valor = escolher_destinatario(telefone, uid, pendencia)
        ctx = dict(contexto_historico, destinatario_envio=valor)
        if pendencia:
            envio = resolver_turno_contato(ctx)
        elif (uid and not telefone and ctx["id_etapa_atual"] != ETAPA_NOME
              and (not ctx.get("telefone_compartilhado") or ctx.get("reconfirmar_telefone"))):
            envio = pedir(ctx, ctx["id_etapa_atual"], ctx["cadastro"].get("nome_titular"),
                          reconfirmar=ctx.get("reconfirmar_telefone",False))
        else:
            envio = _despachar_etapa(ctx)
        envio.setdefault("tipo_destinatario",tipo)
        envio.setdefault("valor_destinatario",valor)
        return envio


def _despachar_etapa(contexto_historico):
    if contexto_historico["id_etapa_atual"] == ETAPA_NOME:
        return resolve_etapa1(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_CPF:
        return resolve_etapa2(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_PRODUTO:
        return resolve_etapa3(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_ASSUNTO:
        return resolve_etapa4(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_PEDIDOS:
        return resolve_etapa5_pedidos(contexto_historico)
    if contexto_historico["id_etapa_atual"] == ETAPA_DETALHES:
        return resolve_etapa6_detalhes(contexto_historico)
    # Não despachar por engano as antigas etapas do Supera com os mesmos IDs.
    raise NotImplementedError(
        f"Etapa de pós-venda {contexto_historico['id_etapa_atual']} ainda não implementada."
    )
```

## 40. `workers/worker_flow/response_flow/flow_worker.py` (conservar)

```python
import logging
from functools import partial

import psycopg
from core.cache.cache_unidade import UnidadeNaoEncontrada
from core.repositories.unidades.consultas import (
    UnidadeDesativada,
    exigir_unidade_habilitada_por_phone_id,
)
from core.database.connection_aws import get_conn
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.integrations.whatsapp.pywa_functions.cliente import antes_do_primeiro_envio
from core.integrations.whatsapp.pywa_functions.digitacao import indicar_digitacao
from core.logging_config import referencia_wamid, short_value
from core.repositories.atendimento.conversas import tentar_lock_conversa
from core.repositories.atendimento.locks import (
    LockConversaPerdido,
    proteger_conversa,
    reler_conversa,
)
from core.repositories.atendimento.fila import (
    pegar_mensagens_da_fila,
    reagendar_mensagem_sem_erro,
    vincular_mensagem_fila_a_conversa,
)
from workers.tratamento_erros_externos.erro_conexao import handle_erro_conexao
from workers.tratamento_erros_externos.erro_generico import handle_erro_generico
from workers.tratamento_erros_externos.exceptions import BancoFalhouAposEnvioMeta
from workers.tratamento_erros_externos.unidade_nao_encontrada import (
    handle_unidade_nao_encontrada,
)
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.suporte.cache_repair import (
    confirmar_cache_cliente_se_pendente,
    reparar_cache_cliente_stale_se_fk_invalida,
    reparar_cache_unidade_stale_se_fk_invalida,
)
from workers.worker_flow.suporte.estado_ciclo import (
    aguardar_fila_vazia,
    atualizar_estado_com_contexto,
    atualizar_estado_com_mensagem,
    atualizar_estado_lock,
    criar_estado_ciclo,
    montar_mensagem_fila,
)
from workers.worker_flow.transacoes.finalizacao_fila import (
    finalizar_mensagem_processada,
    registrar_cache_bloqueio_apos_commit,
)
from workers.worker_flow.transacoes.lock_conversa import (
    liberar_lock_conversa_se_necessario,
)
from workers.worker_flow.transacoes.ordem_turno import (
    logar_lock_recusado,
    reagendar_se_houver_mensagem_anterior,
)
from workers.worker_flow.transacoes.persistencia_resposta import (
    atualizar_banco_com_contexto_final,
)
from workers.worker_flow.tratar_bloqueio import tratar_conversa_bloqueada
from workers.worker_flow.valida_banco import validar_banco_mensagem
from workers.worker_flow.valida_historico import valida_historico

logger = logging.getLogger("worker.response_flow")


def worker_flow():
    logger.info("worker_iniciado")

    max_retry = 3
    retry_delay = 5

    while True:
        logger.debug("ciclo_worker_inicio")

        conn_ciclo = None
        cursor_ciclo = None
        # Nenhum desvio pode reutilizar dados da mensagem do ciclo anterior.
        mensagem = None
        resultado_encerramento = None
        estado_ciclo = criar_estado_ciclo()
        contexto_envio = {}

        try:
            conn_ciclo = get_conn(application_name="worker_chatbot")
            cursor_ciclo = conn_ciclo.cursor()
            retry_delay = 5
            logger.debug("ciclo_conexao_banco_ok | acao=dequeue")

            registro = pegar_mensagens_da_fila(cursor_ciclo)
            conn_ciclo.commit()

            if not registro:
                conn_ciclo.close()
                conn_ciclo = None
                cursor_ciclo = None
                aguardar_fila_vazia()
                continue

            mensagem = montar_mensagem_fila(registro)
            atualizar_estado_com_mensagem(estado_ciclo, mensagem)

            logger.info(
                "mensagem_processando | acao=iniciar id_mensagem=%s cliente=%s phone_number_id=%s tipo=%s retry=%s",
                mensagem["id_mensagem"],
                short_value(mensagem["cliente_telefone"]),
                short_value(mensagem["id_phone_unidade"]),
                mensagem["tipo_mensagem"],
                mensagem["retry_count"],
            )

            if reagendar_se_houver_mensagem_anterior(
                mensagem,
                cursor_ciclo,
            ):
                conn_ciclo.commit()
                continue

            exigir_unidade_habilitada_por_phone_id(mensagem["id_phone_unidade"], cursor_ciclo)
            contexto_banco = validar_banco_mensagem(
                mensagem,
                cursor_ciclo,
            )
            atualizar_estado_com_contexto(estado_ciclo, contexto_banco)

            contexto_conversa = contexto_banco["conversa"]
            id_conversa = contexto_conversa["id_conversa"]

            conn_ciclo.commit()
            logger.debug(
                "contexto_banco_confirmado | acao=commit id_mensagem=%s id_conversa_calculada=%s estado=%s",
                mensagem["id_mensagem"],
                id_conversa,
                contexto_conversa["estado"],
            )

            confirmar_cache_cliente_se_pendente(contexto_banco)

            if contexto_conversa["estado"] == "bloqueada":
                tratar_conversa_bloqueada(
                    mensagem["id_mensagem"],
                    mensagem["cliente_telefone"],
                    mensagem["id_phone_unidade"],
                    id_conversa,
                    cursor_ciclo,
                )
                conn_ciclo.commit()
                continue

            lock_ok, lock_version = tentar_lock_conversa(id_conversa, cursor_ciclo)
            conn_ciclo.commit()
            atualizar_estado_lock(estado_ciclo, lock_ok, lock_version)

            if not lock_ok:
                logar_lock_recusado(mensagem, contexto_banco)
                reagendar_mensagem_sem_erro(
                    mensagem["id_mensagem"],
                    cursor_ciclo,
                    delay_seconds=5,
                )
                conn_ciclo.commit()
                continue

            linhas_vinculadas = vincular_mensagem_fila_a_conversa(
                mensagem["id_mensagem"],
                id_conversa,
                cursor_ciclo,
            )

            if linhas_vinculadas == 0:
                logger.critical(
                    "mensagem_conversa_vinculo_inconsistente | "
                    "motivo=historico_conflitante_ou_fila_ausente "
                    "acao=reagendar_sem_consumir_retry id_mensagem=%s "
                    "cliente=%s phone_number_id=%s "
                    "id_conversa_calculada=%s",
                    mensagem["id_mensagem"],
                    short_value(mensagem["cliente_telefone"]),
                    short_value(mensagem["id_phone_unidade"]),
                    id_conversa,
                )
                reagendar_mensagem_sem_erro(
                    mensagem["id_mensagem"],
                    cursor_ciclo,
                    delay_seconds=300,
                )
                conn_ciclo.commit()
                continue

            contexto_banco = reler_conversa(contexto_banco, lock_version, cursor_ciclo)
            exigir_unidade_habilitada_por_phone_id(mensagem["id_phone_unidade"], cursor_ciclo)
            contexto_conversa = contexto_banco["conversa"]
            contexto_historico = valida_historico(
                mensagem,
                contexto_banco,
                cursor_ciclo,
            )
            conn_ciclo.commit()
            logger.debug(
                "historico_contexto_ok | acao=commit id_mensagem=%s id_conversa=%s etapa_cliente=%s etapa_resposta=%s inserido=%s",
                mensagem["id_mensagem"],
                id_conversa,
                contexto_historico["id_etapa_cliente"],
                contexto_historico["id_etapa_resposta"],
                contexto_historico["mensagem_cliente_inserida"],
            )

            proteger_conversa(id_conversa, lock_version, cursor_ciclo, renovar=True)
            exigir_unidade_habilitada_por_phone_id(mensagem["id_phone_unidade"], cursor_ciclo)
            conn_ciclo.commit()
            # O escopo não chama a Meta: só um sender com resposta pronta o faz.
            # Replays e resolvers sem envio não ativam o indicador.
            with antes_do_primeiro_envio(partial(
                indicar_digitacao,
                mensagem["id_phone_unidade"],
                mensagem.get("id_hash"),
                id_mensagem=mensagem["id_mensagem"],
                id_conversa=id_conversa,
            )):
                contexto_envio = flow_sender(contexto_historico)

            try:
                proteger_conversa(id_conversa, lock_version, cursor_ciclo)
                contexto_final = atualizar_banco_com_contexto_final(
                    contexto_historico, contexto_envio, cursor_ciclo
                )
                conn_ciclo.commit()

            except Exception as erro:
                if contexto_envio.get("enviou"):
                    raise BancoFalhouAposEnvioMeta(
                        "Banco falhou depois da Meta confirmar envio",
                        id_mensagem=mensagem["id_mensagem"],
                        id_conversa=id_conversa,
                        id_hash_msg_bot=contexto_envio.get("id_hash_msg_bot"),
                        id_etapa=contexto_envio.get("id_etapa_resultante"),
                    ) from erro

                raise

            logger.debug(
                "resposta_bot_contexto_final_ok | acao=commit id_mensagem=%s id_conversa=%s etapa=%s resposta_ja_existia=%s ref_envio=%s tratamento=%s tipo_tratamento=%s",
                mensagem["id_mensagem"],
                id_conversa,
                contexto_final["id_etapa_resultante"],
                contexto_final["resposta_ja_existia"],
                referencia_wamid(contexto_final["id_hash_msg_bot"]),
                contexto_envio.get("tratamento", False),
                contexto_envio.get("tipo_tratamento"),
            )

            proteger_conversa(id_conversa, lock_version, cursor_ciclo)
            resultado_encerramento = finalizar_mensagem_processada(
                mensagem,
                contexto_banco,
                lock_version,
                cursor_ciclo,
                contexto_final,
            )
            conn_ciclo.commit()

            if resultado_encerramento is None:
                raise RuntimeError("Finalização da mensagem sem resultado de encerramento")

            logger.info(
                "mensagem_processada | status=sent id_mensagem=%s id_central=%s id_conversa=%s "
                "etapa=%s evento=%s tentativa=%s ref_envio=%s lock_version=%s atendimento_encerrado=%s "
                "movimento=%s turnos_sem_avanco=%s resposta_ja_existia=%s",
                mensagem["id_mensagem"], contexto_banco["id_central"], id_conversa,
                contexto_final["id_etapa_resultante"], contexto_envio.get("evento_transicao"), mensagem["retry_count"],
                referencia_wamid(contexto_final.get("id_hash_msg_bot")), lock_version,
                resultado_encerramento["atendimento_encerrado"],
                contexto_final.get("movimento_conversa"), contexto_final.get("turnos_sem_avanco"),
                contexto_final["resposta_ja_existia"],
            )
            registrar_cache_bloqueio_apos_commit(
                mensagem,
                resultado_encerramento,
            )

        except UnidadeDesativada:
            if mensagem is None:
                raise
            conn_ciclo.rollback()
            # Preserva pendência/histórico; a função dequeue não reserva inativas.
            reagendar_mensagem_sem_erro(
                mensagem["id_mensagem"], cursor_ciclo, delay_seconds=300,
                retry_esperado=mensagem["retry_count"],
            )
            conn_ciclo.commit()
            logger.info("unidade_desativada | acao=preservar_pendente id_mensagem=%s", mensagem["id_mensagem"])

        except LockConversaPerdido:
            if conn_ciclo:
                conn_ciclo.rollback()
            # Não reescreve uma fila que pode estar sendo processada pelo novo dono.
            logger.warning(
                "lock_perdido | acao=aguardar_recuperacao_fila id_conversa=%s",
                estado_ciclo["id_conversa"],
            )

        except ErroEnvioMeta as erro:
            logger.warning(
                "meta_envio_erro | acao=reagendar_sem_sent id_mensagem=%s cliente=%s phone_number_id=%s etapa=%s erro=%s",
                estado_ciclo["id_mensagem"],
                short_value(estado_ciclo["cliente_telefone"]),
                short_value(estado_ciclo["id_phone_unidade"]),
                erro.id_etapa,
                erro,
            )
            if conn_ciclo:
                conn_ciclo.rollback()

            handle_erro_generico(
                cursor_ciclo,
                estado_ciclo["id_mensagem"],
                erro,
                max_retry,
            )

            if conn_ciclo:
                conn_ciclo.commit()

        except BancoFalhouAposEnvioMeta as erro:
            if isinstance(erro.__cause__, LockConversaPerdido):
                conn_ciclo.rollback()
                logger.critical(
                    "meta_confirmou_com_lock_perdido | id_conversa=%s ref_envio=%s risco=duplicidade",
                    erro.id_conversa,
                    referencia_wamid(erro.id_hash_msg_bot),
                )
                continue
            logger.critical(
                "banco_falhou_apos_envio_meta | risco=resposta_duplicada acao=reagendar_sem_sent id_mensagem=%s id_conversa=%s etapa=%s ref_envio=%s tratamento=%s tipo_tratamento=%s erro=%s",
                erro.id_mensagem,
                erro.id_conversa,
                erro.id_etapa,
                referencia_wamid(erro.id_hash_msg_bot),
                contexto_envio.get("tratamento", False),
                contexto_envio.get("tipo_tratamento"),
                erro,
            )
            if conn_ciclo:
                conn_ciclo.rollback()

            handle_erro_generico(
                cursor_ciclo,
                estado_ciclo["id_mensagem"],
                erro,
                max_retry,
            )

            if conn_ciclo:
                conn_ciclo.commit()

        except psycopg.OperationalError as erro:
            logger.warning(
                "banco_operacional_erro | acao=retry_conexao id_mensagem=%s erro=%s",
                estado_ciclo["id_mensagem"],
                erro,
            )
            retry_delay = handle_erro_conexao(erro, retry_delay)
            continue

        except UnidadeNaoEncontrada as erro:
            logger.warning(
                "unidade_nao_encontrada | acao=tratar_unidade_invalida id_mensagem=%s cliente=%s phone_number_id=%s erro=%s",
                estado_ciclo["id_mensagem"],
                short_value(estado_ciclo["cliente_telefone"]),
                short_value(estado_ciclo["id_phone_unidade"]),
                erro,
            )
            if conn_ciclo:
                conn_ciclo.rollback()

            handle_unidade_nao_encontrada(
                cursor_ciclo,
                estado_ciclo["id_mensagem"],
                erro,
            )

            if conn_ciclo:
                conn_ciclo.commit()

        except Exception as erro:
            logger.exception(
                "mensagem_erro | acao=tratar_erro_generico id_mensagem=%s cliente=%s phone_number_id=%s id_conversa=%s estado=%s erro=%s",
                estado_ciclo["id_mensagem"],
                short_value(estado_ciclo["cliente_telefone"]),
                short_value(estado_ciclo["id_phone_unidade"]),
                estado_ciclo["id_conversa"],
                estado_ciclo["estado"],
                erro,
            )
            if conn_ciclo:
                conn_ciclo.rollback()

            reparar_cache_cliente_stale_se_fk_invalida(erro, estado_ciclo)
            reparar_cache_unidade_stale_se_fk_invalida(erro, estado_ciclo)

            handle_erro_generico(
                cursor_ciclo,
                estado_ciclo["id_mensagem"],
                erro,
                max_retry,
            )

            if conn_ciclo:
                conn_ciclo.commit()

        finally:
            if conn_ciclo:
                try:
                    unlock_realizado = liberar_lock_conversa_se_necessario(
                        cursor_ciclo,
                        estado_ciclo,
                    )

                    if unlock_realizado is not None:
                        conn_ciclo.commit()

                except Exception as erro:
                    logger.exception(
                        "finalizacao_ciclo_falhou | acao=continuar_para_close erro=%s",
                        erro,
                    )

                finally:
                    try:
                        conn_ciclo.close()

                    except Exception as erro:
                        logger.exception(
                            "conexao_ciclo_close_falhou | acao=registrar_e_continuar erro=%s",
                            erro,
                        )
```

## 41. `workers/worker_flow/suporte/cache_repair.py` (alterar)

```python
import logging

from core.cache.cache_unidade import recarregar_cache_unidades
from core.cache.runtime.cache_cliente import remover_cliente_cache, salvar_cliente_cache
from core.logging_config import short_value


logger = logging.getLogger("worker.support")


def confirmar_cache_cliente_se_pendente(contexto_banco):
    if not contexto_banco.get("cliente_cache_pendente"):
        return False

    if contexto_banco.get("cliente_telefone"):
        salvar_cliente_cache(contexto_banco["cliente_telefone"],contexto_banco["id_cliente"])
    if contexto_banco.get("bsuid_origem"):
        salvar_cliente_cache(contexto_banco["bsuid_origem"],contexto_banco["id_cliente"],
                             id_central=contexto_banco["id_central"],tipo="bsuid")
    contexto_banco["cliente_cache_pendente"] = False

    logger.debug(
        "cliente_cache_confirmado | acao=salvar cliente=%s id_cliente=%s",
        short_value(contexto_banco["cliente_telefone"]),
        contexto_banco["id_cliente"],
    )
    return True


def reparar_cache_cliente_stale_se_fk_invalida(erro, estado_ciclo):
    erro_texto = str(erro)

    if "chat_id_cliente_fkey" not in erro_texto:
        return False

    cliente_telefone = estado_ciclo.get("cliente_telefone")

    if not cliente_telefone:
        return False

    removido = remover_cliente_cache(cliente_telefone)

    logger.warning(
        "cliente_cache_stale_reparado | motivo=fk_cliente_inexistente acao=remover_cache cliente=%s id_mensagem=%s removido=%s",
        short_value(cliente_telefone),
        estado_ciclo.get("id_mensagem"),
        removido,
    )
    return removido


def reparar_cache_unidade_stale_se_fk_invalida(erro, estado_ciclo):
    erro_texto = str(erro)

    if "chat_id_central_fkey" not in erro_texto:
        return False

    total_unidades = recarregar_cache_unidades()

    logger.warning(
        "unidade_cache_stale_reparado | motivo=fk_unidade_inexistente acao=recarregar_cache_unidades phone_number_id=%s id_mensagem=%s unidades=%s",
        short_value(estado_ciclo.get("id_phone_unidade")),
        estado_ciclo.get("id_mensagem"),
        total_unidades,
    )
    return total_unidades is not None
```

## 42. `workers/worker_flow/transacoes/efeitos_transicao.py` (alterar)

```python
"""Efeitos de negócio por etapa de origem, após o envio confirmado.

O ciclo transacional permanece no flow_worker. Este módulo coordena chamadas
aos repositórios; não executa SQL, commit, rollback, HTTP ou escrita em cache.
"""

from core.identidade_atendimento import conciliar_apos_cpf
from core.etapas_pos_venda import (
    ETAPA_NOME, ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, EVENTO_PRODUTO_ESCOLHIDO,
    ETAPA_PEDIDOS, ETAPA_DETALHES, EVENTO_SITUACAO_INFORMADA, EVENTO_ASSUNTO_ESCOLHIDO,
    ETAPA_ENCAMINHAMENTO, EVENTO_NOME_VALIDO_FALTA_CPF,
    EVENTO_CPF_VALIDO,
    EVENTOS_ENCAMINHAMENTO,
)
from core.repositories.atendimento.clientes import atualizar_nome_titular, atualizar_cpf_titular
from core.repositories.atendimento.pos_venda import (
    atualizar_nome_do_atendimento, atualizar_cpf_do_atendimento,
    registrar_contatos_encaminhados, atualizar_produto_do_atendimento,
    atualizar_assunto_do_atendimento, registrar_detalhes,
)
from core.validacoes.assunto_pos_venda import ASSUNTOS
from core.validacoes.encaminhamento_pos_venda import grupos_encaminhamento
from core.validacoes.produto_pos_venda import PRODUTOS
from core.validacoes.pedidos_pos_venda import pedidos_de_filiais_cadastradas, transicao_dos_pedidos
from core.repositories.atendimento.pedidos import inserir_pedidos_da_conversa, registrar_situacao_nota

_CAMPOS_EFEITO = frozenset({
    "nome_titular", "cpf_titular", "produto", "assunto", "encaminhado_baratao", "encaminhado_atacadao",
    "numeros_pedido", "detalhes",
})


def _validar_campos_efeito(envio, permitidos):
    """Presença de chaves complementa a etapa/evento; não escolhe o efeito."""
    if (_CAMPOS_EFEITO & envio.keys()) != set(permitidos):
        raise ValueError("Dados de negócio incompatíveis com a etapa e o evento.")
    campos_textuais = permitidos - {"numeros_pedido"}
    if any(not isinstance(envio[chave], str) or not envio[chave].strip() for chave in campos_textuais):
        raise ValueError("Dado obrigatório ausente ao confirmar efeito da etapa.")


def _validar_destino(contexto, envio, destino_esperado):
    evento = envio.get("evento_transicao")
    if (
        envio["id_etapa_resultante"] != destino_esperado
        or (contexto.get("transicoes_permitidas") or {}).get(evento) != destino_esperado
        or envio.get("tratamento")
    ):
        raise ValueError("Efeito incompatível com a transição autorizada.")


def _registrar_encaminhamento(contexto, envio, cursor):
    """O efeito exige os contatos das redes identificadas para este atendimento."""
    _validar_destino(contexto, envio, ETAPA_ENCAMINHAMENTO)
    grupos = grupos_encaminhamento(contexto)
    campos = {f"encaminhado_{grupo}" for grupo in grupos}
    if envio["evento_transicao"] == EVENTO_SITUACAO_INFORMADA:
        campos.add("detalhes")
    _validar_campos_efeito(envio, campos)
    registrar_contatos_encaminhados(
        contexto["id_conversa"], envio.get("encaminhado_baratao"),
        envio.get("encaminhado_atacadao"), cursor,
    )
    return {"encaminhado": True}


def atualizar_banco_conforme_transicao_de_etapa(contexto, envio, cursor):
    # Recuperação de resposta já confirmada não repete efeitos de negócio.
    if envio.get("resposta_ja_existia"):
        return {}

    operacao = envio.get("operacao_contato")
    if operacao:
        aplicar_efeito_contato(contexto,envio,cursor)
        if operacao in {"confirmar","repetir"} or (operacao=="abrir" and not envio.get("evento_transicao")):
            return {}
    etapa = contexto["id_etapa_origem_transicao"]
    evento = envio.get("evento_transicao")
    destino = envio["id_etapa_resultante"]
    if envio.get("id_etapa_origem_transicao", etapa) != etapa:
        raise ValueError("Origem do envio diferente da etapa da mensagem processada.")

    # NOME (1): repetição, encaminhamento universal ou nome confirmado → CPF.
    if etapa == ETAPA_NOME:
        if not evento and destino == ETAPA_NOME:
            _validar_campos_efeito(envio, set())
            # O contador comum é persistido em persistencia_resposta, uma única vez.
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_NOME_VALIDO_FALTA_CPF:
            _validar_destino(contexto, envio, ETAPA_CPF)
            _validar_campos_efeito(envio, {"nome_titular"})
            nome = envio["nome_titular"]
            atualizar_nome_titular(contexto["id_cliente"], nome, cursor)
            atualizar_nome_do_atendimento(contexto["id_conversa"], nome, cursor)
            return {"nome_titular": nome}

    # CPF (2): repetição, encaminhamento universal ou CPF confirmado → produto.
    elif etapa == ETAPA_CPF:
        if not evento and destino == ETAPA_CPF:
            _validar_campos_efeito(envio, set())
            # Não sobrescrever CPF global em resposta inválida nem duplicar o contador.
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_CPF_VALIDO:
            _validar_destino(contexto, envio, ETAPA_PRODUTO)
            _validar_campos_efeito(envio, {"cpf_titular"})
            cpf = envio["cpf_titular"]
            if len(cpf) != 11 or not cpf.isascii() or not cpf.isdigit():
                raise ValueError("O efeito de CPF exige 11 dígitos ASCII já normalizados.")
            resultado = conciliar_apos_cpf(contexto, cpf, cursor)
            if resultado.cadastro_para_cpf is not None:
                atualizar_cpf_titular(resultado.cadastro_para_cpf, cpf, cursor)
            atualizar_cpf_do_atendimento(contexto["id_conversa"], cpf, cursor)
            efeito = {"cpf_titular": cpf}
            if resultado.cache:
                efeito["cache_conciliacao"] = resultado.cache
            return efeito

    # PRODUTO (3): pertence ao atendimento atual, nunca ao cadastro global.
    elif etapa == ETAPA_PRODUTO:
        if not evento and destino == ETAPA_PRODUTO:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_PRODUTO_ESCOLHIDO:
            _validar_destino(contexto, envio, ETAPA_ASSUNTO)
            _validar_campos_efeito(envio, {"produto"})
            produto = envio["produto"]
            if produto not in PRODUTOS:
                raise ValueError("Produto inválido ao confirmar escolha.")
            atualizar_produto_do_atendimento(contexto["id_conversa"], produto, cursor)
            return {"produto": produto}

    # ASSUNTO (4): a escolha pertence à mesma conversa que o produto.
    elif etapa == ETAPA_ASSUNTO:
        if not evento and destino == ETAPA_ASSUNTO:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_ASSUNTO_ESCOLHIDO:
            _validar_destino(contexto, envio, ETAPA_PEDIDOS)
            _validar_campos_efeito(envio, {"assunto"})
            assunto = envio["assunto"]
            if assunto not in ASSUNTOS:
                raise ValueError("Assunto inválido ao confirmar escolha.")
            atualizar_assunto_do_atendimento(contexto["id_conversa"], assunto, cursor)
            return {"assunto": assunto}

    # PEDIDOS (5): o vínculo com a filial pertence a cada número desta conversa.
    elif etapa == ETAPA_PEDIDOS:
        if not evento and destino == ETAPA_PEDIDOS:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        _validar_campos_efeito(envio, {"numeros_pedido"})
        numeros = envio["numeros_pedido"]
        if not isinstance(numeros, list):
            raise ValueError("O efeito de pedidos exige a lista de números confirmados.")
        perdeu_nota = not numeros
        esperado, destino_esperado = transicao_dos_pedidos(contexto["assunto"], perdeu_nota=perdeu_nota)
        if evento != esperado:
            raise ValueError("Evento de pedidos incompatível com o assunto ou a opção de nota perdida.")
        _validar_destino(contexto, envio, destino_esperado)
        if numeros:
            if not pedidos_de_filiais_cadastradas(numeros, contexto["codigos_filiais"]):
                raise ValueError("Pedido ou filial inválidos ao confirmar o atendimento.")
            inserir_pedidos_da_conversa(contexto["id_conversa"], numeros, cursor)
        registrar_situacao_nota(contexto["id_conversa"], perdeu_nota, cursor)
        return {"perdeu_nota": perdeu_nota}

    elif etapa == ETAPA_DETALHES:
        if not evento and destino == ETAPA_DETALHES:
            _validar_campos_efeito(envio, set())
            return {}
        if evento in EVENTOS_ENCAMINHAMENTO:
            return _registrar_encaminhamento(contexto, envio, cursor)
        if evento == EVENTO_SITUACAO_INFORMADA:
            resultado = _registrar_encaminhamento(contexto, envio, cursor)
            registrar_detalhes(contexto["id_conversa"], envio["detalhes"], cursor)
            return resultado

    raise ValueError(
        f"Efeito não implementado para etapa={etapa}, evento={evento}, destino={destino}."
    )


def aplicar_efeito_contato(ctx,envio,cursor):
    from core.repositories.atendimento import identidade_cliente as ident
    from core.repositories.atendimento import solicitacao_contato as repositorio
    conversa = ctx["id_conversa"]
    operacao = envio["operacao_contato"]
    uid = envio.get("bsuid_contato")
    if operacao == "abrir":
        if envio["motivo_contato"] == "reconfirmacao":
            from core.repositories.atendimento.fallback_contato import concluir_reservas
            concluir_reservas(conversa,cursor)
        repositorio.abrir_solicitacao(conversa,envio["motivo_contato"],envio["id_etapa_resultante"],
                                      uid,envio["id_hash_msg_bot"],cursor)
    elif operacao == "repetir":
        repositorio.repetir_solicitacao(conversa,uid,envio["id_hash_msg_bot"],cursor)
    elif operacao == "confirmar":
        solicitacao = repositorio.ler_solicitacao_para_confirmar(conversa, uid, cursor)
        if not solicitacao:
            raise ValueError("Solicitação já encerrada")
        telefone = envio["telefone_provado"]
        ident.serializar_chave(f"wa:{telefone}",cursor)
        dono = ident.cliente_telefone(telefone, cursor)
        if envio.get("telefone_em_outro_cadastro") or dono not in (None, ctx["id_cliente"]):
            if solicitacao[1] != "cadastro":
                raise ValueError("O telefone de reconfirmação pertence a outro cadastro.")
            from core.repositories.atendimento.conciliacao_cliente import guardar_telefone_compartilhado
            guardar_telefone_compartilhado(conversa, telefone, cursor)
        else:
            ident.definir_telefone(ctx["id_cliente"], telefone, cursor)
        ident.alias_confirmado(ctx["id_central"],uid,cursor)
        repositorio.encerrar_solicitacao(conversa,cursor)
    elif operacao=="encerrar":
        repositorio.encerrar_solicitacao(conversa,cursor)
```

## 43. `workers/worker_flow/transacoes/finalizacao_fila.py` (alterar)

```python
import logging

from core.cache.runtime.cache_conversas_bloqueadas import (
    registrar_bloqueio_conversa_cache,
)
from core.cache.runtime.cache_cliente import remover_cliente_cache, salvar_cliente_cache
from core.logging_config import short_value
from core.repositories.atendimento.fila import marcar_mensagem_como_enviada
from workers.worker_flow.transacoes.encerramento_atendimento import (
    aplicar_encerramento_se_necessario,
)


logger = logging.getLogger("worker.support")


def finalizar_mensagem_processada(
    mensagem,
    contexto_banco,
    lock_version,
    cursor,
    contexto_final=None,
):
    contexto_conversa = contexto_banco["conversa"]
    id_conversa = contexto_conversa["id_conversa"]
    contexto_final = contexto_final or {}

    resultado_encerramento = aplicar_encerramento_se_necessario(
        id_conversa,
        contexto_final.get("intencao_encerramento"),
        cursor,
    )

    marcar_mensagem_como_enviada(mensagem["id_mensagem"], cursor)

    conciliacao = (contexto_final.get("efeitos_transicao") or {}).get("cache_conciliacao")
    if conciliacao:
        resultado_encerramento["cache_conciliacao"] = conciliacao
    return resultado_encerramento


def registrar_cache_bloqueio_apos_commit(
    mensagem,
    resultado_encerramento,
):
    """Publica o vínculo reconciliado ou o bloqueio somente depois do commit da fila."""
    if conciliacao := resultado_encerramento.get("cache_conciliacao"):
        for telefone in conciliacao["telefones_antigos"]:
            remover_cliente_cache(telefone)
        for central, uid in conciliacao["aliases_antigos"]:
            remover_cliente_cache(uid, id_central=central, tipo="bsuid")
        salvar_cliente_cache(conciliacao["telefone"], conciliacao["cliente"])
        if conciliacao["uid"]:
            salvar_cliente_cache(conciliacao["uid"], conciliacao["cliente"],
                                 id_central=conciliacao["central"], tipo="bsuid")
    if not resultado_encerramento.get("atendimento_encerrado"):
        return False

    bloqueio_dias = int(
        resultado_encerramento.get("bloqueio_dias") or 0
    )

    if bloqueio_dias <= 0:
        return False

    registrado = False
    for chave in dict.fromkeys((mensagem.get("cliente_telefone"),mensagem.get("user_id_origem"))):
        if chave:
            gravado = registrar_bloqueio_conversa_cache(chave,mensagem["id_phone_unidade"],
                                                         resultado_encerramento["finalizou_em"],bloqueio_dias)
            registrado = registrado or gravado

    logger.info(
        "cache_bloqueio_pos_commit | acao=registrar cliente=%s "
        "phone_number_id=%s bloqueio_dias=%s registrado=%s",
        short_value(mensagem["cliente_telefone"]),
        short_value(mensagem["id_phone_unidade"]),
        bloqueio_dias,
        registrado,
    )
    return registrado
```

## 44. `workers/worker_flow/valida_banco.py` (alterar)

```python
"""Resolve cliente, central e conversa sem enviar mensagens."""
from core.cache.runtime.cache_cliente import buscar_cliente_cache
from core.cache.cache_unidade import obter_id_unidade_redis_ou_plsql
from core.repositories.atendimento.identidade_cliente import cliente_telefone
from core.repositories.atendimento.clientes import inserindo_em_cliente_caso_seja_novo
from core.repositories.atendimento.chats import garantir_chat_para_atendimento
from core.repositories.atendimento.conversas import buscar_estado_conversa, inserindo_em_conversa_caso_seja_nova


from core.repositories.atendimento.fila import ler_identidade_fila


def valida_cliente(telefone, cursor):
    id_cliente = buscar_cliente_cache(telefone)
    # Uma fila legada pode sobreviver à troca de titular do telefone.
    if id_cliente and cliente_telefone(telefone, cursor) == id_cliente:
        return id_cliente, False, False
    id_cliente, inserido = inserindo_em_cliente_caso_seja_novo(telefone, cursor)
    return id_cliente, inserido, True


def validar_banco_mensagem(mensagem, cursor):
    cadastro, uid, estrutura, central_da_fila = ler_identidade_fila(mensagem["id_mensagem"], cursor)
    id_central = obter_id_unidade_redis_ou_plsql(
        mensagem["id_phone_unidade"], cursor, central_da_fila=central_da_fila,
    )
    mensagem.update(user_id_origem=uid, estrutura_compartilhamento=estrutura)
    if cadastro:
        id_cliente, inserido, pendente = cadastro, False, True
    else:
        id_cliente, inserido, pendente = valida_cliente(mensagem["cliente_telefone"], cursor)
    # A linha do chat serializa a decisão abrir/retomar, mesmo antes do lock da conversa.
    garantir_chat_para_atendimento(id_cliente, id_central, cursor)
    conversa = buscar_estado_conversa(id_cliente, id_central, cursor)
    if not conversa or conversa["estado"] == "liberada":
        inserindo_em_conversa_caso_seja_nova(id_cliente, id_central, cursor)
        conversa = buscar_estado_conversa(id_cliente, id_central, cursor)
    return {
        "id_unidade": id_central, "id_central": id_central, "id_cliente": id_cliente,
        "cliente_telefone": mensagem["cliente_telefone"], "id_phone_unidade": mensagem["id_phone_unidade"],
        "bsuid_origem": uid, "cliente_inserido": inserido, "cliente_cache_pendente": pendente, "conversa": conversa,
    }
```

## 45. `workers/worker_flow/valida_historico.py` (alterar)

```python
"""Carrega a etapa original da entrada e a resposta já confirmada, se houver."""
from core.repositories.atendimento.conversas import atualizar_conversa_mensagem_cliente
from core.repositories.atendimento.historico import inserir_historico_mensagem_cliente, buscar_resposta_bot_por_mensagem_cliente
from core.repositories.fluxo.transicoes import listar_transicoes_permitidas
from core.repositories.fluxo.contextos.pos_venda import buscar_contexto_pos_venda


def valida_historico(mensagem, contexto_banco, cursor):
    conversa = contexto_banco["conversa"]
    id_conversa = conversa["id_conversa"]
    id_hist, recebido, etapa, inserido = inserir_historico_mensagem_cliente(
        mensagem, id_conversa, conversa["id_etapa_atual"], cursor)
    resposta = buscar_resposta_bot_por_mensagem_cliente(id_conversa, mensagem["id_mensagem"], mensagem["id_hash"], cursor)
    if inserido and not resposta:
        atualizar_conversa_mensagem_cliente(id_conversa, recebido, cursor)
    contexto_pos_venda = buscar_contexto_pos_venda(id_conversa, cursor)
    return {
        **contexto_banco, "id_conversa": id_conversa, "id_etapa_atual": conversa["id_etapa_atual"],
        "id_etapa_cliente": etapa, "id_etapa_origem_transicao": etapa, "id_etapa_resposta": etapa,
        "mensagem_cliente_inserida": inserido, "retry_count": mensagem["retry_count"],
        "turnos_sem_avanco": conversa["turnos_sem_avanco"],
        "lock_version": conversa["lock_version"],
        "transicoes_permitidas": listar_transicoes_permitidas(etapa, cursor),
        "resposta_bot_para_mensagem_atual": resposta,
        **contexto_pos_venda,
        "telefone_compartilhado_apto": (mensagem.get("estrutura_compartilhamento") or {}).get("_telefone_verificado"),
        "mensagem_cliente_atual": {
            **mensagem, "id_mensagem": id_hist, "id_mensagem_fila": mensagem["id_mensagem"],
            "id_hash_msg": mensagem["id_hash"], "id_etapa": etapa, "received_data_hora": recebido,
        },
    }
```

## 46. `tests/test_abertura_digitacao_pos_venda.py` (alterar)

```python
"""Abertura sem etapa artificial e indicador compartilhado, sem HTTP real."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.integrations.whatsapp.pywa_functions.cliente import antes_do_primeiro_envio
from core.integrations.whatsapp.pywa_functions.digitacao import indicar_digitacao
from workers.worker_flow.response_flow.flow_sender import flow_sender
from tests.test_etapa1_pos_venda import contexto, ENV
from tests.test_etapa2_pos_venda import contexto_cpf


class AberturaDigitacaoTests(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.ordem = []
        def enviado(**kwargs):
            self.ordem.append("resposta")
            return SimpleNamespace(id="wamid.simulado")
        self.sdk.send_message.side_effect = enviado
        self.sdk.send_carousel.side_effect = enviado
        for p in (patch.dict(os.environ, ENV),
                  patch("core.integrations.whatsapp.pywa_functions.cliente.WhatsAppCentral",
                        return_value=self.sdk)):
            p.start()
            self.addCleanup(p.stop)

    def processar(self, ctx):
        with antes_do_primeiro_envio(lambda: self.ordem.append("digitando")):
            return flow_sender(ctx)

    def test_digitacao_precede_saudacao_repeticao_avanco_e_encaminhamento(self):
        casos = [
            contexto(apresentacao=True, tipo="audio", texto=None),
            contexto(texto="123"),
            contexto(texto="João da Silva"),
            contexto_cpf("123"),
            contexto_cpf("01234567890"),
            contexto(tipo="audio", texto=None),
            contexto_cpf("humano"),
            contexto(turnos=3),
        ]
        for ctx in casos:
            with self.subTest(etapa=ctx["id_etapa_atual"], texto=ctx["mensagem_cliente_atual"]["conteudo_texto"]):
                self.ordem.clear()
                self.processar(ctx)
                self.assertEqual(self.ordem, ["digitando", "resposta"])

    def test_nome_coletado_sempre_pede_cpf_mesmo_com_cadastro_antigo(self):
        ctx = contexto(texto="João da Silva")
        ctx["cadastro"] = {"cpf_titular": "01234567890"}
        envio = self.processar(ctx)
        self.assertEqual(envio["id_etapa_resultante"], 2)
        self.assertIn("CPF do titular", envio["mensagem_bot"])
        self.assertEqual(self.ordem, ["digitando", "resposta"])

    def test_replay_nao_digita_nem_envia(self):
        ctx = contexto()
        ctx["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 1, "id_hash_msg": "wamid.anterior", "interativo": {},
        }
        self.assertTrue(self.processar(ctx)["resposta_ja_existia"])
        self.assertEqual(self.ordem, [])

    def test_mapa_invalido_ou_configuracao_invalida_nao_disparam_digitacao(self):
        ctx = contexto(texto="João da Silva")
        ctx["transicoes_permitidas"] = {}
        with self.assertRaises(ValueError):
            self.processar(ctx)
        with patch.dict(os.environ, {"WHATSAPP_MIDIAS_BASE_URL": ""}):
            with self.assertRaises(ValueError):
                self.processar(contexto(tipo="audio", turnos=3))
        self.assertEqual(self.ordem, [])

    def test_falha_opcional_de_digitacao_nao_impede_a_resposta(self):
        self.sdk.indicate_typing.side_effect = RuntimeError("falha simulada")
        with patch("core.integrations.whatsapp.pywa_functions.digitacao.httpx.Client"):
            with antes_do_primeiro_envio(lambda: indicar_digitacao("999", "wamid.entrada")):
                envio = flow_sender(contexto(apresentacao=True))
        self.assertTrue(envio["enviou"])
        self.sdk.indicate_typing.assert_called_once()
        self.assertEqual(self.ordem, ["resposta"])

    def test_etapa11_nao_pode_voltar_a_saudacao(self):
        with self.assertRaises(NotImplementedError):
            self.processar(contexto(etapa=7, apresentacao=True))
        self.assertEqual(self.ordem, [])

    def test_escolha_de_produto_envia_assunto_com_digitacao(self):
        ctx = contexto(etapa=3, texto="Apenas móveis")
        ctx["transicoes_permitidas"]["produto_escolhido"] = 4
        envio = self.processar(ctx)
        self.assertEqual(envio["id_etapa_resultante"], 4)
        self.assertEqual(envio["produto"], "moveis")
        self.assertEqual(self.ordem, ["digitando", "resposta"])


if __name__ == "__main__":
    unittest.main()
```

## 47. `tests/test_etapa1_pos_venda.py` (alterar)

```python
"""Testes sem banco, Redis, requisições reais ou envio para pessoas."""
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.nome_titular import normalizar_nome_titular
from core.integrations.whatsapp.messages.etapa1_messages import (
    MENSAGEM_PADRAO_ETAPA1, MENSAGEM_NOME_INVALIDO,
)
from core.integrations.whatsapp.messages.encaminhamento_pos_venda import (
    MENSAGEM_SEM_NOTA,
)
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import montar_cartoes
from core.integrations.whatsapp.pywa_functions.cliente import antes_do_primeiro_envio, conta_wa
from core.cache.runtime import cache_conversas_bloqueadas as bloqueio
from workers.worker_flow.response_flow.flow_sender import flow_sender

ENV = {"WHATSAPP_MIDIAS_BASE_URL": "https://example.test/static/monitoramento/img/pos_venda"}
PATCH_TEXTO = "core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda.conta_wa"
PATCH_CARTOES = "core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda.conta_wa"


def contexto(etapa=1, texto="123", tipo="text", turnos=0, apresentacao=False):
    return {
        "apresentacao_pendente": apresentacao, "id_conversa": 12, "id_cliente": 13, "id_etapa_atual": etapa,
        "id_etapa_origem_transicao": etapa, "turnos_sem_avanco": turnos,
        "resposta_bot_para_mensagem_atual": None,
        "transicoes_permitidas": {
            "nome_valido_falta_cpf": 2,
            "humano_solicitado": 7, "limite_sem_avanco": 7,
        },
        "central": {"telefone_atacadao": "557592087803", "telefone_baratao": "557582467000",
                    "phone_number_id": "999", "messaging_account_id": "100", "waac_id": None},
        "cadastro": {},
        "mensagem_cliente_atual": {"tipo_mensagem": tipo, "conteudo_texto": texto,
                                  "cliente_telefone": "5511999990000", "id_phone_unidade": "999"},
    }


class Etapa1Tests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.texto")
        self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.carrossel")
        for destino in (PATCH_TEXTO, PATCH_CARTOES):
            patcher = patch(destino, return_value=self.wa)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_nomes_aceitos(self):
        for entrada, esperado in (
            ("Olá, eu me chamo Ana Maria da Silva.", "Ana Maria da Silva"),
            ("O nome dele é João-Pedro de Souza", "João-Pedro de Souza"),
            ("Eu sou a Ana Costa", "Ana Costa"),
            ("Nome do titular da compra é José dos Santos", "José dos Santos"),
            ("Meu nome é Maria Silva e quero falar do pedido", "Maria Silva"),
            ("João da silva.", "João da silva"),
            ("João-Pedro da Silva", "João-Pedro da Silva"),
            ("João-Pedro da Silva.", "João-Pedro da Silva"),
            ("  María  José da Conceição  ", "María José da Conceição"),
            ("Joa\u0303o da Silva", "João da Silva"),
        ):
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_nome_titular(entrada), esperado)

    def test_nomes_invalidos(self):
        for entrada in ("O nome dele é", "Eu me chamo Ana", "Eu sou de Salvador", "Ana de",
                        "Eu sou João2 Silva", "Quero falar do pedido", None, "", " ", "123", "João 123", "João @ Silva", "João da Silva!",
                        ".João Silva", "João. Silva", "João Silva..", "João - Pedro Silva",
                        "-João Silva", "João- Silva", "João -- Silva", "João Silva-",
                        "João 😊 Silva", "João O'Connor", "João Silva .", "João"):
            with self.subTest(entrada=entrada):
                self.assertIsNone(normalizar_nome_titular(entrada))

    def test_primeiro_contato_apresenta_regras_mesmo_com_midia_ou_humano(self):
        for tipo, texto in (("audio", None), ("image", None), ("text", "Quero um HUMANO"), ("text", "João da Silva")):
            envio = flow_sender(contexto(apresentacao=True, tipo=tipo, texto=texto, turnos=3))
            self.assertRegex(envio["mensagem_bot"], r"^(Bom dia|Boa tarde|Boa noite), eu sou o Theo")
            self.assertEqual(envio["mensagem_bot"].count("\n\n"), 2)
            self.assertIn("nome completo do titular",envio["mensagem_bot"])
            self.assertEqual(envio["id_etapa_resultante"], 1)
            self.assertNotIn("evento_transicao", envio)
        self.wa.send_carousel.assert_not_called()

    def test_tres_repeticoes_e_quarto_encaminhamento(self):
        for turnos in range(3):
            envio = flow_sender(contexto(turnos=turnos))
            self.assertEqual(envio["mensagem_bot"], MENSAGEM_NOME_INVALIDO)
            self.assertNotIn("evento_transicao", envio)
        envio = flow_sender(contexto(turnos=3))
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.assertEqual(envio["id_etapa_resultante"], 7)
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_SEM_NOTA)
        self.wa.send_carousel.assert_called_once()

    def test_nome_valido_avanca_para_cpf(self):
        envio = flow_sender(contexto(texto="João-Pedro da Silva.", turnos=2))
        self.assertEqual(envio["nome_titular"], "João-Pedro da Silva")
        self.assertEqual(envio["id_etapa_resultante"], 2)
        self.assertEqual(envio["evento_transicao"], "nome_valido_falta_cpf")

    def test_midia_repete_cada_pergunta_preservando_os_controles(self):
        for etapa in range(1, 7):
            for tipo in ("audio", "image", "video", "document", "sticker", "location", "contacts", "unknown"):
                with self.subTest(etapa=etapa, tipo=tipo):
                    envio = flow_sender(contexto(etapa=etapa, tipo=tipo, texto="Quero um humano"))
                    self.assertEqual(envio["id_etapa_resultante"], etapa)
                    self.assertEqual(envio["tipo_tratamento"], "midia_na_etapa")
                    self.assertIn("mensagens de texto", envio["mensagem_bot"])
                    self.assertNotIn("evento_transicao", envio)
                    if etapa in (3, 4, 5):
                        interativo = envio["interativo"]
                        self.assertEqual(interativo["body"]["text"], envio["mensagem_bot"])
                        self.assertEqual(interativo["type"], {3:"button", 4:"list", 5:"button"}[etapa])
        self.wa.send_carousel.assert_not_called()

    def test_quarto_erro_sem_nota_oferece_as_duas_redes(self):
        c = contexto(etapa=4, tipo="audio", texto=None, turnos=3)
        c["produto"] = "ambos"
        envio = flow_sender(c)
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_SEM_NOTA)

    def test_humano_em_qualquer_frase_sem_diferenciar_caixa(self):
        for texto in ("Humano", "Quero falar com um HUMANO, por favor", "tem atendimento humano?"):
            self.assertEqual(flow_sender(contexto(texto=texto))["evento_transicao"], "humano_solicitado")

    def test_aviso_de_avarias_depende_do_assunto_da_conversa(self):
        from core.integrations.whatsapp.messages.encaminhamento_pos_venda import AVISO_ASSISTENCIA, mensagem_de_contato
        for assunto in ("assistencia", "misto", "entrega", "montador", "outros", None):
            with self.subTest(assunto=assunto):
                texto = mensagem_de_contato("Selecione o setor.", assunto)
                self.assertEqual(AVISO_ASSISTENCIA in texto, assunto in ("assistencia", "misto"))

    def test_cartoes_ordem_destinos_e_imagens(self):
        cards = [c.to_dict(i) for i, c in enumerate(montar_cartoes(contexto()))]
        self.assertEqual(len(cards), 2)
        for i, (rotulo, numero, imagem) in enumerate((
            ("Pós-venda Atacadão", "557592087803", "estofados.png"),
            ("Pós-venda Baratão", "557582467000", "moveis.png"),
        )):
            card = cards[i]
            self.assertEqual(card["card_index"], i)
            self.assertNotIn("body", card)
            self.assertEqual(card["action"]["parameters"]["display_text"], rotulo)
            self.assertTrue(card["action"]["parameters"]["url"].startswith(f"https://wa.me/{numero}?text="))
            self.assertTrue(card["header"]["image"]["link"].endswith(imagem))
            self.assertNotIn("123", card["action"]["parameters"]["url"])

    def test_configuracao_incompleta_nao_envia_nem_inventa_destino(self):
        for base in ("", "http://example.test/img", "https://example.test/img?token=x"):
            with patch.dict(os.environ, {"WHATSAPP_MIDIAS_BASE_URL": base}):
                with self.assertRaises(ValueError):
                    flow_sender(contexto(tipo="audio", turnos=3))
        c = contexto(tipo="audio", turnos=3)
        c["central"]["telefone_atacadao"] = None
        with self.assertRaises(ValueError):
            flow_sender(c)
        self.wa.send_carousel.assert_not_called()

    def test_falha_meta_e_propagada_para_recuperacao_worker(self):
        self.wa.send_carousel.side_effect = RuntimeError("falha simulada")
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto(tipo="audio", turnos=3))
        self.wa.send_message.assert_not_called()

    def test_resposta_sem_wamid_nao_e_considerada_enviada(self):
        self.wa.send_carousel.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto(texto="humano"))

    def test_replay_nao_envia_nem_reclassifica(self):
        c = contexto(etapa=10)
        c["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 10, "id_hash_msg": "wamid.confirmado",
            "interativo": {"_fluxo": {"evento": "limite_sem_avanco"}},
        }
        with patch.dict(os.environ, {"WHATSAPP_MIDIAS_BASE_URL": ""}):
            envio = flow_sender(c)
        self.assertTrue(envio["resposta_ja_existia"])
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.wa.send_message.assert_not_called()
        self.wa.send_carousel.assert_not_called()

    def test_mapa_invalido_impede_envio(self):
        c = contexto(tipo="audio", turnos=3)
        c["transicoes_permitidas"]["limite_sem_avanco"] = 8
        with self.assertRaises(ValueError):
            flow_sender(c)
        self.wa.send_carousel.assert_not_called()

    def test_etapas_antigas_nao_sao_reutilizadas_por_engano(self):
        with self.assertRaises(NotImplementedError):
            flow_sender(contexto(etapa=8))
        self.wa.send_message.assert_not_called()


class CacheBloqueioTests(unittest.TestCase):
    def test_ttl_usa_data_confirmada_nao_renova_noventa_dias(self):
        fim = datetime.now(timezone.utc) - timedelta(days=10)
        ttl = bloqueio._calcular_ttl(fim, 90)
        self.assertTrue(80 * 86400 - 2 <= ttl <= 80 * 86400)
        self.assertLessEqual(bloqueio._calcular_ttl(fim - timedelta(days=81), 90), 0)
        self.assertEqual(bloqueio._calcular_ttl(None, 90), 0)

    def test_chave_separa_centrais(self):
        self.assertNotEqual(bloqueio._cache_key("5511999990000", "1"), bloqueio._cache_key("5511999990000", "2"))

    @patch.object(bloqueio, "_conversa_esta_bloqueada_banco_e_repara_cache", return_value=True)
    @patch.object(bloqueio, "get_redis_safe")
    def test_cache_vazio_consulta_banco(self, redis, fallback):
        redis.return_value.exists.return_value = False
        self.assertTrue(bloqueio.conversa_esta_bloqueada_cache("5511999990000", "1"))
        fallback.assert_called_once()

    @patch.object(bloqueio, "_conversa_esta_bloqueada_banco_e_repara_cache", return_value=True)
    @patch.object(bloqueio, "get_redis_safe", side_effect=ConnectionError("redis indisponível"))
    def test_cache_indisponivel_consulta_banco(self, redis, fallback):
        self.assertTrue(bloqueio.conversa_esta_bloqueada_cache("5511999990000", "1"))
        fallback.assert_called_once()

    @patch.object(bloqueio, "get_redis_safe")
    def test_hash_e_expiracao_atomicos(self, redis):
        self.assertTrue(bloqueio.registrar_bloqueio_conversa_cache(
            "5511999990000", "1", datetime.now(timezone.utc), 90))
        pipe = redis.return_value.pipeline
        pipe.assert_called_once_with(transaction=True)
        pipe.return_value.__enter__.return_value.expire.assert_called_once()
        pipe.return_value.__enter__.return_value.execute.assert_called_once()


class TransporteTests(unittest.TestCase):
    def test_carrossel_preserva_acao_antes_do_envio_uma_vez(self):
        with patch("core.integrations.whatsapp.pywa_functions.cliente.WhatsAppCentral") as sdk:
            acao = MagicMock()
            with antes_do_primeiro_envio(acao):
                wa = conta_wa("999", token="token-falso")
                wa.send_carousel(to="5511999990000", body="Contatos", cards=[])
                wa.send_message(to="5511999990000", text="Outro")
            acao.assert_called_once()
            sdk.return_value.send_carousel.assert_called_once()

    def test_serializacao_real_do_sdk_com_http_simulado(self):
        import httpx
        import json
        from pywa import WhatsApp
        capturados = []
        def responder(request):
            capturados.append(json.loads(request.content))
            return httpx.Response(200, json={"messaging_product": "whatsapp",
                "contacts": [{"input": "5511999990000", "wa_id": "5511999990000"}],
                "messages": [{"id": "wamid.simulado"}]})
        with patch.dict(os.environ, ENV), httpx.Client(transport=httpx.MockTransport(responder)) as session:
            wa = WhatsApp(phone_id="999", token="token-falso", session=session)
            resposta = wa.send_carousel(to="5511999990000", body=MENSAGEM_SEM_NOTA, cards=montar_cartoes(contexto()))
        self.assertEqual(resposta.id, "wamid.simulado")
        self.assertEqual(len(capturados), 1)
        payload = capturados[0]
        self.assertEqual(payload["interactive"]["type"], "carousel")
        self.assertEqual(len(payload["interactive"]["action"]["cards"]), 2)


if __name__ == "__main__":
    unittest.main()
```

## 48. `tests/test_etapa1_pos_venda_postgres.py` (alterar)

```python
"""Integração do ciclo real do worker em PostgreSQL LOCAL e descartável.

Defina BARATAO_TEST_DSN com dbname iniciado por baratao_ e host local.
Somente Meta, Redis e esperas são simulados. O teste recria o schema chatbot.
"""
import io
import logging
import os
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psycopg
from psycopg.conninfo import conninfo_to_dict
from workers.worker_flow.response_flow import flow_worker as runtime
from core.cache import cache_unidade
from core.repositories.fluxo.politicas import buscar_bloqueio_ativo_por_cliente_unidade
from core.repositories.atendimento.locks import proteger_conversa, LockConversaPerdido
from core.repositories.atendimento.conversas import tentar_lock_conversa, unlock_conversa
from tests.test_etapa1_pos_venda import ENV, PATCH_TEXTO, PATCH_CARTOES

ROOT = Path(__file__).resolve().parents[1]


class PararWorker(BaseException):
    pass


@unittest.skipUnless(os.getenv("BARATAO_TEST_DSN"), "Requer PostgreSQL local isolado.")
class WorkerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["BARATAO_TEST_DSN"]
        info = conninfo_to_dict(cls.dsn)
        if info.get("host") not in {"127.0.0.1", "localhost", "::1"} or not info.get("dbname", "").startswith("baratao_"):
            raise RuntimeError("Os testes recusam banco remoto ou sem prefixo baratao_.")
        cls.adm = psycopg.connect(cls.dsn, autocommit=True)
        cls.adm.execute("DROP SCHEMA IF EXISTS chatbot CASCADE")
        cls.adm.execute("CREATE SCHEMA chatbot")
        cls.adm.execute("CREATE TABLE chatbot.auth_user (id integer PRIMARY KEY)")
        cls.adm.execute((ROOT / "core/database/deploy_database/schema.sql").read_text(encoding="utf-8"))
        cls.adm.execute((ROOT / "core/database/deploy_database/catalogo.sql").read_text(encoding="utf-8"))
        cls.logging_anterior = logging.root.manager.disable
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        cls.adm.close()
        logging.disable(cls.logging_anterior)

    def setUp(self):
        self.adm.execute("TRUNCATE chatbot.central_pos_venda, chatbot.cliente RESTART IDENTITY CASCADE")
        self.carregar_catalogo("core/database/deploy_database/catalogo.sql")
        self.adm.execute("""
            INSERT INTO chatbot.central_pos_venda
                (nome, nome_agente, genero_agente, waba_id, phone_number_id, telefone, telefone_atacadao, telefone_baratao)
            VALUES ('Central QA', 'Theo', 'masculino', 'waba-falsa', '999', '551100000001', '557592087803', '557582467000'),
                   ('Outra QA', 'Theo', 'masculino', 'waba-falsa', '888', '551100000002', '557592087803', '557582467000');
        """)
        self.wa = MagicMock()
        self.n = 0
        def resposta(**kwargs):
            self.n += 1
            return SimpleNamespace(id=f"wamid.bot.{self.n}")
        self.wa.request_contact_info.side_effect = resposta
        self.wa.send_message.side_effect = resposta
        self.wa.send_carousel.side_effect = resposta
        self.cache = MagicMock()
        self.entrada = 0

    def carregar_catalogo(self, caminho):
        self.adm.execute("DELETE FROM chatbot.etapa_transicao")
        self.adm.execute("DELETE FROM chatbot.etapa")
        texto = (ROOT / caminho).read_text(encoding="utf-8")
        self.adm.execute(texto.split("INSERT INTO chatbot.cache_controle")[0])

    def test_migracao_sequencial_preserva_atendimento_retomada_e_bloqueio(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261125.sql")
        self.preparar()
        self.adm.execute("""
            UPDATE chatbot.conversa SET id_etapa_atual=6, turnos_sem_avanco=2;
            UPDATE chatbot.historico_mensagens SET id_etapa=9 WHERE quem_enviou='bot';
            INSERT INTO chatbot.solicitacao_contato
                (id_conversa,motivo,id_etapa_retomada,bsuid_destino,wamid_solicitacao,wamids_aceitos)
            VALUES (1,'reconfirmacao',6,'bsuid-teste','wamid-contato',ARRAY['wamid-contato']);
            INSERT INTO chatbot.conversa
                (id_chat,id_central,id_etapa_atual,status_ativa,finalizou_em,motivo_encerramento)
            VALUES (1,1,11,false,now(),'encaminhamento');
        """)
        snapshot = """
            SELECT c.id_conversa,e.nome_etapa,c.finalizou_em,c.turnos_sem_avanco,
                   c.lock_version,c.status_ativa,c.motivo_encerramento
            FROM chatbot.conversa c JOIN chatbot.etapa e ON e.id_etapa=c.id_etapa_atual
            ORDER BY c.id_conversa
        """
        historico = """
            SELECT h.id_hash_msg,e.nome_etapa,h.interativo FROM chatbot.historico_mensagens h
            JOIN chatbot.etapa e USING (id_etapa) ORDER BY h.id_mensagem
        """
        mapa = """
            SELECT t.id_transicao,o.nome_etapa,t.evento,d.nome_etapa FROM chatbot.etapa_transicao t
            JOIN chatbot.etapa o ON o.id_etapa=t.id_etapa_origem
            JOIN chatbot.etapa d ON d.id_etapa=t.id_etapa_destino ORDER BY t.id_transicao
        """
        consultas = (snapshot, historico, mapa)
        antes = [self.adm.execute(q).fetchall() for q in consultas]
        script = (ROOT / "deploy/migrations/20261126_pendencias_baratao_etapas_sequenciais.sql").read_text(encoding="utf-8")
        for _ in range(2):
            self.adm.execute(script)
            self.assertEqual([self.adm.execute(q).fetchall() for q in consultas], antes)
            self.assertEqual(self.adm.execute("SELECT id_etapa_retomada FROM chatbot.solicitacao_contato").fetchone(), (5,))
            self.assertEqual(self.adm.execute("SELECT id_etapa_atual FROM chatbot.conversa ORDER BY id_conversa").fetchall(), [(5,), (9,)])
            self.assertEqual(self.adm.execute("SELECT id_etapa FROM chatbot.etapa ORDER BY id_etapa").fetchall(),
                             [(i,) for i in range(1, 10)])

    def test_politicas_sequenciais_de_visita_detalhes_e_encaminhamento(self):
        from workers.worker_flow.transacoes.encerramento_atendimento import resolver_intencao_encerramento
        with self.adm.cursor() as cursor:
            def intencao(etapa, evento):
                return resolver_intencao_encerramento(
                    {}, {"id_etapa_resultante": etapa, "evento_transicao": evento}, cursor)
            self.assertIsNone(intencao(5, "assunto_escolhido"))
            self.assertIsNone(intencao(6, "pedidos_assistencia"))
            self.assertEqual(intencao(7, "humano_solicitado"),
                             {"motivo_encerramento": "encaminhamento_humano", "bloqueio_dias": 90})

    def migrar_catalogo(self):
        self.adm.execute((ROOT / "deploy/migrations/20261122_etapas_produto_encerramento.sql").read_text(encoding="utf-8"))

    def fila(self, texto, tipo="text", central=1):
        self.entrada += 1
        return self.adm.execute("""
            INSERT INTO chatbot.fila_mensagens
                (id_central, cliente_telefone, id_hash_msg, received_data_hora, tipo_mensagem, conteudo_texto)
            VALUES (%s, '5511999990000', %s, clock_timestamp(), %s, %s) RETURNING id_mensagem;
        """, (central, f"wamid.cliente.{self.entrada}", tipo, texto)).fetchone()[0]

    def ciclo(self, *, redis_centrais=None, **patches):
        conn = psycopg.connect(self.dsn)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, ENV))
            stack.enter_context(patch.object(runtime, "get_conn", side_effect=[conn, PararWorker()]))
            stack.enter_context(patch.object(runtime, "confirmar_cache_cliente_se_pendente"))
            stack.enter_context(patch.object(runtime, "indicar_digitacao"))
            stack.enter_context(patch.object(runtime, "registrar_cache_bloqueio_apos_commit", self.cache))
            stack.enter_context(patch("workers.worker_flow.valida_banco.buscar_cliente_cache", return_value=None))
            # O caminho de admissão do worker é real. Só o servidor Redis é simulado.
            if redis_centrais is None:
                redis_centrais = MagicMock()
                redis_centrais.get.return_value = "2"
                redis_centrais.hlen.return_value = 2
                redis_centrais.hget.side_effect = lambda chave, phone: {"999": "1", "888": "2"}.get(phone)
            stack.enter_context(patch.object(cache_unidade, "get_redis_safe", return_value=redis_centrais))
            stack.enter_context(patch.object(cache_unidade, "_deve_conferir_versao", return_value=False))
            stack.enter_context(patch("workers.worker_flow.tratar_bloqueio.registrar_bloqueio_conversa_cache"))
            stack.enter_context(patch("workers.tratamento_erros_externos.erro_generico.time.sleep"))
            stack.enter_context(patch("core.integrations.whatsapp.pywa_functions.pywa_senders.compartilhamento_contato.conta_wa",return_value=self.wa))
            stack.enter_context(patch(PATCH_TEXTO, return_value=self.wa))
            stack.enter_context(patch(PATCH_CARTOES, return_value=self.wa))
            for nome, efeito in patches.items():
                stack.enter_context(patch.object(runtime, nome, side_effect=efeito))
            with redirect_stdout(io.StringIO()), self.assertRaises(PararWorker):
                runtime.worker_flow()

    def verificar_reparo_da_central(self, valor_cache, falha_publicacao=False):
        item = self.fila("Oi")
        redis = MagicMock()
        redis.get.return_value = "2"
        redis.hlen.return_value = 2
        redis.hget.return_value = valor_cache
        pipe = redis.pipeline.return_value.__enter__.return_value
        if falha_publicacao:
            pipe.execute.side_effect = ConnectionError("Redis indisponível no reparo")
        self.ciclo(redis_centrais=redis)
        pipe.hset.assert_called_once_with(cache_unidade.CACHE_TEMP_KEY, mapping={"999": 1, "888": 2})
        pipe.execute.assert_called_once()
        self.assertEqual(self.adm.execute(
            "SELECT status FROM chatbot.fila_mensagens WHERE id_mensagem=%s", (item,)
        ).fetchone(), ("sent",))
        self.assertEqual(self.adm.execute("SELECT id_central FROM chatbot.chat").fetchall(), [(1,)])
        self.wa.send_message.assert_called_once()

    def test_central_ausente_em_cache_integro_repara_e_envia(self):
        self.verificar_reparo_da_central(None)

    def test_id_cache_de_outra_central_confere_com_a_fila(self):
        self.verificar_reparo_da_central("2")

    def test_reparo_indisponivel_envia_pela_central_confirmada(self):
        self.verificar_reparo_da_central(None, falha_publicacao=True)

    def conversa(self):
        return self.adm.execute("""
            SELECT id_etapa_atual, turnos_sem_avanco, status_ativa, motivo_encerramento, finalizou_em
            FROM chatbot.conversa ORDER BY id_conversa LIMIT 1;
        """).fetchone()

    def entrada_privada(self, texto=None, *, cartao=False, tipo="text", bsuid=None, telefone=None, assinada=True, envelope_wa=None):
        import json
        from datetime import datetime, timezone
        from callback.webhook.services.populating_fila_mensagens import preparar_dados_fila,povoando_fila
        nome="CONTACT_INFO" if cartao else "BSUID_USERNAME"
        data=json.loads((ROOT/"payloads"/(nome+".json")).read_text(encoding="utf-8-sig"))
        self.entrada += 1
        entry=data["entry"][0]
        entry["id"]="waba-falsa"
        valor=entry["changes"][0]["value"]
        valor["metadata"]["phone_number_id"]="999"
        msg=valor["messages"][0]
        if bsuid:
            msg["from_user_id"] = bsuid
            valor["contacts"][0]["user_id"] = bsuid
        if envelope_wa:
            msg["from"] = envelope_wa
        if cartao and telefone:
            msg["contacts"][0]["phones"] = [{"wa_id": telefone, "phone": telefone, "type": "CELL"}]
        msg["id"]=f"wamid.privado.{self.entrada}"
        if not cartao:
            msg.update(type=tipo,text={"body":texto or ""})
        dados=preparar_dados_fila(data)["dados"]
        # Representa nova entrada posterior ao turno anterior com precisão de microssegundos.
        dados["received_data_hora"]=datetime.now(timezone.utc)
        dados["assinatura_verificada"] = assinada
        with self.adm.transaction(), self.adm.cursor() as cursor:
            return povoando_fila(dados,cursor)

    def postar_webhook(self, wa, uid, username, wamid, *, assinatura_valida=True):
        import hashlib
        import hmac
        import json
        import time
        from callback.webhook.services import post_flow, flood_guard, bloqueio_meta_guard, meta_signature

        data = json.loads((ROOT / "payloads/BSUID_USERNAME.json").read_text(encoding="utf-8-sig"))
        entry = data["entry"][0]
        entry["id"] = "waba-falsa"
        valor = entry["changes"][0]["value"]
        valor["metadata"]["phone_number_id"] = "999"
        msg = valor["messages"][0]
        msg.pop("from_user_id")
        contato = {"profile": {"username": username} if username else {}}
        valor["contacts"] = [contato]
        if wa:
            msg["from"] = contato["wa_id"] = wa
        if uid:
            msg["from_user_id"] = contato["user_id"] = uid
        msg.update(id=wamid, timestamp=str(int(time.time())))
        corpo = json.dumps(data).encode()
        assinatura = hmac.new(b"ensaio-local", corpo, hashlib.sha256).hexdigest()
        req = SimpleNamespace(method="POST", path="/webhook", body=corpo, content_type="application/json",
                              headers={"X-Hub-Signature-256": "sha256=" + (assinatura if assinatura_valida else "x")})
        config = SimpleNamespace(META_APP_SECRET="ensaio-local", META_WEBHOOK_SIGNATURE_REQUIRED=True,
                                 WEBHOOK_MAX_BODY_BYTES=100000, DEFAULT_CHARSET="utf-8")
        with ExitStack() as stack:
            for modulo in (post_flow, bloqueio_meta_guard, flood_guard):
                stack.enter_context(patch.object(modulo, "get_conn", side_effect=lambda **kw: psycopg.connect(self.dsn)))
            for modulo in (post_flow, meta_signature):
                stack.enter_context(patch.object(modulo, "settings", config))
            stack.enter_context(patch("django.http.response.settings", config))
            stack.enter_context(patch.object(post_flow, "unidade_esta_ativa", return_value=True))
            stack.enter_context(patch.object(post_flow, "conversa_esta_bloqueada_cache", return_value=False))
            stack.enter_context(patch.object(flood_guard, "avaliar_flood_redis", return_value={"redis_ok": False}))
            with redirect_stdout(io.StringIO()):
                return post_flow.responder_post_webhook(req)

    def test_log_do_webhook_e_do_worker_seguem_a_mesma_linha_apos_commit(self):
        import re
        from callback.webhook.services import post_flow

        eventos = []
        def observar(formato, *args):
            texto = formato % args
            evento = texto.partition(" |")[0]
            if evento in {"fila_insert_ok", "mensagem_processando", "mensagem_processada"}:
                chave = int(re.search(r"\bid_mensagem=(\d+)", texto)[1])
                # Outra conexão só vê a mudança se o commit já aconteceu.
                linha = self.adm.execute("SELECT status FROM chatbot.fila_mensagens WHERE id_mensagem=%s",
                                        (chave,)).fetchone()
                eventos.append((evento, chave, linha))

        with patch.object(post_flow.fila_logger, "info", side_effect=observar), \
             patch.object(runtime.logger, "info", side_effect=observar):
            self.postar_webhook("5511999990000", None, None, "wamid.teste.log")
            self.ciclo()
            self.postar_webhook("5511999990000", None, None, "wamid.teste.log")
        chave, = self.adm.execute("SELECT id_mensagem FROM chatbot.fila_mensagens").fetchone()
        self.assertEqual(eventos, [
            ("fila_insert_ok", chave, ("pending",)),
            ("mensagem_processando", chave, ("processing",)),
            ("mensagem_processada", chave, ("sent",)),
        ])

    def test_recibo_failed_sem_rota_registra_codigo_sem_conteudo_do_cliente(self):
        from callback.webhook.services import post_flow
        from core.logging_config import referencia_wamid

        data = {"entry": [{"id": "waba-falsa", "changes": [{"value": {"metadata": {"phone_number_id": "999"}}}]}]}
        status = {"id": "wamid.resposta.privada", "errors": [{"code": 131026, "message": "texto privado"}]}
        with patch.object(post_flow, "get_conn", side_effect=lambda **kw: psycopg.connect(self.dsn)), \
             patch.object(post_flow.logger, "warning") as aviso:
            post_flow._registrar_falha_entrega(data, status)
        formato, *args = aviso.call_args.args
        texto = formato % tuple(args)
        self.assertIn("codigos_meta=131026", texto)
        self.assertIn("recuperacao=nao_aplicavel", texto)
        self.assertIn("ref_envio=" + referencia_wamid(status["id"]), texto)
        self.assertNotIn("texto privado", texto)
        self.assertNotIn(status["id"], texto)

    def test_oito_combinacoes_do_webhook_assinado_ate_o_primeiro_envio(self):
        from itertools import product
        for n, (tem_wa, tem_uid, tem_username) in enumerate(product((False, True), repeat=3)):
            wa = f"551199990000{n}" if tem_wa else None
            uid = f"BR.1000{n}" if tem_uid else None
            username = f"cliente{n}" if tem_username else None
            wamid = f"wamid.matriz.{n}"
            with self.subTest(wa=tem_wa, uid=tem_uid, username=tem_username):
                self.assertEqual(self.postar_webhook(wa,uid,username,wamid,assinatura_valida=False).status_code,403)
                resposta = self.postar_webhook(wa, uid, username, wamid)
                self.assertEqual(resposta.status_code, 200)
                fila = self.adm.execute("SELECT id_cliente FROM chatbot.fila_mensagens WHERE id_hash_msg=%s",(wamid,)).fetchone()
                if not (wa or uid):
                    self.assertIsNone(fila)
                    continue
                self.assertIsNotNone(fila)
                self.assertEqual(self.postar_webhook(wa,uid,username,wamid).status_code,200)
                self.ciclo()
                self.assertEqual(self.wa.send_message.call_args.kwargs["to"],wa or uid)
                self.assertIn("nome completo",self.wa.send_message.call_args.kwargs["text"])
                self.assertEqual(self.adm.execute("SELECT waid_telefone,username FROM chatbot.cliente WHERE id_cliente=%s",fila).fetchone(), (wa,username))
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.fila_mensagens").fetchone()[0],6)

    def test_turno_aberto_respondido_aceita_so_a_proxima_mensagem_e_o_replay_nao_duplica(self):
        wa, uid = "5511900000011", "BR.ABC123"
        self.postar_webhook(wa,uid,None,"wamid.primeira")
        self.postar_webhook(None,uid,None,"wamid.enquanto_pendente")
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.fila_mensagens").fetchone()[0],1)
        self.ciclo()
        # Queda após confirmar a resposta e antes de ACK na fila.
        self.adm.execute("UPDATE chatbot.fila_mensagens SET status='processing', processing_started_at=now()")
        self.postar_webhook(None,uid,None,"wamid.segunda")
        self.postar_webhook(wa,None,None,"wamid.segunda")
        self.postar_webhook(wa,None,None,"wamid.terceira")
        self.assertEqual(self.adm.execute("SELECT id_hash_msg FROM chatbot.fila_mensagens ORDER BY id_mensagem").fetchall(),
                         [("wamid.primeira",),("wamid.segunda",)])

    def test_flood_alternando_rotas_marca_banco_e_solicita_bloqueio_remoto(self):
        from callback.webhook.services import flood_guard, bloqueio_meta_guard
        wa, uid = "5511900000011", "BR.ABC123"
        with patch.object(flood_guard, "REGRAS_FLOOD", ({"nome":"rajada_curta","limite":15,"janela_segundos":5},)), patch.object(
                flood_guard, "bloquear_usuario_meta") as bloquear, patch.object(
                bloqueio_meta_guard, "bloquear_usuario_meta") as reconfirmar:
            self.postar_webhook(wa,uid,None,"wamid.flood0")
            for n in range(1,14):
                self.postar_webhook(wa if n%2 else None,None if n%2 else uid,None,f"wamid.flood{n}")
            # Simula a rajada de 5 s mesmo em máquinas onde abrir as conexões do teste demora mais.
            self.adm.execute("UPDATE chatbot.webhook_flood_evento SET received_at=now() WHERE id_central=1")
            self.postar_webhook(None,uid,None,"wamid.flood14")
            bloquear.assert_called_once()
            self.assertEqual(self.adm.execute("SELECT wa_id_cliente FROM chatbot.cliente_bloqueado_meta").fetchall(),[(uid,)])
            self.postar_webhook(wa,None,None,"wamid.apos")
            reconfirmar.assert_called_once()
            self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.fila_mensagens").fetchone()[0],1)

    def test_quatro_midias_com_contato_pendente_encaminham_no_quarto_turno(self):
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        for n in range(1, 4):
            self.entrada_privada(tipo="audio")
            self.ciclo()
            self.assertEqual(self.adm.execute("SELECT erros_cliente FROM chatbot.solicitacao_contato").fetchone(), (n,))
            self.assertIn("mensagens de texto", self.wa.request_contact_info.call_args.kwargs["text"])
        self.entrada_privada(tipo="image")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.wa.send_carousel.assert_called_once()

    def test_so_bsuid_nome_compartilhamento_cpf(self):
        for texto in ("Oi","Ana Maria da Silva"):
            self.assertEqual(self.entrada_privada(texto)["status"],"inserted")
            self.ciclo()
        self.wa.request_contact_info.assert_called_once()
        self.assertIn("Ana,",self.wa.request_contact_info.call_args.kwargs["text"])
        for tipo in ("audio", "image", "text"):
            self.entrada_privada("ainda nao" if tipo == "text" else None, tipo=tipo)
            self.ciclo()
        self.assertEqual(self.adm.execute("SELECT erros_cliente FROM chatbot.solicitacao_contato").fetchone()[0],3)
        self.assertEqual(self.entrada_privada(cartao=True)["status"],"inserted")
        self.ciclo()
        self.assertEqual(self.conversa()[0],2)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.solicitacao_contato").fetchone()[0],0)
        self.assertEqual(self.adm.execute("SELECT nome_titular,waid_telefone FROM chatbot.cliente").fetchone(),
                         ("Ana Maria da Silva","5575999999999"))
        self.assertEqual(self.wa.send_message.call_args.kwargs["to"],"5575999999999")
        self.assertIn("CPF", self.wa.send_message.call_args.kwargs["text"])
        self.entrada_privada("12345678901")
        self.ciclo()
        self.assertEqual(self.conversa()[0],3)
        self.assertEqual(self.wa.send_message.call_args.kwargs["to"],"5575999999999")

    def test_troca_de_bsuid_reconfirma_telefone_e_preserva_a_conversa(self):
        from core.identidade_atendimento import rotacionar_bsuid

        antigo = "BR.1111111111111"
        novo = "BR.2222222222222"
        for texto in ("Oi", "Ana Maria"):
            self.entrada_privada(texto, bsuid=antigo)
            self.ciclo()
        self.entrada_privada(cartao=True, bsuid=antigo, telefone="5575988888888")
        self.ciclo()
        self.assertEqual(self.conversa()[0], 2)
        sistema = {"type": "user_changed_user_id", "previous_user_id": antigo, "user_id": novo}
        with self.adm.transaction(), self.adm.cursor() as cursor:
            self.assertTrue(rotacionar_bsuid(1, sistema, "wamid.mudanca", cursor))
            self.assertFalse(rotacionar_bsuid(1, sistema, "wamid.mudanca", cursor))
        self.entrada_privada("Oi", bsuid=novo)
        self.ciclo()
        self.assertEqual(self.wa.request_contact_info.call_args.kwargs["to"], novo)
        self.entrada_privada(cartao=True, bsuid=novo, telefone="5575977777777")
        self.ciclo()
        self.assertEqual(self.wa.send_message.call_args.kwargs["to"], "5575977777777")
        self.assertEqual(self.conversa()[0], 2)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.conversa").fetchone()[0], 1)
        self.assertEqual(self.adm.execute("SELECT waid_telefone FROM chatbot.cliente").fetchall(),
                         [("5575977777777",)])

    def test_so_bsuid_quarta_invalida_aplica_bloqueio(self):
        for texto in ("Oi","Ana Maria","x","x","x","x"):
            self.assertEqual(self.entrada_privada(texto)["status"],"inserted")
            self.ciclo()
        self.assertEqual(self.conversa()[:4],(7,0,False,"encaminhamento_sem_avanco"))
        self.assertEqual(self.entrada_privada("Oi")["reason"],"cliente_impedido")
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente_bloqueado_meta").fetchone()[0],0)

    def preparar(self):
        self.fila(None, "audio")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (1, 0, True))

    def test_username_em_recibo_correlacionado_e_reentrega_antiga(self):
        from datetime import datetime, timedelta, timezone
        from core.repositories.atendimento.identidade_cliente import atualizar_username_por_recibo
        self.entrada_privada("Oi", bsuid="BR.ABC123")
        self.ciclo()
        agora = datetime.now(timezone.utc) + timedelta(seconds=2)
        with self.adm.transaction(), self.adm.cursor() as cursor:
            for uid, wamid, nome, instante in (
                ("BR.ABC123", "wamid.bot.1", "vigente", agora),
                ("BR.ABC123", "wamid.bot.1", "antigo", agora-timedelta(seconds=1)),
                ("BR.OUTRO", "wamid.bot.1", "outra.pessoa", agora+timedelta(seconds=1)),
                ("BR.ABC123", "wamid.ignorado", "desconhecido", agora+timedelta(seconds=1)),
            ):
                atualizar_username_por_recibo(1,wamid,uid,None,nome,instante,cursor)
        self.assertEqual(self.adm.execute("SELECT username FROM chatbot.cliente").fetchone(),("vigente",))

    def test_suspensao_apos_reserva_preserva_mensagem_ate_reativar(self):
        id_mensagem = self.fila("Oi")
        verificar = runtime.exigir_unidade_habilitada_por_phone_id

        def desativar_apos_reserva(phone_id, cursor):
            self.adm.execute("UPDATE chatbot.central_pos_venda SET ativa=false WHERE phone_number_id=%s", (phone_id,))
            verificar(phone_id, cursor)

        self.ciclo(exigir_unidade_habilitada_por_phone_id=desativar_apos_reserva)
        fila = self.adm.execute(
            "SELECT status, retry_count, next_attempt_at > now() FROM chatbot.fila_mensagens WHERE id_mensagem=%s",
            (id_mensagem,),
        ).fetchone()
        self.assertEqual(fila, ("pending", 0, True))
        self.wa.send_message.assert_not_called()
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (id_mensagem,))
        self.assertIsNone(self.adm.execute("SELECT * FROM chatbot.dequeue_message()").fetchone())
        self.adm.execute("UPDATE chatbot.central_pos_venda SET ativa=true WHERE id_central=1")
        self.ciclo()
        self.wa.send_message.assert_called_once()
        self.assertEqual(self.conversa()[:3], (1, 0, True))

    def test_conversas_do_mesmo_cliente_usam_o_remetente_da_respectiva_central(self):
        from core.repositories.fluxo.contextos.pos_venda import buscar_contexto_pos_venda
        self.adm.execute("UPDATE chatbot.central_pos_venda SET waba_id='120', waac_id='771' WHERE id_central=2")
        esperados = {1: ("999", "waba-falsa", None), 2: ("888", "120", "771")}
        for id_central, esperado in esperados.items():
            self.fila("Olá", central=id_central)
            self.ciclo()
            id_conversa, = self.adm.execute(
                "SELECT id_conversa FROM chatbot.conversa WHERE id_central=%s", (id_central,)
            ).fetchone()
            with self.adm.cursor() as cursor:
                central = buscar_contexto_pos_venda(id_conversa, cursor)["central"]
            self.assertEqual((central["phone_number_id"], central["messaging_account_id"], central["waac_id"]), esperado)

    def test_saudacao_tres_repeticoes_e_quarto_encaminhamento(self):
        self.preparar()
        for n in range(1, 4):
            self.fila("123")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (1, n, True))
        self.fila("???")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.wa.send_carousel.assert_called_once()
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.historico_mensagens").fetchone()[0], 10)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.fila_mensagens WHERE status <> 'sent'").fetchone()[0], 0)
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)

    def test_nome_confirmado_avanca_e_zera_contador(self):
        self.preparar()
        self.fila("123")
        self.ciclo()
        self.fila("João-Pedro da Silva.")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (2, 0, True))
        self.assertEqual(self.adm.execute("SELECT nome_titular FROM chatbot.cliente").fetchone()[0], "João-Pedro da Silva")
        self.assertEqual(self.adm.execute("SELECT nome_titular FROM chatbot.atendimento_pos_venda").fetchone()[0], "João-Pedro da Silva")

    def test_humano_fecha_e_registra_os_contatos_realmente_enviados(self):
        self.preparar()
        self.fila("Quero falar com um HUMANO")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_humano"))
        self.assertEqual(self.adm.execute("""
            SELECT produto, encaminhado_atacadao, encaminhado_baratao, situacao FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, "557592087803", "557582467000", "Já encaminhado"))
        cur = self.adm.cursor()
        self.assertEqual(buscar_bloqueio_ativo_por_cliente_unidade("5511999990000", "999", cur).bloqueio_dias, 90)
        self.assertIsNone(buscar_bloqueio_ativo_por_cliente_unidade("5511999990000", "888", cur))
        envios = self.wa.send_message.call_count + self.wa.send_carousel.call_count
        self.fila("Olá novamente")
        self.ciclo()
        self.assertEqual(self.wa.send_message.call_count + self.wa.send_carousel.call_count, envios)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.conversa").fetchone()[0], 1)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente_bloqueado_meta").fetchone()[0], 0)

    def test_falha_meta_nao_conta_turno_nem_fecha(self):
        self.preparar()
        self.wa.send_carousel.side_effect = RuntimeError("falha de transporte simulada")
        item = self.fila("humano")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (1, 0, True))
        self.assertEqual(self.adm.execute("""
            SELECT count(*) FROM chatbot.historico_mensagens WHERE id_mensagem_fila=%s AND quem_enviou='bot'
        """, (item,)).fetchone()[0], 0)
        self.assertEqual(self.adm.execute("SELECT status FROM chatbot.fila_mensagens WHERE id_mensagem=%s", (item,)).fetchone()[0], "pending")

    def test_queda_apos_commit_da_resposta_recupera_fechamento_sem_reenviar(self):
        self.preparar()
        item = self.fila("humano")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda antes da finalização"))
        self.assertEqual(self.conversa()[:3], (7, 0, True))
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_humano"))
        self.wa.send_carousel.assert_called_once()

    def test_retry_de_repeticao_nao_incrementa_duas_vezes(self):
        self.preparar()
        item = self.fila("123")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após resposta"))
        self.assertEqual(self.conversa()[1], 1)
        contagem = self.wa.send_message.call_count
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[1], 1)
        self.assertEqual(self.wa.send_message.call_count, contagem)

    def test_queda_antes_commit_faz_rollback_de_nome_etapa_historico(self):
        self.preparar()
        original = runtime.atualizar_banco_com_contexto_final
        def persistir_e_falhar(*args):
            original(*args)
            raise RuntimeError("queda após alterações ainda sem commit")
        item = self.fila("João da Silva")
        self.ciclo(atualizar_banco_com_contexto_final=persistir_e_falhar)
        self.assertEqual(self.conversa()[:3], (1, 0, True))
        self.assertIsNone(self.adm.execute("SELECT nome_titular FROM chatbot.cliente").fetchone()[0])
        self.assertEqual(self.adm.execute("""
            SELECT count(*) FROM chatbot.historico_mensagens WHERE id_mensagem_fila=%s AND quem_enviou='bot'
        """, (item,)).fetchone()[0], 0)
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (2, 0, True))

    def test_apos_noventa_dias_mesmo_chat_pode_abrir_outra_conversa(self):
        self.preparar()
        self.fila("Humano")
        self.ciclo()
        self.adm.execute("""
            UPDATE chatbot.conversa SET iniciou_em=now()-interval '92 days',
                finalizou_em=now()-interval '91 days';
        """)
        self.assertIsNone(buscar_bloqueio_ativo_por_cliente_unidade("5511999990000", "999", self.adm.cursor()))
        self.fila("Bom dia")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.chat").fetchone()[0], 1)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.conversa").fetchone()[0], 2)

    def test_lock_antigo_nao_pode_persistir_ou_liberar_novo_dono(self):
        self.preparar()
        cur = self.adm.cursor()
        ok, versao = tentar_lock_conversa(1, cur)
        self.assertTrue(ok)
        self.assertFalse(tentar_lock_conversa(1, cur)[0])
        self.adm.execute("UPDATE chatbot.conversa SET processing_started_at=now()-interval '111 seconds' WHERE id_conversa=1")
        ok, nova = tentar_lock_conversa(1, cur)
        self.assertTrue(ok)
        self.assertGreater(nova, versao)
        with self.assertRaises(LockConversaPerdido):
            proteger_conversa(1, versao, cur)
        self.assertFalse(unlock_conversa(1, versao, cur))
        self.assertTrue(unlock_conversa(1, nova, cur))

    def test_migracao_incremental_reaplicavel_e_visita_pendente_sem_bloqueio(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261118.sql")
        script = (ROOT / "deploy/migrations/20261118_etapa1_encaminhamento_90_dias.sql").read_text(encoding="utf-8")
        self.adm.execute(script)
        self.adm.execute(script)
        self.assertEqual(self.adm.execute("SELECT id_etapa,bloqueio_dias FROM chatbot.etapa WHERE encerra_automaticamente ORDER BY id_etapa").fetchall(), [(8,0),(10,90)])
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem=11 AND evento='midia_recebida'").fetchone()[0], 0)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem=1 AND id_etapa_destino=10").fetchone()[0], 3)

    def preparar_cpf(self):
        self.preparar()
        self.fila("João da Silva")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (2, 0, True))

    def test_etapa2_cpf_global_snapshot_e_zero_inicial(self):
        self.preparar_cpf()
        self.fila("Meu CPF é 012.345678-90.")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (3, 0, True))
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.cliente").fetchone(),
                         ("João da Silva", "01234567890"))
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.atendimento_pos_venda").fetchone(),
                         ("João da Silva", "01234567890"))
        # Outra conversa inicia uma coleta independente, inclusive em outra central.
        from core.repositories.atendimento.conversas import inserindo_em_conversa_caso_seja_nova
        nova = inserindo_em_conversa_caso_seja_nova(1, 2, self.adm.cursor())
        self.assertIsNone(self.adm.execute("SELECT cpf_titular FROM chatbot.atendimento_pos_venda WHERE id_conversa=%s", (nova,)).fetchone()[0])

    def test_etapa2_tres_erros_e_quarto_encaminhamento_sem_cpf(self):
        self.preparar_cpf()
        for n, invalido in enumerate(("1234567890", "123456789012", "1234567890A"), 1):
            self.fila(invalido)
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (2, n, True))
            self.assertIsNone(self.adm.execute("SELECT cpf_titular FROM chatbot.cliente").fetchone()[0])
        self.fila("não sei")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.wa.send_carousel.assert_called_once()
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente_bloqueado_meta").fetchone()[0], 0)

    def test_cpf_mistura_midia_e_texto_quarto_erro_encaminha(self):
        self.preparar_cpf()
        for n, (texto, tipo) in enumerate([(None,"document"),("123","text"),(None,"image")], 1):
            self.fila(texto, tipo)
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (2, n, True))
        self.fila(None, "video")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)
        self.wa.send_carousel.assert_called_once()

    def test_etapa2_retry_de_cpf_invalido_nao_conta_duas_vezes(self):
        self.preparar_cpf()
        item = self.fila("12345")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após resposta"))
        self.assertEqual(self.conversa()[:3], (2, 1, True))
        envios = self.wa.send_message.call_count
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (2, 1, True))
        self.assertEqual(self.wa.send_message.call_count, envios)

    def test_etapa2_cpf_valido_zera_contador_e_replay_preserva_cadastro(self):
        self.preparar_cpf()
        self.fila("12345")
        self.ciclo()
        item = self.fila("01234567890")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após commit do CPF"))
        self.assertEqual(self.conversa()[:3], (3, 0, True))
        self.assertEqual(self.adm.execute("SELECT cpf_titular FROM chatbot.cliente").fetchone()[0], "01234567890")
        envios = self.wa.send_message.call_count
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.wa.send_message.call_count, envios)
        self.assertEqual(self.adm.execute("SELECT cpf_titular FROM chatbot.atendimento_pos_venda").fetchone()[0], "01234567890")

    def test_etapa2_falha_de_envio_nao_salva_cpf_nem_avanca(self):
        self.preparar_cpf()
        self.wa.send_message.side_effect = RuntimeError("falha simulada de envio")
        self.fila("01234567890")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (2, 0, True))
        self.assertIsNone(self.adm.execute("SELECT cpf_titular FROM chatbot.cliente").fetchone()[0])

    def test_etapa2_falha_antes_commit_reverte_cpf_global_e_snapshot(self):
        self.preparar_cpf()
        original = runtime.atualizar_banco_com_contexto_final
        def persistir_e_falhar(*args):
            original(*args)
            raise RuntimeError("queda depois de gravar CPF, antes de commit")
        self.fila("01234567890")
        self.ciclo(atualizar_banco_com_contexto_final=persistir_e_falhar)
        self.assertEqual(self.conversa()[:3], (2, 0, True))
        self.assertIsNone(self.adm.execute("SELECT cpf_titular FROM chatbot.cliente").fetchone()[0])
        self.assertIsNone(self.adm.execute("SELECT cpf_titular FROM chatbot.atendimento_pos_venda").fetchone()[0])

    def test_etapa2_cidade_global_nao_e_perguntada_de_novo(self):
        self.preparar_cpf()
        self.adm.execute("UPDATE chatbot.cliente SET cidade_loja_compra='Salvador'")
        self.fila("01234567890")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (3, 0, True))
        self.assertEqual(len(self.wa.send_message.call_args.kwargs["buttons"]), 3)
        self.assertEqual(self.adm.execute("SELECT cidade_loja_compra,cpf_titular FROM chatbot.cliente").fetchone(), ("Salvador", "01234567890"))

    def test_etapa2_migracao_catalogo_reaplicavel(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261118.sql")
        self.adm.execute("DELETE FROM chatbot.etapa_transicao WHERE id_etapa_origem=2 AND evento IN ('humano_solicitado','limite_sem_avanco')")
        script = (ROOT / "deploy/migrations/20261118_etapa2_cpf.sql").read_text(encoding="utf-8")
        self.adm.execute(script)
        self.adm.execute(script)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem=2 AND id_etapa_destino=10").fetchone()[0], 3)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao").fetchone()[0], 32)


    def encerrar_fixture_ha_91_dias(self):
        self.adm.execute("""
            UPDATE chatbot.conversa
            SET id_etapa_atual=7, iniciou_em=now()-interval '92 days',
                finalizou_em=now()-interval '91 days', status_ativa=false,
                motivo_encerramento='encaminhamento';
        """)

    def test_nova_conversa_recolhe_titular_e_preserva_snapshot_anterior(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        self.fila("Oi, voltei")
        self.ciclo()
        self.assertIn("nome completo", self.wa.send_message.call_args.kwargs["text"])
        self.assertEqual(self.adm.execute(
            "SELECT nome_titular,cpf_titular FROM chatbot.atendimento_pos_venda ORDER BY id_conversa"
        ).fetchall(), [("João da Silva", "01234567890"), (None, None)])
        self.fila("Ana da Silva")
        self.ciclo()
        self.assertIn("CPF do titular", self.wa.send_message.call_args.kwargs["text"])
        self.fila("12345678901")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.cliente").fetchone(),
                         ("Ana da Silva", "12345678901"))
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.chat").fetchone()[0], 1)

    def test_universal_no_retorno_so_compartilha_os_dados_da_nova_conversa(self):
        from urllib.parse import parse_qs, urlsplit
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        for texto in ("Olá", "Quero um humano"):
            self.fila(texto)
            self.ciclo()
        cartoes = self.wa.send_carousel.call_args.kwargs["cards"]
        self.assertEqual(len(cartoes), 2)
        for indice, cartao in enumerate(cartoes):
            link = cartao.to_dict(indice)["action"]["parameters"]["url"]
            resumo = parse_qs(urlsplit(link).query)["text"][0]
            self.assertNotIn("01234567890", resumo)
            self.assertNotIn("João da Silva", resumo)

    def test_par_exato_vence_cpf_igual_mais_recente(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        def ids():
            return self.adm.execute("SELECT id_cliente FROM chatbot.cliente ORDER BY id_cliente").fetchall()
        canonico, provisorio = ids()
        duplicado = self.adm.execute("""
            INSERT INTO chatbot.cliente (cpf_titular) VALUES ('01234567890') RETURNING id_cliente
        """).fetchone()
        conversa = self.adm.execute("SELECT id_conversa FROM chatbot.conversa WHERE status_ativa").fetchone()
        telefone = "5511999990000"
        self.assertEqual(self.entrada_privada(cartao=True, telefone=telefone, assinada=False)["status"], "ignored")
        self.assertEqual(ids(), [canonico, provisorio, duplicado])
        self.assertEqual(self.entrada_privada(cartao=True, telefone=telefone, envelope_wa=telefone)["status"], "inserted")
        self.ciclo()
        self.assertEqual(ids(), [canonico, provisorio, duplicado])
        self.assertIn("CPF do titular", self.wa.send_message.call_args.kwargs["text"])
        self.assertEqual(self.adm.execute("SELECT nome_titular FROM chatbot.cliente WHERE id_cliente=%s", canonico).fetchone(), ("João da Silva",))
        self.assertEqual(self.entrada_privada("Meu CPF é 012.345.678-90", envelope_wa=telefone)["status"], "inserted")
        self.ciclo()
        self.assertEqual(ids(), [canonico])
        self.assertEqual(self.adm.execute("SELECT id_conversa FROM chatbot.conversa WHERE status_ativa").fetchone(), conversa)
        self.assertEqual(self.adm.execute("SELECT count(DISTINCT id_chat) FROM chatbot.conversa").fetchone(), (1,))
        self.assertEqual(self.adm.execute("SELECT DISTINCT id_cliente FROM chatbot.fila_mensagens WHERE user_id_origem IS NOT NULL").fetchall(), [canonico])
        self.assertEqual(self.adm.execute("SELECT id_cliente FROM chatbot.identidade_bsuid WHERE vigente").fetchone(), canonico)
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.atendimento_pos_venda ORDER BY id_conversa").fetchall(),
                         [("João da Silva", "01234567890"), ("Ana da Silva", "01234567890")])
        self.assertEqual(self.adm.execute("SELECT nome_titular FROM chatbot.cliente").fetchone(), ("Ana da Silva",))
        self.entrada_privada("Móveis")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT tipo_destinatario,valor_destinatario FROM chatbot.historico_mensagens WHERE quem_enviou='bot' ORDER BY id_mensagem DESC LIMIT 1").fetchone(), ("wa_id", telefone))

    def conferir_vencedor_por_telefone(self, cpf_antigo):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        self.adm.execute("UPDATE chatbot.cliente SET cpf_titular=%s", (cpf_antigo,))
        antigo = self.adm.execute("SELECT id_cliente FROM chatbot.cliente").fetchone()[0]
        self.adm.execute("""
            INSERT INTO chatbot.identidade_bsuid (id_central,user_id,id_cliente,wamid_origem)
            VALUES (2,'alias-anterior',%s,'wamid.anterior')
        """, (antigo,))
        telefone = "5511999990000"
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        self.entrada_privada(cartao=True, telefone=telefone, envelope_wa=telefone)
        self.ciclo()
        self.entrada_privada("inválido", envelope_wa=telefone)
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente").fetchone(), (2,))
        self.entrada_privada("12345678901", envelope_wa=telefone)
        self.ciclo()
        self.assertEqual(self.adm.execute("""
            SELECT id_cliente,nome_titular,cpf_titular,waid_telefone,username FROM chatbot.cliente
        """).fetchall(), [(antigo, "Ana da Silva", "12345678901", telefone, "ana.silva")])
        self.assertEqual(self.adm.execute("""
            SELECT a.nome_titular,a.cpf_titular,ch.id_cliente
            FROM chatbot.atendimento_pos_venda a JOIN chatbot.conversa c USING(id_conversa)
            JOIN chatbot.chat ch USING(id_chat) ORDER BY c.iniciou_em
        """).fetchall(), [("João da Silva", "01234567890", antigo), ("Ana da Silva", "12345678901", antigo)])
        self.assertEqual(self.adm.execute("""
            SELECT vigente FROM chatbot.identidade_bsuid WHERE user_id='alias-anterior'
        """).fetchone(), (False,))
        for texto in ("Móveis", "Entrega", "Perdi a nota", "Quero saber a data"):
            self.assertEqual(self.entrada_privada(texto, envelope_wa=telefone)["status"], "inserted")
            self.ciclo()
        self.assertEqual(self.adm.execute("""
            SELECT tipo_destinatario,valor_destinatario FROM chatbot.historico_mensagens
            WHERE quem_enviou='bot' ORDER BY id_mensagem DESC LIMIT 1
        """).fetchone(), ("wa_id", telefone))
        self.assertEqual(self.adm.execute("""
            SELECT id_etapa_atual,status_ativa FROM chatbot.conversa ORDER BY id_conversa DESC LIMIT 1
        """).fetchone(), (7, False))

    def test_somente_telefone_igual_atualiza_cpf_e_preserva_historico(self):
        self.conferir_vencedor_por_telefone("01234567890")

    def test_somente_telefone_igual_preenche_cpf_anterior_ausente(self):
        self.conferir_vencedor_por_telefone(None)

    def test_desempate_em_dados_legados_respeita_grupo_e_exclui_provisorio(self):
        from core.identidade_atendimento import escolher_cadastro_vencedor
        cpf, tel = "01234567890", "5511999990000"
        candidatos = [(50, None, tel, False), (10, "11111111111", tel, False), (30, None, tel, False)]
        self.assertEqual(escolher_cadastro_vencedor(candidatos, 50, cpf, tel), 30)
        candidatos.extend([(4, cpf, None, False), (9, cpf, "5575999990000", False)])
        self.assertEqual(escolher_cadastro_vencedor(candidatos, 50, cpf, tel), 9)
        candidatos.extend([(2, cpf, tel, False), (7, cpf, tel, False)])
        self.assertEqual(escolher_cadastro_vencedor(candidatos, 50, cpf, tel), 7)

    def test_numero_novo_e_mesmo_cpf_atualizam_a_ficha_antiga(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        novo = "5575999991234"
        self.entrada_privada(cartao=True, telefone=novo)
        self.ciclo()
        self.entrada_privada("01234567890")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT waid_telefone, nome_titular FROM chatbot.cliente ORDER BY id_cliente").fetchall(),
                         [(novo, "Ana da Silva")])
        self.assertEqual(self.adm.execute("SELECT tipo_destinatario,valor_destinatario FROM chatbot.historico_mensagens WHERE quem_enviou='bot' ORDER BY id_mensagem DESC LIMIT 1").fetchone(), ("wa_id", novo))

    def test_telefone_e_cpf_em_fichas_diferentes_reunem_historico_por_central(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        telefone = "5511999990000"
        cpf = "12345678901"
        # O dono anterior do telefone teve atendimento com outro CPF.
        antigo = self.adm.execute("SELECT id_conversa FROM chatbot.conversa").fetchone()[0]
        mensagens = self.adm.execute("""
            SELECT id_mensagem,id_hash_msg,received_data_hora FROM chatbot.historico_mensagens
            WHERE id_conversa=%s ORDER BY id_mensagem
        """, (antigo,)).fetchall()
        def ficha(wa):
            return self.adm.execute("""
                INSERT INTO chatbot.cliente (cpf_titular,waid_telefone)
                VALUES (%s,%s) RETURNING id_cliente
            """, (cpf, wa)).fetchone()[0]

        duplicado = ficha("557500000001")
        vencedor = ficha("557500000002")
        chat_outra_central = self.adm.execute("""
            INSERT INTO chatbot.chat (id_cliente,id_central) VALUES (%s,2) RETURNING id_chat
        """, (duplicado,)).fetchone()[0]
        outra = self.adm.execute("""
            INSERT INTO chatbot.conversa (id_chat,id_central,id_etapa_atual,status_ativa,
                                          iniciou_em,finalizou_em,motivo_encerramento)
            VALUES (%s,2,7,false,now()-interval '100 days',now()-interval '99 days','encaminhamento')
            RETURNING id_conversa
        """, (chat_outra_central,)).fetchone()[0]
        self.adm.execute("""
            INSERT INTO chatbot.identidade_bsuid (id_central,user_id,id_cliente,wamid_origem)
            VALUES (1,'uid-antigo',%s,'wamid.antigo')
        """, (vencedor,))
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        self.entrada_privada(cartao=True, telefone=telefone, envelope_wa=telefone)
        self.ciclo()
        atual = self.adm.execute("SELECT id_conversa FROM chatbot.conversa WHERE status_ativa").fetchone()[0]
        self.entrada_privada(cpf, envelope_wa=telefone)
        self.ciclo()
        self.assertEqual(self.adm.execute("""
            SELECT id_cliente,nome_titular,cpf_titular,waid_telefone FROM chatbot.cliente
        """).fetchall(), [(vencedor, "Ana da Silva", cpf, telefone)])
        self.assertEqual(self.adm.execute("SELECT username FROM chatbot.cliente").fetchone(), ("ana.silva",))
        self.assertEqual(self.adm.execute("""
            SELECT ch.id_cliente,ch.id_central,c.id_conversa FROM chatbot.chat ch
            JOIN chatbot.conversa c USING(id_chat) ORDER BY ch.id_central,c.iniciou_em
        """).fetchall(), [(vencedor, 1, antigo), (vencedor, 1, atual), (vencedor, 2, outra)])
        self.assertEqual(self.adm.execute("""
            SELECT id_mensagem,id_hash_msg,received_data_hora FROM chatbot.historico_mensagens
            WHERE id_conversa=%s ORDER BY id_mensagem
        """, (antigo,)).fetchall(), mensagens)
        self.assertEqual(self.adm.execute("""
            SELECT cpf_titular FROM chatbot.atendimento_pos_venda WHERE id_conversa=%s
        """, (antigo,)).fetchone(), ("01234567890",))
        self.assertEqual(self.adm.execute("""
            SELECT id_cliente,vigente FROM chatbot.identidade_bsuid WHERE user_id='uid-antigo'
        """).fetchone(), (vencedor, False))
        self.entrada_privada("Móveis", envelope_wa=telefone)
        self.ciclo()
        self.assertEqual(self.adm.execute("""
            SELECT id_etapa_atual FROM chatbot.conversa WHERE id_conversa=%s
        """, (atual,)).fetchone(), (4,))

    def test_rollback_da_fusao_e_replay_apos_commit(self):
        from core.identidade_atendimento import conciliar_apos_cpf
        from core.repositories.atendimento import conciliacao_cliente

        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        telefone = "5511999990000"
        self.entrada_privada(cartao=True, telefone=telefone)
        self.ciclo()
        cpf = "01234567890"
        self.entrada_privada(cpf)
        entrada = self.adm.execute("""
            SELECT f.id_cliente,c.id_conversa,f.user_id_origem,f.id_mensagem,f.received_data_hora
            FROM chatbot.fila_mensagens f JOIN chatbot.chat ch USING(id_cliente,id_central)
            JOIN chatbot.conversa c USING(id_chat) WHERE c.status_ativa ORDER BY f.id_mensagem DESC LIMIT 1
        """).fetchone()
        origem, conversa, uid, fila, recebido = entrada
        contexto = {"id_cliente": origem, "id_conversa": conversa, "id_central": 1,
                    "id_phone_unidade": "999", "bsuid_vigente": uid, "telefone_compartilhado": telefone,
                    "mensagem_cliente_atual": {"id_mensagem_fila": fila, "received_data_hora": recebido}}
        def estado():
            return tuple(self.adm.execute(consulta).fetchall() for consulta in (
                "SELECT * FROM chatbot.cliente ORDER BY id_cliente",
                "SELECT * FROM chatbot.chat ORDER BY id_chat",
                "SELECT id_conversa,id_chat FROM chatbot.conversa ORDER BY id_conversa",
                "SELECT id_mensagem,id_cliente FROM chatbot.fila_mensagens ORDER BY id_mensagem",
                "SELECT * FROM chatbot.identidade_bsuid ORDER BY id_central,user_id",
                "SELECT telefone_compartilhado FROM chatbot.atendimento_pos_venda ORDER BY id_conversa",
            ))
        anterior = estado()
        with self.assertRaisesRegex(RuntimeError, "falha simulada"):
            with self.adm.transaction(), self.adm.cursor() as cursor:
                with patch.object(conciliacao_cliente, "excluir_cadastros_redundantes",
                                  side_effect=RuntimeError("falha simulada")):
                    conciliar_apos_cpf(contexto, cpf, cursor)
        self.assertEqual(estado(), anterior)

        # O próximo ciclo perde a finalização da fila, depois do commit dos efeitos.
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após o commit"))
        confirmado = estado()
        self.assertEqual(len(confirmado[0]), 1)
        envios = self.wa.send_message.call_count
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (fila,))
        self.ciclo()
        self.assertEqual(estado(), confirmado)
        self.assertEqual(self.wa.send_message.call_count, envios)
        self.assertEqual(self.adm.execute("SELECT status FROM chatbot.fila_mensagens WHERE id_mensagem=%s",
                                          (fila,)).fetchone(), ("sent",))

    def test_migracao_conferencia_cpf_reaplicavel_com_duplicados(self):
        self.adm.execute("INSERT INTO chatbot.cliente (cpf_titular) VALUES ('01234567890'),('01234567890')")
        self.adm.execute("DROP INDEX chatbot.cliente_cpf_conciliacao")
        self.adm.execute("ALTER TABLE chatbot.atendimento_pos_venda DROP COLUMN telefone_compartilhado")
        sql = (ROOT / "deploy/migrations/20261127_contato_conferencia_cpf.sql").read_text(encoding="utf8")
        self.adm.execute(sql)
        self.adm.execute(sql)
        self.assertTrue(self.adm.execute(
            "SELECT to_regclass('chatbot.cliente_cpf_conciliacao') IS NOT NULL"
        ).fetchone()[0])
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente").fetchone(), (2,))

    def test_encaminhamento_antes_do_cpf_preserva_o_dono_do_telefone(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        telefone = "5511999990000"
        self.entrada_privada(cartao=True, telefone=telefone)
        self.ciclo()
        self.assertEqual(self.entrada_privada("01234567890", assinada=False)["status"], "ignored")
        self.entrada_privada("Quero falar com um humano", envelope_wa=telefone)
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.cliente ORDER BY id_cliente").fetchall(),
                         [("João da Silva", "01234567890"), ("Ana da Silva", None)])
        self.assertEqual(self.adm.execute("SELECT id_etapa_atual,status_ativa FROM chatbot.conversa ORDER BY id_conversa DESC LIMIT 1").fetchone(), (7, False))

    def test_contato_comprovado_respeita_bloqueio_vigente_do_cadastro_antigo(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        self.adm.execute("UPDATE chatbot.conversa SET finalizou_em=now()-interval '1 day'")
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        self.assertEqual(self.entrada_privada(cartao=True, telefone="5511999990000")["reason"], "cliente_impedido")
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente").fetchone(), (2,))

    def test_compartilhar_com_chat_antigo_ativo_preserva_as_duas_conversas(self):
        self.preparar_produto()
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        eventos = self.adm.execute("SELECT id_conversa,id_chat FROM chatbot.conversa ORDER BY id_conversa").fetchall()
        self.assertEqual(self.entrada_privada(cartao=True, telefone="5511999990000")["status"], "inserted")
        self.ciclo()
        self.entrada_privada("01234567890")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT id_conversa,id_chat FROM chatbot.conversa ORDER BY id_conversa").fetchall(), eventos)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.cliente").fetchone(), (2,))

    def test_primeira_saudacao_replay_sem_reenvio_e_sem_contar_turno(self):
        item = self.fila("Quero um humano")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após saudação confirmada"))
        self.assertEqual(self.conversa()[:3], (1, 0, True))
        self.assertIsNone(self.adm.execute("SELECT nome_titular FROM chatbot.cliente").fetchone()[0])
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.wa.send_message.assert_called_once()
        self.wa.send_carousel.assert_not_called()
        self.assertEqual(self.conversa()[:3], (1, 0, True))

    def test_falha_da_primeira_saudacao_repete_apresentacao_sem_interpretar_nome(self):
        enviar = self.wa.send_message.side_effect
        self.wa.send_message.side_effect = RuntimeError("falha simulada")
        item = self.fila("João da Silva")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (1, 0, True))
        self.wa.send_message.side_effect = enviar
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertIsNone(self.adm.execute("SELECT nome_titular FROM chatbot.cliente").fetchone()[0])
        self.assertIn("eu sou o Theo", self.wa.send_message.call_args.kwargs["text"])

    def test_migracao_remapeia_encerramento_preservando_prazo_e_historico(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261118.sql")
        self.preparar()
        self.adm.execute("""
            UPDATE chatbot.conversa SET id_etapa_atual=10, status_ativa=false,
                finalizou_em=clock_timestamp(), motivo_encerramento='encaminhamento';
            UPDATE chatbot.historico_mensagens SET id_etapa=10 WHERE quem_enviou='bot';
        """)
        prazo = self.adm.execute("SELECT finalizou_em FROM chatbot.conversa").fetchone()[0]
        texto = self.adm.execute("SELECT id_hash_msg,conteudo_texto FROM chatbot.historico_mensagens ORDER BY id_mensagem").fetchall()
        self.migrar_catalogo()
        self.migrar_catalogo()
        self.assertEqual(self.adm.execute("SELECT id_etapa_atual,finalizou_em,status_ativa FROM chatbot.conversa").fetchone(),
                         (11, prazo, False))
        self.assertEqual(self.adm.execute("SELECT id_hash_msg,conteudo_texto FROM chatbot.historico_mensagens ORDER BY id_mensagem").fetchall(), texto)
        self.assertEqual(buscar_bloqueio_ativo_por_cliente_unidade("5511999990000", "999", self.adm.cursor()).bloqueio_dias, 90)
        self.assertEqual(self.adm.execute("SELECT id_etapa,bloqueio_dias FROM chatbot.etapa WHERE encerra_automaticamente ORDER BY id_etapa").fetchall(), [(8,0),(11,90)])
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao").fetchone()[0], 23)

    def test_migracao_cidade_pendente_apresenta_produto_sem_gravar_cidade(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261118.sql")
        self.preparar()
        self.adm.execute("""
            UPDATE chatbot.cliente SET nome_titular='João da Silva',cpf_titular='01234567890';
            UPDATE chatbot.conversa SET id_etapa_atual=3;
            UPDATE chatbot.historico_mensagens
            SET id_etapa=3,conteudo_texto='Qual a cidade da loja em que realizou a compra?'
            WHERE quem_enviou='bot';
        """)
        self.migrar_catalogo()
        self.fila("Salvador")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (3,0,True))
        self.assertIn("Sobre qual tipo de produto", self.wa.send_message.call_args.kwargs["text"])
        self.assertIsNone(self.adm.execute("SELECT cidade_loja_compra FROM chatbot.cliente").fetchone()[0])
        from core.repositories.fluxo.contextos.pos_venda import buscar_contexto_pos_venda
        self.assertFalse(buscar_contexto_pos_venda(1, self.adm.cursor())["apresentacao_pendente"])

    def test_migracao_abertura_pendente_com_cadastro_preserva_retry_da_entrada(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261118.sql")
        self.adm.execute("""
            INSERT INTO chatbot.cliente (waid_telefone,nome_titular,cpf_titular)
            VALUES ('5511999990000','João da Silva','01234567890');
            INSERT INTO chatbot.chat (id_cliente,id_central) VALUES (1,1);
            INSERT INTO chatbot.conversa (id_chat,id_central,id_etapa_atual) VALUES (1,1,11);
            INSERT INTO chatbot.atendimento_pos_venda (id_conversa,nome_titular,cpf_titular)
            VALUES (1,'João da Silva','01234567890');
        """)
        item = self.fila("Olá")
        self.adm.execute("UPDATE chatbot.fila_mensagens SET id_conversa=1 WHERE id_mensagem=%s", (item,))
        self.adm.execute("""
            INSERT INTO chatbot.historico_mensagens
            (id_conversa,id_etapa,received_data_hora,quem_enviou,id_hash_msg,id_mensagem_fila,tipo_mensagem,conteudo_texto)
            SELECT 1,11,received_data_hora,'cliente',id_hash_msg,id_mensagem,'text',conteudo_texto
            FROM chatbot.fila_mensagens WHERE id_mensagem=%s;
        """, (item,))
        self.migrar_catalogo()
        self.assertEqual(self.adm.execute("SELECT id_etapa FROM chatbot.historico_mensagens").fetchone()[0], 3)
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (3,0,True))
        self.assertIn("Sobre qual tipo de produto", self.wa.send_message.call_args.kwargs["text"])
        self.assertEqual(self.adm.execute("SELECT status FROM chatbot.fila_mensagens").fetchone()[0], "sent")


    def preparar_produto(self):
        self.preparar()
        self.fila("João da Silva")
        self.ciclo()
        self.fila("01234567890")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (3, 0, True))

    def test_produto_botao_grava_atendimento_e_zera_contador_ao_avancar(self):
        self.preparar_produto()
        self.fila("não quero falar dos dois")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (3, 1, True))
        self.fila("Apenas Móveis", "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (4, 0, True))
        self.assertEqual(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0], "moveis")
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.cliente").fetchone(),
                         ("João da Silva", "01234567890"))
        historico = self.adm.execute("""
            SELECT interativo FROM chatbot.historico_mensagens WHERE quem_enviou='bot'
            ORDER BY id_mensagem DESC LIMIT 1
        """).fetchone()[0]
        self.assertEqual(historico["type"], "list")
        self.assertEqual(len(historico["action"]["sections"][0]["rows"]), 5)

    def preparar_assunto(self, produto):
        self.preparar_produto()
        self.fila(produto, "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (4, 0, True))

    def preparar_pedidos(self, assunto):
        self.preparar_assunto("Apenas Móveis")
        self.fila(assunto)
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (5, 0, True))

    def test_pedidos_rejeita_filial_desconhecida_grava_varias_filiais_e_recupera_fila(self):
        self.preparar_pedidos("avarias")
        for turno, texto in enumerate(("10.24 e 10.09", "10.09 e 25.1 e 456.999"), start=1):
            self.fila(texto)
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (5, turno, True))
            self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.pedido_conversa").fetchone(), (0,))
            self.assertEqual(self.adm.execute("SELECT perdeu_nota FROM chatbot.atendimento_pos_venda").fetchone(), (None,))
        item = self.fila("Na nota: 0010.09, 0010.15 e 0010.09.")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após commit de pedidos"))
        self.wa.reset_mock()
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.wa.send_message.assert_not_called()
        self.assertEqual(self.conversa()[:3], (6, 0, True))
        self.assertEqual(self.adm.execute("""
            SELECT p.numero, f.nome FROM chatbot.pedido_conversa p
            JOIN chatbot.filial_compra f ON f.codigo=p.codigo_filial ORDER BY p.numero
        """).fetchall(), [("0010.09", "ATACADÃO DO SOFÁ - IRECÊ"), ("0010.15", "ATACADÃO DO SOFÁ - COITÉ")])
        self.assertEqual(self.adm.execute("SELECT perdeu_nota FROM chatbot.atendimento_pos_venda").fetchone(), (False,))

    def test_conclusao_mista_grava_relato_e_um_carrossel_com_dois_links(self):
        from urllib.parse import parse_qs, urlsplit
        self.preparar_assunto("Estofados e Móveis")
        for texto in ("Duas ou mais opções acima", "0010.09 e 0010.26"):
            self.fila(texto)
            self.ciclo()
        relato = "O sofá rasgou.\nA mesa veio riscada."
        entrada = self.fila(relato)
        with patch("core.integrations.whatsapp.messages.encaminhamento_pos_venda.obter_saudacao_por_horario",
                   return_value="Boa tarde"):
            self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento"))
        self.assertEqual(self.adm.execute(
            "SELECT detalhes,encaminhado_atacadao,encaminhado_baratao,situacao FROM chatbot.atendimento_pos_venda"
        ).fetchone(), (relato, "557592087803", "557582467000", "Já encaminhado"))
        partes = self.adm.execute("""
            SELECT parte_resposta,conteudo_texto,interativo FROM chatbot.historico_mensagens
            WHERE id_mensagem_fila=%s AND quem_enviou='bot' ORDER BY parte_resposta
        """, (entrada,)).fetchall()
        self.assertEqual([p[0] for p in partes], [1])
        self.wa.send_carousel.assert_called_once()
        self.assertIn("90 dias", partes[0][1])
        cartoes = partes[0][2]["action"]["cards"]
        self.assertEqual(len(cartoes), 2)
        for interativo, numero in zip(cartoes, ("557592087803", "557582467000")):
            url = urlsplit(interativo["action"]["parameters"]["url"])
            self.assertEqual(url.path, "/" + numero)
            resumo = parse_qs(url.query)["text"][0]
            self.assertEqual(resumo, (
                "Olá, boa tarde! Fui encaminhado(a) pelo assistente Theo e gostaria de atendimento humano.\n\n"
                "- Titular da compra: João da Silva\n"
                "- CPF do titular: 01234567890\n"
                "- Produto: Móveis e Estofados\n"
                "- Assunto: Misto\n"
                "- Números das notas:\n"
                "  • 0010.09 (ATACADÃO DO SOFÁ - IRECÊ)\n"
                "  • 0010.26 (BARATÃO DOS MÓVEIS - SAJ (FEIRÃO))\n\n"
                + relato
            ))

    def test_falha_no_carrossel_nao_confirma_relato_nem_encerramento(self):
        self.preparar_assunto("Estofados e Móveis")
        for texto in ("Entrega", "Perdi a nota"):
            self.fila(texto)
            self.ciclo()
        self.wa.send_carousel.side_effect = RuntimeError("carrossel indisponível")
        item = self.fila("Minha entrega está atrasada.")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (6, 0, True))
        self.assertEqual(self.adm.execute("""
            SELECT detalhes, encaminhado_atacadao, encaminhado_baratao, situacao FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, None, None, "Não encaminhado"))
        self.assertEqual(self.adm.execute("""
            SELECT count(*) FROM chatbot.historico_mensagens WHERE id_mensagem_fila=%s AND quem_enviou='bot'
        """, (item,)).fetchone(), (0,))

    def test_situacao_e_observacao_do_operador_resistem_a_regravacao_dos_destinos(self):
        from core.repositories.atendimento.pos_venda import registrar_contatos_encaminhados

        self.preparar()
        consulta = "SELECT id_conversa, situacao, observacao FROM chatbot.atendimento_pos_venda"
        conversa, situacao, observacao = self.adm.execute(consulta).fetchone()
        self.assertEqual((situacao, observacao), ("Não encaminhado", None))
        editar = "UPDATE chatbot.atendimento_pos_venda SET situacao=%s, observacao=%s WHERE id_conversa=%s"
        with self.assertRaises(psycopg.errors.CheckViolation):
            self.adm.execute(editar, ("Resolvido", "Ainda no bot", conversa))

        self.fila("Quero falar com um humano")
        self.ciclo()
        for nova_situacao, nota in (("Aguardando cliente", "Enviei a previsão."), ("Resolvido", "Entrega confirmada.")):
            self.adm.execute(editar, (nova_situacao, nota, conversa))
            with self.adm.cursor() as cursor:
                registrar_contatos_encaminhados(conversa, "557582467000", "557592087803", cursor)
            self.assertEqual(self.adm.execute(consulta).fetchone(), (conversa, nova_situacao, nota))

    def test_encaminhamento_universal_apos_perder_nota_usa_resumo_parcial(self):
        from urllib.parse import parse_qs, urlsplit
        self.preparar_pedidos("entrega")
        self.fila("Perdi a nota")
        self.ciclo()
        self.fila("Quero falar com um humano")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_humano"))
        texto, interativo = self.adm.execute("""
            SELECT conteudo_texto,interativo FROM chatbot.historico_mensagens
            WHERE quem_enviou='bot' ORDER BY id_mensagem DESC LIMIT 1
        """).fetchone()
        self.assertNotIn("avaria", texto)
        cartoes = interativo["action"]["cards"]
        self.assertEqual(len(cartoes), 2)
        for cartao in cartoes:
            resumo = parse_qs(urlsplit(cartao["action"]["parameters"]["url"]).query)["text"][0]
            self.assertEqual(len(resumo.split("\n\n")), 2)
            self.assertTrue(resumo.endswith("- Assunto: Entrega\n- Número da nota: Perdi a nota"))
            self.assertNotIn("5511999990000", resumo)

    def conferir_encaminhamento_uma_rede(self, notas, resposta, rede, numero):
        self.preparar_pedidos("entrega")
        for texto in (notas, resposta):
            self.fila(texto)
            self.ciclo()
        self.assertEqual(self.conversa()[:3], (7, 0, False))
        self.wa.send_carousel.assert_not_called()
        interativo = self.adm.execute("""
            SELECT interativo FROM chatbot.historico_mensagens WHERE quem_enviou='bot'
            ORDER BY id_mensagem DESC LIMIT 1
        """).fetchone()[0]
        self.assertEqual(interativo["type"], "cta_url")
        self.assertNotIn("header", interativo)
        parametros = interativo["action"]["parameters"]
        self.assertEqual(parametros["display_text"], "Pós-venda " + rede)
        self.assertIn("wa.me/" + numero + "?", parametros["url"])
        destinos = self.adm.execute("""
            SELECT encaminhado_atacadao, encaminhado_baratao FROM chatbot.atendimento_pos_venda
        """).fetchone()
        self.assertEqual(destinos, (numero, None) if rede == "Atacadão" else (None, numero))

    def test_notas_sfb_e_deposito_encaminham_ao_baratao(self):
        self.conferir_encaminhamento_uma_rede("100.01 e 200.05", "Minha entrega atrasou.",
                                             "Baratão", "557582467000")

    def test_universal_depois_de_notas_do_atacadao_encaminha_apenas_ao_atacadao(self):
        self.conferir_encaminhamento_uma_rede("100.09 e 200.15", "Quero um humano",
                                             "Atacadão", "557592087803")

    def test_migracao_sete_etapas_reapresenta_pergunta_e_respeita_visita_antiga(self):
        from core.integrations.whatsapp.messages.etapa6_detalhes_messages import MENSAGEM_DETALHES

        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_9_etapas.sql")
        self.preparar()
        self.adm.execute("""
            UPDATE chatbot.conversa SET id_etapa_atual=6,turnos_sem_avanco=2;
            UPDATE chatbot.historico_mensagens SET id_etapa=6 WHERE quem_enviou='bot';
            INSERT INTO chatbot.conversa (id_chat,id_central,id_etapa_atual,status_ativa,finalizou_em,motivo_encerramento)
            VALUES (1,1,7,false,now(),'visita_pendente');
        """)
        script = (ROOT / "deploy/migrations/20261126_baratao_sete_etapas.sql").read_text(encoding="utf-8")
        self.adm.execute(script)
        self.adm.execute(script)
        recoleta = (ROOT / "deploy/migrations/20261126_recoleta_titular.sql").read_text(encoding="utf-8")
        for _ in range(2):
            self.adm.execute(recoleta)
            self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao").fetchone(), (27,))
        midia = (ROOT / "deploy/migrations/20261127_midia_repete_etapa.sql").read_text(encoding="utf-8")
        for _ in range(2):
            self.adm.execute(midia)
            self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao").fetchone(), (21,))
        self.assertIsNone(buscar_bloqueio_ativo_por_cliente_unidade("5511999990000", "999", self.adm.cursor()))
        self.fila("Sim")
        self.ciclo()
        self.assertEqual(self.wa.send_message.call_args.kwargs["text"], MENSAGEM_DETALHES)
        self.assertTrue(MENSAGEM_DETALHES.startswith("Certo, estamos quase lá! 😁\n\nPara podermos"))
        self.assertIsNone(self.adm.execute("SELECT detalhes FROM chatbot.atendimento_pos_venda").fetchone()[0])

    def test_nota_perdida_avanca_para_relato_sem_criar_pedido(self):
        self.preparar_pedidos("entrega")
        self.fila("Perdi a nota", "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (6, 0, True))
        self.assertEqual(self.adm.execute("SELECT perdeu_nota FROM chatbot.atendimento_pos_venda").fetchone(), (True,))
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.pedido_conversa").fetchone(), (0,))

    def test_correcao_com_uma_nota_processa_apenas_a_nova_resposta(self):
        self.preparar_pedidos("entrega")
        self.fila("0010.09 e 25.1 e 33.4")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (5, 1, True))
        self.fila("25.01")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (6, 0, True))
        self.assertEqual(self.adm.execute("SELECT numero FROM chatbot.pedido_conversa").fetchall(), [("25.01",)])

    def test_repetir_filial_inexistente_encaminha_no_quarto_turno(self):
        self.preparar_pedidos("entrega")
        for turno in range(1, 4):
            self.fila("123.04")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (5, turno, True))
        self.fila("123.04")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.pedido_conversa").fetchone(), (0,))

    def test_assunto_misto_persiste_somente_apos_confirmacao_e_sobrevive_ao_replay(self):
        self.preparar_assunto("Estofados e Móveis")
        self.fila("Ainda não sei")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (4, 1, True))
        self.assertIsNone(self.adm.execute("SELECT assunto FROM chatbot.atendimento_pos_venda").fetchone()[0])
        self.fila("Previsão de entrega e montagem")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após commit do assunto"))
        self.assertEqual(self.conversa()[:3], (5, 0, True))
        self.assertEqual(self.adm.execute("SELECT produto, assunto FROM chatbot.atendimento_pos_venda").fetchone(),
                         ("ambos", "misto"))
        self.wa.reset_mock()
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE status='pending'")
        self.ciclo()
        self.wa.send_message.assert_not_called()
        self.assertEqual(self.adm.execute("SELECT status FROM chatbot.fila_mensagens ORDER BY id_mensagem DESC LIMIT 1").fetchone()[0], "sent")

    def test_quarto_turno_na_lista_encaminha_ambas_redes_e_bloqueia(self):
        self.preparar_assunto("Apenas Estofados")
        for turno in range(1, 4):
            self.fila("?", "text")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (4, turno, True))
        self.fila(None, "document")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.assertEqual(self.adm.execute("""
            SELECT assunto, encaminhado_baratao, encaminhado_atacadao FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, "557582467000", "557592087803"))
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)

    def test_produto_quarta_entrada_encaminha_sem_salvar_escolha(self):
        self.preparar_produto()
        for n in range(1, 4):
            self.fila("???")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (3, n, True))
        self.fila("id de botão desconhecido", "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.assertIsNone(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0])
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)

    def test_produto_valido_apos_tres_midias_zera_contador(self):
        self.preparar_produto()
        for n in range(1, 4):
            self.fila(None, "video")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (3, n, True))
        self.fila("móveis")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (4, 0, True))
        self.assertEqual(self.adm.execute("""
            SELECT produto,encaminhado_atacadao,encaminhado_baratao FROM chatbot.atendimento_pos_venda
        """).fetchone(), ("moveis", None, None))

    def test_produto_queda_antes_commit_reverte_dado_etapa_e_resposta(self):
        self.preparar_produto()
        original = runtime.atualizar_banco_com_contexto_final
        def persistir_e_falhar(*args):
            original(*args)
            raise RuntimeError("queda antes do commit de produto")
        item = self.fila("Quero falar dos dois")
        self.ciclo(atualizar_banco_com_contexto_final=persistir_e_falhar)
        self.assertEqual(self.conversa()[:3], (3, 0, True))
        self.assertIsNone(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0])
        self.assertEqual(self.adm.execute("""
            SELECT count(*) FROM chatbot.historico_mensagens
            WHERE id_mensagem_fila=%s AND quem_enviou='bot'
        """, (item,)).fetchone()[0], 0)
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (4, 0, True))
        self.assertEqual(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0], "ambos")

    def test_produto_replay_apos_commit_nao_reenvia_lista(self):
        self.preparar_produto()
        item = self.fila("não quero falar de móveis")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após commit de produto"))
        self.assertEqual(self.conversa()[:3], (4, 0, True))
        envios = self.wa.send_message.call_count
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.wa.send_message.call_count, envios)
        self.assertEqual(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0], "estofados")
        self.assertEqual(self.adm.execute("SELECT status FROM chatbot.fila_mensagens WHERE id_mensagem=%s", (item,)).fetchone()[0], "sent")

    def test_produto_nao_e_reutilizado_em_nova_conversa(self):
        self.preparar_produto()
        self.fila("Móveis")
        self.ciclo()
        self.adm.execute("""
            UPDATE chatbot.conversa SET id_etapa_atual=7,status_ativa=false,
                iniciou_em=now()-interval '92 days',finalizou_em=now()-interval '91 days',
                motivo_encerramento='encaminhamento';
        """)
        self.fila("Olá")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda ORDER BY id_conversa").fetchall(),
                         [("moveis",), (None,)])
        self.assertEqual(self.adm.execute("SELECT id_etapa_atual FROM chatbot.conversa ORDER BY id_conversa DESC LIMIT 1").fetchone()[0], 1)
        self.fila("Maria Souza")
        self.ciclo()
        self.assertIn("CPF", self.wa.send_message.call_args.kwargs["text"])
        self.fila("12345678901")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT id_etapa_atual FROM chatbot.conversa ORDER BY id_conversa DESC LIMIT 1").fetchone()[0], 3)

    def test_migracao_produto_assunto_preserva_historico_e_reaplica(self):
        self.carregar_catalogo("tests/fixtures/catalogo_pos_venda_20261118.sql")
        self.migrar_catalogo()
        self.preparar_produto()
        self.adm.execute("UPDATE chatbot.conversa SET id_etapa_atual=5")
        self.adm.execute("UPDATE chatbot.historico_mensagens SET id_etapa=5 WHERE quem_enviou='bot' AND id_etapa=3")
        conteudos = self.adm.execute("SELECT id_hash_msg,conteudo_texto FROM chatbot.historico_mensagens ORDER BY id_mensagem").fetchall()
        novo = (ROOT / "deploy/migrations/20261122_etapa3_produto_assunto.sql").read_text(encoding="utf-8")
        self.adm.execute(novo)
        self.adm.execute(novo)
        self.assertEqual(self.conversa()[:3], (4, 0, True))
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa WHERE id_etapa=5").fetchone()[0], 0)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.etapa_transicao").fetchone()[0], 25)
        self.assertEqual(self.adm.execute("SELECT id_hash_msg,conteudo_texto FROM chatbot.historico_mensagens ORDER BY id_mensagem").fetchall(), conteudos)
        self.assertEqual(self.adm.execute("SELECT id_etapa_destino FROM chatbot.etapa_transicao WHERE id_etapa_origem=3 AND evento='produto_escolhido'").fetchone()[0], 4)


if __name__ == "__main__":
    unittest.main()
```

## 49. `tests/test_etapa2_pos_venda.py` (alterar)

```python
"""CPF e encaminhamento universal da etapa 2 sem serviços externos."""
import os
import unittest
from itertools import product
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.cpf_titular import extrair_cpf_titular
from core.integrations.whatsapp.messages.etapa2_messages import (
    MENSAGEM_PADRAO_ETAPA2, MENSAGEM_CPF_INVALIDO,
)
from core.integrations.whatsapp.messages.etapa3_messages import MENSAGEM_PRODUTO
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from workers.worker_flow.response_flow.flow_sender import flow_sender
from tests.test_etapa1_pos_venda import contexto, ENV, PATCH_TEXTO, PATCH_CARTOES


def contexto_cpf(texto="12345678901", *, tipo="text", turnos=0, cidade=None):
    ctx = contexto(etapa=2, texto=texto, tipo=tipo, turnos=turnos)
    ctx["transicoes_permitidas"] = {
        "cpf_valido": 3,
        "humano_solicitado": 7, "limite_sem_avanco": 7,
    }
    ctx["cadastro"] = {"nome_titular": "João da Silva", "cidade_loja_compra": cidade}
    return ctx


class ExtratorCpfTests(unittest.TestCase):
    def test_pontuacao_completa_ou_faltando_em_todas_as_combinacoes(self):
        for ponto1, ponto2, traco in product(("", "."), ("", "."), ("", "-")):
            entrada = f"Meu CPF é 012{ponto1}345{ponto2}678{traco}90, obrigado."
            with self.subTest(entrada=entrada):
                self.assertEqual(extrair_cpf_titular(entrada), "01234567890")

    def test_extrai_documento_sem_juntar_numeros_da_frase(self):
        for entrada in (
            "01234567890", "CPF:012.345.678-90", "Tenho 30 anos, meu CPF é 01234567890.",
            "01234567890,obrigado", "(012.345.678-90)", "Meu CPF é *01234567890*",
            "RG 1234567, nasci em 01/02/1990. CPF 012.345.678-90.",
            "01234567890; confirmando: 012.345.678-90",
        ):
            with self.subTest(entrada=entrada):
                self.assertEqual(extrair_cpf_titular(entrada), "01234567890")

    def test_rejeita_ausente_maior_menor_letras_e_trechos(self):
        for entrada in (
            None, "", "não lembro", "1234567890", "123456789012", "123.456.789-0",
            "123.456.789-012", "123.456.78A-01", "1234567890A", "A12345678901",
            "12345678901A", "123456789O1", "12345678901/2", "12345678901+2",
            "12345678901,2", "0123456789-012", "123 456 789 01", "123_456_789_01",
            "１２３４５６７８９０１", "123.4567.8901X", "123.456.789-01/99",
            "RG 12345678 e pedido 901", "123..456.789-01",
        ):
            with self.subTest(entrada=entrada):
                self.assertIsNone(extrair_cpf_titular(entrada))

    def test_dois_cpfs_diferentes_exigem_correcao(self):
        self.assertIsNone(extrair_cpf_titular("O meu é 012.345.678-90 e o dele 12345678901"))

    def test_simbolos_proibidos_nao_sao_removidos_nem_separam_um_cpf_parcial(self):
        cpf = "01234567890"
        for simbolo in '/\\@#$_+*=,:;!?|&%~^<>()[]{}\"\'–—😊\u200b':
            entradas = [cpf[:i] + simbolo + cpf[i:] for i in range(1, len(cpf))]
            entradas += [cpf + simbolo + "1", "1" + simbolo + cpf]
            for entrada in entradas:
                with self.subTest(entrada=entrada):
                    self.assertIsNone(extrair_cpf_titular("Meu CPF é " + entrada))

    def test_criterio_e_formato_nao_digito_verificador_ou_receita(self):
        self.assertEqual(extrair_cpf_titular("11111111111"), "11111111111")
        self.assertEqual(extrair_cpf_titular("000.000.000-00"), "00000000000")


class Etapa2Tests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.cpf")
        self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.carrossel")
        patches = (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                   patch(PATCH_CARTOES, return_value=self.wa))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_nome_valido_agora_envia_novo_texto_do_cpf(self):
        envio = flow_sender(contexto(texto="João da Silva"))
        self.assertEqual(envio["id_etapa_resultante"], 2)
        self.assertEqual(envio["mensagem_bot"], "Certo João. Em uma única mensagem, me informe o CPF do titular da compra.")

    def test_cpf_extraido_avanca_com_zero_inicial_preservado(self):
        envio = flow_sender(contexto_cpf("Meu CPF: 012.345678-90"))
        self.assertEqual(envio["cpf_titular"], "01234567890")
        self.assertEqual(envio["id_etapa_resultante"], 3)
        self.assertEqual(envio["evento_transicao"], "cpf_valido")
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_PRODUTO)

    def test_cidade_global_ja_presente_vai_ao_produto_com_tres_botoes(self):
        envio = flow_sender(contexto_cpf(cidade="Salvador"))
        self.assertEqual(envio["id_etapa_resultante"], 3)
        self.assertEqual(envio["evento_transicao"], "cpf_valido")
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_PRODUTO)
        self.assertEqual([b["reply"]["title"] for b in envio["interativo"]["action"]["buttons"]],
                         ["Apenas Estofados", "Apenas Móveis", "Estofados e Móveis"])

    def test_invalido_permanece_sem_tentar_salvar_cpf(self):
        for texto in ("12345678A01", "012/345/678-90", "01234567890@1", "012_345_678_90"):
            with self.subTest(texto=texto):
                envio = flow_sender(contexto_cpf(texto))
                self.assertEqual(envio["mensagem_bot"], MENSAGEM_CPF_INVALIDO)
                self.assertEqual(envio["id_etapa_resultante"], 2)
                self.assertTrue(envio["tratamento"])
                self.assertNotIn("cpf_titular", envio)
                self.assertNotIn("evento_transicao", envio)

    def test_tres_erros_repetem_e_quarto_encaminha(self):
        for turnos in range(3):
            self.assertEqual(flow_sender(contexto_cpf("123", turnos=turnos))["mensagem_bot"], MENSAGEM_CPF_INVALIDO)
        envio = flow_sender(contexto_cpf("123", turnos=3))
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.wa.send_carousel.assert_called_once()

    def test_pedido_humano_antecipa_validacao_do_cpf(self):
        envio = flow_sender(contexto_cpf("Quero um HUMANO, CPF 01234567890"))
        self.assertEqual(envio["evento_transicao"], "humano_solicitado")
        self.assertNotIn("cpf_titular", envio)
        self.wa.send_message.assert_not_called()

    def test_transicao_ausente_impede_envio(self):
        ctx = contexto_cpf()
        ctx["transicoes_permitidas"].pop("cpf_valido")
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()

    def test_falha_meta_ou_ausencia_de_wamid_nao_devolve_cpf_para_persistir(self):
        self.wa.send_message.side_effect = RuntimeError("falha simulada")
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_cpf())
        self.wa.send_message.side_effect = None
        self.wa.send_message.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_cpf())

    def test_replay_nao_reinterpreta_documento_nem_envia(self):
        ctx = contexto_cpf("conteúdo diferente")
        ctx["id_etapa_atual"] = 3
        ctx["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 3, "id_hash_msg": "wamid.confirmado",
            "interativo": {"_fluxo": {"evento": "cpf_valido"}},
        }
        envio = flow_sender(ctx)
        self.assertTrue(envio["resposta_ja_existia"])
        self.assertNotIn("cpf_titular", envio)
        self.wa.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

## 50. `tests/test_identidade_cliente_whatsapp.py` (criar)

```python
import json
from pathlib import Path
from unittest import TestCase

from core.integrations.whatsapp.identidade_cliente import extrair_identidade
from core.validacoes.compartilhamento_contato import telefone_compartilhado
from core.validacoes.destinatario_whatsapp import escolher_destinatario

def entrada(nome):
    pasta = Path(__file__).resolve().parents[1] / "payloads"
    evento = json.loads((pasta / (nome + ".json")).read_text(encoding="utf-8-sig"))
    valor = evento["entry"][0]["changes"][0]["value"]
    return valor, valor["messages"][0]

class IdentidadeClienteTests(TestCase):
    def test_prioridade_das_rotas(self):
        for nome, rota in (("WAID", "wa_id"), ("WAID_BSUID_USERNAME", "wa_id"),
                           ("BSUID_USERNAME", "bsuid")):
            with self.subTest(nome=nome):
                identidade = extrair_identidade(*entrada(nome))
                self.assertEqual(escolher_destinatario(identidade.wa_id,
                                 identidade.user_id, False)[0], rota)

    def test_apenas_contato_oficial_do_remetente(self):
        _, msg = entrada("CONTACT_INFO")
        bsuid = msg["from_user_id"]
        self.assertTrue(telefone_compartilhado(msg, bsuid, ()))
        self.assertIsNone(telefone_compartilhado(msg, "outro", ()))
        msg["contacts"][0]["origin"] = "other"
        self.assertIsNone(telefone_compartilhado(msg, bsuid, ()))


class ContratoHTTP(TestCase):
    def test_telefone_e_bsuid_com_as_duas_rotas_de_central(self):
        import httpx
        from core.integrations.whatsapp.remetente import usar_remetente_central
        from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
        from core.integrations.whatsapp.tools.config import get_meta_graph_api_version
        for waac in (None,"901"):
            for chave, valor in (("to","5511999999999"),("recipient","BR.123456789")):
                with self.subTest(waac=waac,chave=chave):
                    def resposta(req):
                        corpo=json.loads(req.content)
                        self.assertEqual(req.url.path,f"/v{get_meta_graph_api_version()}/{waac or '900'}/messages")
                        self.assertEqual(corpo["messaging_account_id"],"800")
                        self.assertEqual(corpo[chave],valor)
                        self.assertNotIn("to" if chave=="recipient" else "recipient",corpo)
                        self.assertEqual(corpo["interactive"]["action"]["name"],"request_contact_info")
                        return httpx.Response(200,json={"messaging_product":"whatsapp",
                            "contacts":[{"input":valor, "user_id" if chave=="recipient" else "wa_id":valor}],
                            "messages":[{"id":"wamid.simulado"}]})
                    central={"phone_number_id":"900","waac_id":waac,"messaging_account_id":"800"}
                    with httpx.Client(transport=httpx.MockTransport(resposta)) as sessao:
                        with usar_remetente_central(central,"900"):
                            msg=conta_wa("900",token="teste",session=sessao).request_contact_info(to=valor,text="Teste")
                    self.assertEqual(msg.id,"wamid.simulado")

    def test_bloqueio_e_desbloqueio_pelo_sdk_com_waac_e_phone_id(self):
        import httpx
        from unittest.mock import patch
        from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
        from core.integrations.whatsapp.tools import usuarios
        from core.integrations.whatsapp.remetente import usar_remetente_central

        for waac in (None, "771"):
            for chave, valor in (("user", "5511991234567"), ("user_id", "BR.12345")):
                with self.subTest(waac=waac, chave=chave):
                    metodos = []
                    def responder(req):
                        metodos.append(req.method)
                        self.assertTrue(req.url.path.endswith(f"/{waac or '999'}/block_users"))
                        self.assertEqual(json.loads(req.content)["block_users"], [{chave: valor}])
                        campo = "added_users" if req.method == "POST" else "removed_users"
                        resultado = {"input": valor, "wa_id" if chave == "user" else "user_id": valor}
                        return httpx.Response(200, json={"block_users": {campo: [resultado]}})
                    central = {"phone_number_id": "999", "messaging_account_id": "100", "waac_id": waac}
                    with httpx.Client(transport=httpx.MockTransport(responder)) as sessao:
                        with usar_remetente_central(central, "999"):
                            cliente = conta_wa("999", token="teste", session=sessao)
                        with patch.object(usuarios, "cliente_de_bloqueio", return_value=cliente):
                            self.assertTrue(usuarios.bloquear_usuario_meta(valor,"999").added_users)
                            self.assertTrue(usuarios.desbloquear_usuario_meta(valor,"999").removed_users)
                    self.assertEqual(metodos, ["POST", "DELETE"])
```

## 51. `callback/webhook/admin.py` (alterar)

```python
"""Painel operacional do pós-venda. A fila e o histórico são controlados pelo worker."""
import logging

from django.contrib import admin, messages
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect
from django.urls import reverse

from core.cache.cache_unidade import CacheUnidadesIndisponivel, recarregar_cache_unidades_ou_erro
from . import models
from .admin_relacoes import ConsultasRelacionadasMixin
from .forms import CentralPosVendaForm
from .models import CentralPosVenda

logger = logging.getLogger(__name__)


@admin.register(CentralPosVenda)
class CentralPosVendaAdmin(ConsultasRelacionadasMixin, admin.ModelAdmin):
    campo_vinculo = "central"
    consultas = {
        "acessos": (models.MonitoramentoAcesso, ("usuario_id", "usuario__username"), ("usuario_id",)),
        "bloqueios": (models.ClienteBloqueadoMeta, ("wa_id_cliente", "bloqueado_em"), ("wa_id_cliente",)),
        "consumo": (models.ConsumoMensalMeta, ("mes_referencia", "qtd_janela_gratuita", "qtd_franquia_consumida",
                    "qtd_cobradas_meta", "valor_meta", "moeda", "status_apuracao"), ("-mes_referencia",)),
        "coletas": (models.ConsumoMetaColeta, ("periodo", "proxima_consulta_em", "ultima_tentativa_em",
                    "falhas_consecutivas", "ultimo_erro"), ("periodo",)),
        "identidades": (models.IdentidadeBsuid, ("cliente_id", "user_id", "vigente", "suspender_telefone"),
                        ("cliente_id", "user_id")),
    }
    fieldsets = (
        ("Atendimento", {"fields": ("nome", "ativa", "nome_agente", "genero_agente")}),
        ("Remetente no WhatsApp", {"fields": ("telefone", "waba_id", "phone_number_id", "waac_id")}),
        ("Redes de pós-venda", {"fields": ("telefone_baratao", "telefone_atacadao")}),
        ("Monitoramento", {"fields": ("consultas_do_registro", "id_fuso", "nome_fuso", "fuso_verificado_em")}),
    )
    form = CentralPosVendaForm
    list_display = ("nome", "ativa", "telefone", "phone_number_id", "waba_id", "waac_id")
    search_fields = ("nome", "telefone", "phone_number_id", "waba_id", "waac_id")
    list_filter = ("ativa",)
    ordering = ("nome", "id_central")
    readonly_fields = ("consultas_do_registro", "id_fuso", "nome_fuso", "fuso_verificado_em")

    def save_model(self, request, obj, form, change):
        if change:
            # Preserva o fuso sincronizado em paralelo. O trigger central_mudou
            # versiona o cache na própria transação, uma vez por UPDATE.
            obj.save(update_fields=form.changed_data)
        else:
            super().save_model(request, obj, form, change)
        self._sincronizar_apos_commit(request, obj._state.db)

    def delete_model(self, request, obj):
        using = obj._state.db
        super().delete_model(request, obj)
        self._sincronizar_apos_commit(request, using)

    def delete_queryset(self, request, queryset):
        using = queryset.db
        super().delete_queryset(request, queryset)
        self._sincronizar_apos_commit(request, using)

    def _sincronizar_apos_commit(self, request, using):
        # O trigger já versionou o catálogo. Recarregar apenas dados confirmados,
        # inclusive quando o Admin está dentro de uma transação externa.
        def publicar():
            try:
                with connections[using].cursor() as cursor:
                    recarregar_cache_unidades_ou_erro(cursor)
            except (CacheUnidadesIndisponivel, DatabaseError):
                logger.exception("central_confirmada_cache_pendente")
                self.message_user(
                    request, "Alteração salva no banco. A sincronização do cache está pendente.",
                    level=messages.WARNING,
                )

        transaction.on_commit(publicar, using=using)

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except IntegrityError as exc:
            # Um worker pode criar um vínculo após a tela de confirmação.
            if not isinstance(exc, ProtectedError) and getattr(exc.__cause__, "sqlstate", None) != "23503":
                raise
            self.message_user(request, "A central passou a ter registros vinculados. Para suspender o atendimento, desative a central.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:webhook_centralposvenda_changelist"))

    def changelist_view(self, request, extra_context=None):
        try:
            return super().changelist_view(request, extra_context)
        except IntegrityError as exc:
            vinculado = isinstance(exc, ProtectedError) or getattr(exc.__cause__, "sqlstate", None) == "23503"
            if request.POST.get("action") != "delete_selected" or not vinculado:
                raise
            self.message_user(request, "Uma das centrais passou a ter registros vinculados. Reabra a lista para conferir.", messages.ERROR)
            return HttpResponseRedirect(request.path)


class SomenteConsulta(admin.ModelAdmin):
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Conversa)
class ConversaAdmin(ConsultasRelacionadasMixin, SomenteConsulta):
    campo_vinculo = "conversa"
    consultas = {
        "pedidos": (models.PedidoConversa, ("numero", "codigo_filial"), ("numero",)),
        "etiquetas": (models.EtiquetaConversa, ("etiqueta",), ("etiqueta",)),
        "recuperacao": (models.FallbackContato, ("mensagem_fila_id", "estado", "atualizado_em", "wamid_original"),
                        ("-atualizado_em", "mensagem_fila_id")),
    }
    readonly_fields = ("consultas_do_registro",)
    list_display = ("id_conversa", "central", "chat_id", "etapa_atual", "status_ativa", "turnos_sem_avanco", "processing", "iniciou_em")
    list_filter = ("central", "status_ativa", "etapa_atual", "processing")
    ordering = ("-id_conversa",)
    search_fields = ("=chat__cliente__waid_telefone", "chat__cliente__nome_titular")


@admin.register(models.Cliente)
class ClienteAdmin(SomenteConsulta):
    list_display = ("id_cliente", "nome_titular", "waid_telefone", "username")
    search_fields = ("nome_titular", "waid_telefone", "username", "=cpf_titular")
    ordering = ("-id_cliente",)


@admin.register(models.Chat)
class ChatAdmin(SomenteConsulta):
    list_display = ("id_chat", "central", "cliente")
    list_filter = ("central",)
    ordering = ("-id_chat",)


@admin.register(models.Etapa)
class EtapaAdmin(SomenteConsulta):
    list_display = ("id_etapa", "nome_etapa", "encerra_automaticamente", "bloqueio_dias")
    ordering = ("id_etapa",)


@admin.register(models.EtapaTransicao)
class TransicaoAdmin(SomenteConsulta):
    list_display = ("origem", "evento", "destino")
    list_filter = ("origem", "destino")
    ordering = ("origem_id", "evento")


@admin.register(models.AtendimentoPosVenda)
class AtendimentoAdmin(SomenteConsulta):
    list_display = ("conversa", "nome_titular", "produto", "assunto", "perdeu_nota")
    list_filter = ("produto", "assunto", "perdeu_nota")
    ordering = ("-conversa_id",)


@admin.register(models.FilaMensagens)
class FilaAdmin(SomenteConsulta):
    list_display = ("id_mensagem", "central", "conversa_id", "tipo_mensagem", "status", "retry_count", "received_data_hora")
    list_filter = ("central", "status", "tipo_mensagem")
    search_fields = ("=id_hash_msg", "=cliente_telefone", "=user_id_origem")
    ordering = ("-id_mensagem",)


@admin.register(models.HistoricoMensagens)
class HistoricoAdmin(SomenteConsulta):
    list_display = ("id_mensagem", "conversa", "etapa", "quem_enviou", "tipo_mensagem", "status_envio", "received_data_hora")
    list_filter = ("quem_enviou", "status_envio", "etapa")
    search_fields = ("=id_hash_msg", "=id_hash_cliente_origem")
    ordering = ("-id_mensagem",)


@admin.register(models.FilialCompra)
class FilialAdmin(SomenteConsulta):
    list_display = ("codigo", "nome", "grupo")
    list_filter = ("grupo",)
    search_fields = ("codigo", "nome")
    ordering = ("codigo",)


@admin.register(models.SolicitacaoContato)
class SolicitacaoAdmin(SomenteConsulta):
    list_display = ("conversa", "motivo", "etapa_retomada", "erros_cliente")


@admin.register(models.WebhookFloodEvento)
class FloodAdmin(SomenteConsulta):
    list_display = ("id_hash_msg", "central", "wa_id_cliente", "received_at")
    list_filter = ("central",)
    ordering = ("-received_at",)


@admin.register(models.CacheControle)
class CacheAdmin(SomenteConsulta):
    list_display = ("nome", "versao", "atualizado_em")


@admin.register(models.ContatoInterno)
class ContatoInternoAdmin(admin.ModelAdmin):
    list_display = ("waid_telefone",)
    search_fields = ("=waid_telefone",)

    def get_readonly_fields(self, request, obj=None):
        # O telefone é a chave. Alterá-lo em uma edição criaria outro registro.
        return ("waid_telefone",) if obj is not None else ()
```

## 52. `callback/webhook/models.py` (alterar)

```python
"""Mapeamento de leitura e administração do schema chatbot, criado pelo DDL do projeto."""
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models.functions import Right


class CentralPosVenda(models.Model):
    validar_telefone_setor = RegexValidator(
        r"\A[1-9][0-9]{7,14}\Z", "Informe de 8 a 15 dígitos, com DDI e sem zero inicial.",
    )

    id_central = models.AutoField(primary_key=True)
    nome = models.CharField("nome da central")
    nome_agente = models.CharField("nome do agente")
    genero_agente = models.CharField("gênero do agente", choices=[("masculino", "Masculino"), ("feminino", "Feminino")])
    ativa = models.BooleanField(default=True, help_text="Habilita o atendimento desta central.")
    waba_id = models.CharField("WABA ID", help_text="ID da conta empresarial (messaging_account_id).")
    phone_number_id = models.CharField("Phone Number ID", unique=True)
    waac_id = models.CharField(
        "WAAC ID", unique=True, blank=True, null=True,
        validators=[RegexValidator(r"\A[1-9][0-9]*\Z", "Informe um ID numérico positivo, sem zero inicial.")],
        help_text="Informe o ID de conta verificado para este número. Em branco, o envio usa o Phone Number ID.",
    )
    telefone = models.CharField("telefone da central", unique=True)
    telefone_baratao = models.CharField(
        "telefone do pós-venda do Baratão", blank=True, null=True, validators=[validar_telefone_setor],
    )
    telefone_atacadao = models.CharField(
        "telefone do pós-venda do Atacadão", blank=True, null=True, validators=[validar_telefone_setor],
    )
    id_fuso = models.IntegerField("ID do fuso", blank=True, null=True, editable=False)
    nome_fuso = models.TextField("nome do fuso", blank=True, null=True, editable=False)
    fuso_verificado_em = models.DateTimeField("fuso verificado em", blank=True, null=True, editable=False)

    def clean(self):
        super().clean()
        erros = {}
        if self.waac_id and self.waac_id == self.phone_number_id:
            erros["waac_id"] = "O WAAC ID deve ser diferente do Phone Number ID."
        if self.ativa:
            for campo in ("telefone_baratao", "telefone_atacadao"):
                if not getattr(self, campo):
                    erros[campo] = "Informe o telefone desta rede para ativar a central."
        if self.telefone_baratao and self.telefone_baratao == self.telefone_atacadao:
            erros["telefone_atacadao"] = "Informe números diferentes para o Baratão e o Atacadão."
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return self.nome

    class Meta:
        managed = False
        db_table = "central_pos_venda"
        verbose_name = "central de pós-venda"
        verbose_name_plural = "centrais de pós-venda"



class Cliente(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    waid_telefone = models.CharField(unique=True, blank=True, null=True)
    username = models.TextField(blank=True, null=True)
    username_observado_em = models.DateTimeField(blank=True, null=True)
    nome_titular = models.TextField(blank=True, null=True)
    cpf_titular = models.CharField(max_length=11, blank=True, null=True)
    cidade_loja_compra = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nome_titular or f"Cliente {self.pk}"

    class Meta:
        managed = False
        db_table = "cliente"
        indexes = [models.Index(fields=["cpf_titular", "id_cliente"], name="cliente_cpf_conciliacao",
                                condition=models.Q(cpf_titular__isnull=False))]


class ContatoInterno(models.Model):
    waid_telefone = models.CharField("telefone", primary_key=True)

    class Meta:
        managed = False
        db_table = "contato_interno"
        verbose_name = "contato interno"


class Chat(models.Model):
    id_chat = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, models.PROTECT, db_column="id_cliente")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")

    class Meta:
        managed = False
        db_table = "chat"
        unique_together = (("cliente", "central"), ("id_chat", "central"))


class Etapa(models.Model):
    id_etapa = models.IntegerField(primary_key=True)
    nome_etapa = models.CharField(max_length=100, unique=True)
    encerra_automaticamente = models.BooleanField(default=False)
    bloqueio_dias = models.SmallIntegerField(default=0)

    def __str__(self):
        return f"{self.pk} · {self.nome_etapa}"

    class Meta:
        managed = False
        db_table = "etapa"


class EtapaTransicao(models.Model):
    id_transicao = models.AutoField(primary_key=True)
    origem = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_origem", related_name="saidas")
    evento = models.CharField(max_length=100)
    destino = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_destino", related_name="entradas")

    class Meta:
        managed = False
        db_table = "etapa_transicao"
        unique_together = (("origem", "evento"),)
        verbose_name = "transição de etapa"
        verbose_name_plural = "mapa de transições"


class Conversa(models.Model):
    id_conversa = models.AutoField(primary_key=True)
    # O SQL garante que a central seja a do chat por uma chave estrangeira composta.
    chat = models.ForeignKey(Chat, models.PROTECT, db_column="id_chat")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central", db_constraint=False)
    etapa_atual = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_atual")
    iniciou_em = models.DateTimeField()
    finalizou_em = models.DateTimeField(null=True)
    status_ativa = models.BooleanField(default=True)
    motivo_encerramento = models.TextField(null=True)
    last_interaction_at = models.DateTimeField(null=True)
    last_message_from = models.CharField(null=True)
    processing = models.BooleanField(default=False)
    processing_started_at = models.DateTimeField(null=True)
    lock_version = models.IntegerField(default=0)
    turnos_sem_avanco = models.IntegerField(default=0)

    def __str__(self):
        return f"Conversa {self.pk}"

    class Meta:
        managed = False
        db_table = "conversa"


class AtendimentoPosVenda(models.Model):
    class Situacao(models.TextChoices):
        NAO_ENCAMINHADO = "Não encaminhado", "Não encaminhado"
        JA_ENCAMINHADO = "Já encaminhado", "Já encaminhado"
        AGUARDANDO_CLIENTE = "Aguardando cliente", "Aguardando cliente"
        RESOLVIDO = "Resolvido", "Resolvido"

    conversa = models.OneToOneField(Conversa, models.PROTECT, primary_key=True, db_column="id_conversa")
    nome_titular = models.TextField(null=True)
    cpf_titular = models.CharField(max_length=11, null=True)
    cidade_loja_compra = models.TextField(null=True)
    produto = models.TextField(null=True)
    assunto = models.CharField(null=True)
    perdeu_nota = models.BooleanField(null=True)
    foi_a_loja = models.BooleanField(null=True)
    detalhes = models.TextField(null=True)
    encaminhado_baratao = models.CharField(null=True)
    encaminhado_atacadao = models.CharField(null=True)
    telefone_compartilhado = models.CharField(null=True, editable=False)
    situacao = models.TextField("situação", choices=Situacao, default=Situacao.NAO_ENCAMINHADO)
    observacao = models.TextField("observação", null=True, blank=True)

    class Meta:
        managed = False
        db_table = "atendimento_pos_venda"
        verbose_name = "atendimento de pós-venda"


class ProdutoCatalogo(models.Model):
    codigo_produto = models.IntegerField(primary_key=True)
    nome_produto = models.TextField()
    categoria = models.TextField(choices=[("moveis", "Móveis"), ("estofado", "Estofado")])

    class Meta:
        managed = False
        db_table = "catalogo"


class FilialCompra(models.Model):
    codigo = models.TextField(primary_key=True)
    nome = models.TextField()

    grupo = models.TextField(choices=[("Atacadão", "Atacadão"), ("Baratão", "Baratão")])

    def __str__(self):
        return f"{self.codigo} · {self.nome}"

    class Meta:
        managed = False
        db_table = "filial_compra"
        verbose_name = "filial de compra"
        verbose_name_plural = "filiais de compra"


class PedidoConversa(models.Model):
    id_nota = models.BigAutoField(primary_key=True)
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    numero = models.TextField()
    codigo_filial = models.GeneratedField(expression=Right("numero", 2), output_field=models.TextField(), db_persist=True)

    class Meta:
        managed = False
        db_table = "pedido_conversa"
        unique_together = (("conversa", "numero"),)
        verbose_name = "pedido da conversa"


class NotaProduto(models.Model):
    pk = models.CompositePrimaryKey("nota", "produto")
    nota = models.ForeignKey(PedidoConversa, models.PROTECT, db_column="id_nota")
    produto = models.ForeignKey(ProdutoCatalogo, models.PROTECT, db_column="codigo_produto")
    qtd = models.IntegerField("quantidade", default=1, validators=[MinValueValidator(1)])

    class Meta:
        managed = False
        db_table = "nota_produtos"
        verbose_name = "produto da nota"


class EtiquetaConversa(models.Model):
    pk = models.CompositePrimaryKey("conversa", "etiqueta")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    etiqueta = models.CharField()

    class Meta:
        managed = False
        db_table = "etiqueta_conversa"
        verbose_name = "etiqueta da conversa"


class FilaMensagens(models.Model):
    id_mensagem = models.AutoField(primary_key=True)
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa", null=True)
    cliente = models.ForeignKey(Cliente, models.PROTECT, db_column="id_cliente", null=True)
    cliente_telefone = models.CharField(null=True)
    user_id_origem = models.TextField(null=True)
    username_origem = models.TextField(null=True)
    id_hash_msg = models.CharField(unique=True)
    received_data_hora = models.DateTimeField()
    tipo_mensagem = models.CharField()
    conteudo_texto = models.TextField(null=True)
    interativo = models.JSONField(null=True)
    status = models.CharField(default="pending")
    retry_count = models.IntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    processing_started_at = models.DateTimeField(null=True)
    last_error = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "fila_mensagens"
        verbose_name_plural = "fila de mensagens"


class HistoricoMensagens(models.Model):
    id_mensagem = models.BigAutoField(primary_key=True)
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    etapa = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa")
    received_data_hora = models.DateTimeField()
    quem_enviou = models.CharField()
    id_hash_msg = models.CharField(unique=True)
    mensagem_fila = models.ForeignKey(FilaMensagens, models.SET_NULL, db_column="id_mensagem_fila", null=True)
    id_hash_cliente_origem = models.CharField(null=True)
    parte_resposta = models.SmallIntegerField(default=1)
    tipo_mensagem = models.CharField()
    conteudo_texto = models.TextField(null=True)
    interativo = models.JSONField(null=True)
    tipo_destinatario = models.TextField(null=True)
    valor_destinatario = models.TextField(null=True)
    status_envio = models.CharField(null=True)

    class Meta:
        managed = False
        db_table = "historico_mensagens"
        verbose_name_plural = "histórico de mensagens"


class IdentidadeBsuid(models.Model):
    pk = models.CompositePrimaryKey("central", "user_id")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    user_id = models.TextField()
    cliente = models.ForeignKey(Cliente, models.PROTECT, db_column="id_cliente")
    wamid_origem = models.TextField()
    suspender_telefone = models.BooleanField(default=False)
    vigente = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "identidade_bsuid"
        verbose_name = "identidade por BSUID"


class SolicitacaoContato(models.Model):
    conversa = models.OneToOneField(Conversa, models.PROTECT, db_column="id_conversa", primary_key=True)
    motivo = models.TextField()
    etapa_retomada = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_retomada")
    bsuid_destino = models.TextField()
    wamid_solicitacao = models.TextField()
    wamids_aceitos = ArrayField(models.TextField())
    erros_cliente = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "solicitacao_contato"
        verbose_name = "solicitação de contato"
        verbose_name_plural = "solicitações de contato"


class FallbackContato(models.Model):
    pk = models.CompositePrimaryKey("conversa", "mensagem_fila")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    mensagem_fila = models.ForeignKey(FilaMensagens, models.PROTECT, db_column="id_mensagem_fila")
    wamid_original = models.TextField(null=True, unique=True)
    estado = models.TextField()
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "fallback_contato"
        verbose_name = "recuperação de contato"


class CacheControle(models.Model):
    nome = models.CharField(primary_key=True)
    versao = models.BigIntegerField(default=1)
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "cache_controle"
        verbose_name_plural = "versões do cache"


class ClienteBloqueadoMeta(models.Model):
    pk = models.CompositePrimaryKey("central", "wa_id_cliente")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    wa_id_cliente = models.CharField()
    bloqueado_em = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "cliente_bloqueado_meta"
        verbose_name = "bloqueio na Meta"


class WebhookFloodEvento(models.Model):
    id_hash_msg = models.CharField(primary_key=True)
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    wa_id_cliente = models.CharField()
    received_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "webhook_flood_evento"
        verbose_name_plural = "eventos de proteção contra flood"


class MonitoramentoAcesso(models.Model):
    pk = models.CompositePrimaryKey("usuario", "central")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, db_column="id_usuario_django")
    central = models.ForeignKey(CentralPosVenda, models.CASCADE, db_column="id_central")

    class Meta:
        managed = False
        db_table = "monitoramento_acesso"
        verbose_name = "acesso ao monitoramento"


class ConsumoMensalMeta(models.Model):
    pk = models.CompositePrimaryKey("central", "mes_referencia")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    mes_referencia = models.DateField()
    waba_id = models.CharField()
    phone_number_id = models.CharField()
    fuso_horario = models.TextField()
    qtd_gratuitas = models.BigIntegerField()
    qtd_cobradas_meta = models.BigIntegerField()
    valor_meta = models.DecimalField(max_digits=14, decimal_places=6, null=True)
    moeda = models.CharField(max_length=3, null=True)
    consultado_ate = models.DateTimeField()
    consolidado_em = models.DateTimeField(null=True)
    timezone_id = models.IntegerField(null=True)
    data_hora_inicio = models.DateTimeField(null=True)
    data_hora_fim = models.DateTimeField(null=True)
    qtd_janela_gratuita = models.BigIntegerField(null=True)
    qtd_franquia_consumida = models.BigIntegerField(null=True)
    ultimo_sucesso_em = models.DateTimeField(null=True)
    status_apuracao = models.TextField(default="pendente_detalhamento")
    data_proxima_consolidacao = models.DateField(null=True)
    ultima_decisao_consolidacao_em = models.DateTimeField(null=True)
    franquia_meta_mensal = models.IntegerField(default=1000)
    beneficio_esl_mensal = models.IntegerField(default=1000)
    tarifa_referencia_brl = models.DecimalField(max_digits=12, decimal_places=6, default="0.035")
    tarifa_vigencia = models.DateField()
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "consumo_mensal_meta"
        verbose_name = "consumo mensal da Meta"


class ConsumoMetaColeta(models.Model):
    pk = models.CompositePrimaryKey("central", "periodo")
    central = models.ForeignKey(CentralPosVenda, models.CASCADE, db_column="id_central")
    periodo = models.CharField()
    proxima_consulta_em = models.DateTimeField()
    ultima_tentativa_em = models.DateTimeField(null=True)
    falhas_consecutivas = models.IntegerField(default=0)
    ultimo_erro = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "consumo_meta_coletas"
        verbose_name = "coleta de consumo"
```

## 53. `callback/webhook/services/bloqueio_meta_guard.py` (alterar)

```python
import logging

from django.http import JsonResponse

from core.database.connection_aws import get_conn
from core.integrations.whatsapp.tools.usuarios import bloquear_usuario_meta
from core.logging_config import short_value
from core.repositories.seguranca.bloqueio_meta import (
    consultar_protecao_remetente,
)


logger = logging.getLogger("webhook.bloqueio_meta_guard")


def verificar_protecao_remetente(
    wa_id_cliente,
    phone_id_unidade,
    identificadores,
    conta_origem,
):
    """
    Intercepta apenas a denylist existente.

    Repetição de etapa é encaminhamento ao pós-venda, decidido pelo worker;
    não promove bloqueio na Meta.

    O banco é confirmado antes da chamada externa à Meta. Se a Meta recusar,
    a mensagem continua sendo ignorada e a próxima mensagem fará nova
    tentativa.
    """
    if not wa_id_cliente or not phone_id_unidade:
        return None, wa_id_cliente

    consulta = _consultar_cliente_marcado_para_bloqueio(
        wa_id_cliente,
        phone_id_unidade,
        identificadores=identificadores,
        conta_origem=conta_origem,
    )

    if not consulta["banco_ok"]:
        return JsonResponse(
            {
                "status": "unavailable",
                "reason": "blocklist_validation_unavailable",
            },
            status=503,
        ), None

    if consulta["protecao"] is None:
        return JsonResponse({"status": "ignored", "reason": "central_incompativel"}), None

    central, chave_flood = consulta["protecao"]
    if central is None:
        return None, chave_flood or wa_id_cliente

    meta_ok = False

    try:
        bloquear_usuario_meta(wa_id_cliente, phone_id_unidade, central=central)
        meta_ok = True
        logger.warning(
            "bloqueio_meta_reconfirmado | acao=bloquear_novamente "
            "wa_id_cliente=%s phone_id_unidade=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
        )

    except Exception as exc:
        logger.warning(
            "bloqueio_meta_retentativa_falhou | "
            "acao=ignorar_e_tentar_na_proxima_mensagem "
            "wa_id_cliente=%s phone_id_unidade=%s erro=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
            exc,
        )

    logger.warning(
        "mensagem_ignorada | motivo=cliente_marcado_bloqueio_meta "
        "acao=nao_enfileirar wa_id_cliente=%s phone_id_unidade=%s meta_ok=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
        meta_ok,
    )
    return JsonResponse({
        "status": "ignored",
        "reason": "cliente_marcado_bloqueio_meta",
    }), None


def _consultar_cliente_marcado_para_bloqueio(
    wa_id_cliente,
    phone_id_unidade,
    identificadores,
    conta_origem,
):
    conn = None

    try:
        conn = get_conn(application_name="webhook_chatbot")
        cursor = conn.cursor()

        protecao = consultar_protecao_remetente(
            identificadores,
            phone_id_unidade,
            conta_origem,
            cursor,
        )

        conn.commit()
        return {
            "banco_ok": True,
            "protecao": protecao,
        }

    except Exception as exc:
        if conn:
            conn.rollback()

        logger.exception(
            "bloqueio_meta_consulta_falhou | "
            "acao=retornar_503_para_reentrega "
            "wa_id_cliente=%s phone_id_unidade=%s erro=%s",
            short_value(wa_id_cliente),
            short_value(phone_id_unidade),
            exc,
        )
        return {
            "banco_ok": False,
            "central": None,
        }

    finally:
        if conn:
            conn.close()
```

## 54. `core/integrations/whatsapp/pywa_functions/cliente.py` (alterar)

```python
from contextlib import contextmanager
from contextvars import ContextVar

from core.integrations.whatsapp.remetente import WhatsAppCentral

from core.integrations.whatsapp.messages.tratamentos.composicao import (
    aplicar_prefixo_retorno,
)
from core.integrations.whatsapp.tools.config import (
    TOKEN_USUARIO_META,
    get_meta_graph_api_version,
)

_PREFIXO_MENSAGEM_BOT = ContextVar(
    "prefixo_mensagem_bot",
    default=None,
)
_ANTES_DO_PRIMEIRO_ENVIO = ContextVar("antes_do_primeiro_envio", default=None)


def conta_wa(phone_id, token=TOKEN_USUARIO_META, *, session=None):
    phone_id = _normalizar_phone_id(phone_id)

    opcoes = {"session": session} if session is not None else {}
    cliente = WhatsAppCentral(
        token=token,
        phone_id=phone_id,
        api_version=get_meta_graph_api_version(),
        **opcoes,
    )

    if _PREFIXO_MENSAGEM_BOT.get() or _ANTES_DO_PRIMEIRO_ENVIO.get():
        return _ClienteWhatsAppDoTurno(cliente)

    return cliente


@contextmanager
def antes_do_primeiro_envio(acao):
    """Adia uma ação até o envio efetivo, uma vez por escopo, sem criar tarefa."""
    executada = False

    def executar_uma_vez():
        nonlocal executada
        if not executada:
            # Uma falha também consome a tentativa opcional deste turno.
            executada = True
            acao()

    token = _ANTES_DO_PRIMEIRO_ENVIO.set(executar_uma_vez)
    try:
        yield
    finally:
        _ANTES_DO_PRIMEIRO_ENVIO.reset(token)


@contextmanager
def usar_prefixo_mensagem_bot(prefixo):
    """Limita o prefixo à resolução corrente, inclusive sob exceção."""
    prefixo_normalizado = prefixo if isinstance(prefixo, str) else None
    token = _PREFIXO_MENSAGEM_BOT.set(prefixo_normalizado or None)

    try:
        yield
    finally:
        _PREFIXO_MENSAGEM_BOT.reset(token)


def aplicar_prefixo_mensagem_bot(texto, prefixo=None):
    prefixo = prefixo if prefixo is not None else _PREFIXO_MENSAGEM_BOT.get()

    return aplicar_prefixo_retorno(texto, prefixo)


class _ClienteWhatsAppDoTurno:
    """Aplica prefixo e ação de envio apenas no escopo corrente do worker."""

    def __init__(self, cliente):
        self._cliente = cliente

    def send_message(self, *args, **kwargs):
        return self._enviar_com_prefixo(
            self._cliente.send_message,
            args,
            kwargs,
        )

    def request_contact_info(self, *args, **kwargs):
        return self._enviar_com_prefixo(
            self._cliente.request_contact_info,
            args,
            kwargs,
        )

    @staticmethod
    def _enviar_com_prefixo(metodo, args, kwargs):
        if "text" in kwargs:
            kwargs = dict(kwargs)
            kwargs["text"] = aplicar_prefixo_mensagem_bot(kwargs["text"])

        antes_de_enviar = _ANTES_DO_PRIMEIRO_ENVIO.get()
        if antes_de_enviar is not None:
            antes_de_enviar()

        return metodo(*args, **kwargs)

    def send_carousel(self, *args, **kwargs):
        kwargs = dict(kwargs)
        if "body" in kwargs:
            kwargs["body"] = aplicar_prefixo_mensagem_bot(kwargs["body"])
        return self._enviar_com_prefixo(self._cliente.send_carousel, args, kwargs)

    def __getattr__(self, nome):
        return getattr(self._cliente, nome)


def _normalizar_phone_id(phone_id):
    if phone_id is None:
        raise ValueError("phone_id da unidade nao informado")

    phone_id = str(phone_id).strip()

    if not phone_id:
        raise ValueError("phone_id da unidade vazio")

    return phone_id
```

## 55. `core/integrations/whatsapp/tools/ativando_numero.py` (alterar)

```python

import logging

import requests

from core.integrations.whatsapp.tools.config import (
    construir_url_graph_api,
    get_meta_http_timeout,
    get_phone_registration_pin,
    get_token_usuario_meta,
)
from core.integrations.whatsapp.remetente import recurso_registro_meta
from core.logging_config import short_value


logger = logging.getLogger("whatsapp.registro")


def registrar_numero_whatsapp(phone_number_id, pin=None, *, id_registro=None):
    # No cadastro o recurso validado ainda não está disponível no banco.
    recurso = id_registro or recurso_registro_meta(phone_number_id)
    url = construir_url_graph_api(f"{recurso}/register")

    headers = {
        "Authorization": f"Bearer {get_token_usuario_meta()}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "pin": pin or get_phone_registration_pin(),
    }

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=get_meta_http_timeout(),
    )

    # resposta = _normalizar_resposta(response)
    #
    # print(response)
    # print(response.json())
    # print(resposta)

    logger.info(
        "whatsapp_numero_registro_resposta | acao=registrar_numero phone_number_id=%s status=%s",
        short_value(phone_number_id),
        response.status_code,
    )

    return response.status_code, _normalizar_resposta(response)


def _normalizar_resposta(response):
    try:
        return response.json()

    except ValueError:
        return {
            "success": False,
            "text": response.text,
        }

# registrar_numero_whatsapp(1265716939963855)









# def consultar_status_numero(phone_number_id):
#     url = construir_url_graph_api(phone_number_id)
#
#     headers = {
#         "Authorization": f"Bearer {get_token_usuario_meta()}",
#     }
#
#     response = requests.get(
#         url,
#         headers=headers,
#         params={
#             "fields": "display_phone_number,verified_name,status,name_status"
#         },
#         timeout=get_meta_http_timeout(),
#     )
#
#     print("HTTP:", response.status_code)
#     print(response.json())
#
#     return response.status_code, response.json()
#
# consultar_status_numero(1238343616032627)
```

## 56. `core/integrations/whatsapp/tools/config.py` (alterar)

```python
import re

from core.config_env import env_int, env_optional, env_required


_META_GRAPH_API_VERSION_PATTERN = re.compile(r"^[1-9]\d*\.0$")


TOKEN_USUARIO_META = env_required("META_ACCESS_TOKEN")


def _normalizar_meta_graph_api_version(value):
    version = str(value or "").strip()

    if not _META_GRAPH_API_VERSION_PATTERN.fullmatch(version):
        raise RuntimeError(
            "Valor invalido em META_GRAPH_API_VERSION: use o formato 27.0, "
            "sem o prefixo v"
        )

    return version


META_GRAPH_API_VERSION = _normalizar_meta_graph_api_version(
    env_required("META_GRAPH_API_VERSION")
)
PHONE_REGISTRATION_PIN = env_optional("META_PHONE_REGISTRATION_PIN")

META_HTTP_TIMEOUT = (
    env_int("META_HTTP_CONNECT_TIMEOUT_SECONDS", 30),
    env_int("META_HTTP_READ_TIMEOUT_SECONDS", 35),
)


def get_token_usuario_meta():
    return TOKEN_USUARIO_META


def get_meta_graph_api_version():
    return META_GRAPH_API_VERSION


def construir_url_graph_api(caminho):
    """Monta uma URL versionada sem espalhar a versão pelo projeto."""
    caminho = str(caminho or "").strip().strip("/")

    if not caminho:
        raise ValueError("caminho da Graph API nao informado")

    # O prefixo "v" pertence à URL da Graph API.
    return (
        "https://graph.facebook.com/"
        f"v{get_meta_graph_api_version()}/{caminho}"
    )


def get_phone_registration_pin():
    if not PHONE_REGISTRATION_PIN:
        raise RuntimeError(
            "Variavel de ambiente obrigatoria ausente: "
            "META_PHONE_REGISTRATION_PIN"
        )

    return PHONE_REGISTRATION_PIN


def get_meta_http_timeout():
    return META_HTTP_TIMEOUT
```

## 57. `core/integrations/whatsapp/tools/desativando_numero.py` (alterar)

```python
import logging

import requests

from core.integrations.whatsapp.tools.config import (
    construir_url_graph_api,
    get_meta_http_timeout,
    get_token_usuario_meta,
)
from core.integrations.whatsapp.remetente import recurso_registro_meta
from core.logging_config import short_value


logger = logging.getLogger("whatsapp.registro")


def desregistrar_numero_whatsapp(phone_number_id):
    url = construir_url_graph_api(f"{recurso_registro_meta(phone_number_id)}/deregister")

    headers = {
        "Authorization": f"Bearer {get_token_usuario_meta()}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        timeout=get_meta_http_timeout(),
    )

    # print(response)

    logger.info(
        "whatsapp_numero_desregistro_resposta | acao=desregistrar_numero phone_number_id=%s status=%s",
        short_value(phone_number_id),
        response.status_code,
    )

    return response.status_code, _normalizar_resposta(response)


def _normalizar_resposta(response):
    try:
        return response.json()

    except ValueError:
        return {
            "success": response.ok,
            "text": response.text,
        }

# desregistrar_numero_whatsapp(1376957325492184)
```

## 58. `core/integrations/whatsapp/tools/usuarios.py` (alterar)

```python
import logging

from core.database.connection_aws import get_conn
from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.remetente import usar_remetente_central
from core.logging_config import short_value
from core.repositories.seguranca.bloqueio_meta import buscar_central_para_bloqueio


logger = logging.getLogger("whatsapp.block")


def cliente_de_bloqueio(phone_id_unidade, central=None):
    phone_id = str(phone_id_unidade).strip()
    if central is None:
        # Chamadores sem contexto de turno (inclusive o desbloqueio administrativo).
        with get_conn(application_name="whatsapp_bloqueio") as conn, conn.cursor() as cursor:
            central = buscar_central_para_bloqueio(phone_id, cursor)
        if central is None:
            raise ValueError("Phone Number ID sem central cadastrada para bloqueio.")

    with usar_remetente_central(central, phone_id):
        return conta_wa(phone_id)


def bloquear_usuario_meta(wa_id_cliente, phone_id_unidade, *, central=None):
    cliente_wa = cliente_de_bloqueio(phone_id_unidade, central)
    resultado = cliente_wa.block_users(users=[str(wa_id_cliente)])

    if resultado.errors or resultado.failed_users or not resultado.added_users:
        raise RuntimeError("A Meta não confirmou o bloqueio do contato.")

    logger.warning(
        "whatsapp_usuario_bloqueado | acao=bloquear wa_id_cliente=%s phone_id_unidade=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
    )

    return resultado


def desbloquear_usuario_meta(wa_id_cliente, phone_id_unidade):
    cliente_wa = cliente_de_bloqueio(phone_id_unidade, central=None)
    resultado = cliente_wa.unblock_users(users=[str(wa_id_cliente)])

    if not resultado.removed_users:
        raise RuntimeError("A Meta não confirmou o desbloqueio do contato.")

    logger.warning(
        "whatsapp_usuario_desbloqueado | acao=desbloquear wa_id_cliente=%s phone_id_unidade=%s",
        short_value(wa_id_cliente),
        short_value(phone_id_unidade),
    )

    return resultado
```

## 59. `core/repositories/seguranca/comparacao_bloqueios.py` (alterar)

```python
"""Operações SQL isoladas; conexão e transação pertencem ao chamador.

Extração organizacional: preserva os nomes do esquema usados pelo consumidor.
"""


def iniciar_leitura_consistente(cursor):
    cursor.execute(
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;"
    )


def listar_unidades_para_comparacao(cursor):
    cursor.execute(
        """
        SELECT id_central, nome, waba_id, phone_number_id
        FROM chatbot.central_pos_venda
        WHERE waba_id IS NOT NULL
          AND BTRIM(waba_id) <> ''
          AND phone_number_id IS NOT NULL
          AND BTRIM(phone_number_id) <> ''
        ORDER BY id_central;
        """
    )
    return cursor.fetchall()


def listar_bloqueios_para_comparacao(cursor):
    cursor.execute(
        """
        SELECT m.wa_id_cliente, u.id_central, u.nome, u.waba_id, u.phone_number_id,
               COALESCE(telefone.id_cliente, alias.id_cliente),
               COALESCE(telefone.nome_titular, privado.nome_titular)
        FROM chatbot.cliente_bloqueado_meta m
        JOIN chatbot.central_pos_venda u USING (id_central)
        LEFT JOIN chatbot.cliente telefone ON telefone.waid_telefone=m.wa_id_cliente
        LEFT JOIN chatbot.identidade_bsuid alias
          ON alias.id_central=m.id_central AND alias.user_id=m.wa_id_cliente
        LEFT JOIN chatbot.cliente privado ON privado.id_cliente=alias.id_cliente
        ORDER BY u.id_central, m.wa_id_cliente;
        """
    )
    return cursor.fetchall()
```

## 60. `core/repositories/unidades/consultas.py` (alterar)

```python
import logging


logger = logging.getLogger("db.unidades.consultas")


class UnidadeDesativada(Exception):
    """Suspensão administrativa; não é falha nem motivo para apagar a fila."""


def unidade_habilitada(id_unidade, cursor):
    """Leitura atual para lotes já carregados antes de uma desativação."""
    cursor.execute(
        "SELECT ativa IS TRUE FROM chatbot.central_pos_venda WHERE id_central = %s",
        (id_unidade,),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def exigir_unidade_habilitada_por_phone_id(phone_number_id, cursor):
    """Retorna o ID ativo, None para ausente e sinaliza a suspensão ao worker."""
    cursor.execute(
        "SELECT id_central, ativa FROM chatbot.central_pos_venda WHERE phone_number_id = %s",
        (phone_number_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    if not row[1]:
        raise UnidadeDesativada("Central de pós-venda desativada")
    return row[0]


def pegar_unidades(cursor):
    cursor.execute("""
        SELECT phone_number_id, id_central
        FROM chatbot.central_pos_venda
        WHERE ativa = TRUE
    """)

    resultado = {row[0]: row[1] for row in cursor.fetchall()}

    logger.debug("unidades_consultadas | total=%s", len(resultado))

    return resultado


def buscar_id_unidade_por_phone_id(phone_number_id, cursor):
    cursor.execute("""
        SELECT id_central
        FROM chatbot.central_pos_venda
        WHERE phone_number_id = %s
          AND ativa = TRUE
    """, (phone_number_id,))

    resultado = cursor.fetchone()
    logger.debug(
        "unidade_consulta | acao=buscar_por_phone phone_number_id=%s encontrada=%s",
        phone_number_id,
        bool(resultado),
    )
    return resultado[0] if resultado else None


def buscar_id_registro_meta(phone_number_id, cursor):
    """Seleciona o recurso para registrar ou desregistrar o número comercial."""
    cursor.execute("""
        SELECT COALESCE(waac_id, phone_number_id)
        FROM chatbot.central_pos_venda WHERE phone_number_id=%s
    """, (phone_number_id,))
    linha = cursor.fetchone()
    return linha[0] if linha else phone_number_id
```

## 61. `tests/test_remetente_central.py` (criar)

```python
"""Contratos HTTP da conta empresarial, sem chamadas à Meta."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.remetente import WhatsAppCentral, usar_remetente_central
from tests.test_etapa1_pos_venda import contexto, ENV
from tests.test_etapa3_pos_venda import contexto_produto
from workers.worker_flow.response_flow.flow_sender import flow_sender


class RemetenteCentralTests(unittest.TestCase):
    def setUp(self):
        self.requisicoes = []

    def sessao(self):
        def responder(request):
            corpo = json.loads(request.content)
            self.requisicoes.append((request.url.path, corpo))
            if corpo.get("status") == "read":
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": corpo["to"], "wa_id": corpo["to"]}],
                "messages": [{"id": "wamid.teste"}],
            })
        return self.enterContext(httpx.Client(transport=httpx.MockTransport(responder)))

    def test_turno_texto_botoes_lista_cta_e_carrossel(self):
        def criar_cliente(**opcoes):
            return WhatsAppCentral(**{**opcoes, "session": self.sessao(), "token": "teste"})
        self.enterContext(patch("core.integrations.whatsapp.pywa_functions.cliente.WhatsAppCentral",
                                side_effect=criar_cliente))
        self.enterContext(patch.dict(os.environ, ENV))
        encaminhar_baratao = contexto(etapa=6, tipo="audio", turnos=3)
        encaminhar_baratao["grupos_das_notas"] = {"Baratão"}
        for ctx, tipo in (
            (contexto(apresentacao=True), "text"), (contexto_produto("talvez"), "button"),
            (contexto_produto("móveis"), "list"), (encaminhar_baratao, "cta_url"),
            (contexto(tipo="audio", turnos=3), "carousel"),
        ):
            for waac in (None, "771"):
                with self.subTest(tipo=tipo, waac=waac):
                    ctx["central"]["waac_id"] = waac
                    self.requisicoes.clear()
                    envio = flow_sender(ctx)
                    self.assertEqual(envio["id_hash_msg_bot"], "wamid.teste")
                    (path, corpo), = self.requisicoes
                    self.assertTrue(path.endswith(f"/{waac or '999'}/messages"))
                    self.assertEqual(corpo["messaging_account_id"], "100")
                    self.assertEqual(corpo["to"], ctx["mensagem_cliente_atual"]["cliente_telefone"])
                    self.assertEqual(corpo.get("interactive", {}).get("type", corpo["type"]), tipo)

    def test_digitacao_e_isolamento_entre_centrais_apos_erro(self):
        central = contexto()["central"] | {"waac_id": "771"}
        outra = {"phone_number_id": "222", "messaging_account_id": "300", "waac_id": None}
        with usar_remetente_central(central, "999"):
            with self.assertRaisesRegex(ValueError, "difere"):
                with usar_remetente_central(outra, "222"):
                    conta_wa("999", token="teste", session=self.sessao())
            cliente = conta_wa("999", token="teste", session=self.sessao())
            self.assertTrue(cliente.indicate_typing(message_id="wamid.entrada").success)
            with self.assertRaisesRegex(ValueError, "remetente"):
                cliente.send_message(to="5511000000000", text="teste", sender="222")
        with usar_remetente_central(outra, "222"):
            conta_wa("222", token="teste", session=self.sessao()).send_message(to="5511000000000", text="teste")
        self.assertEqual(len(self.requisicoes), 2)
        (path_digitacao, digitacao), (path_envio, envio) = self.requisicoes
        self.assertTrue(path_digitacao.endswith("/771/messages"))
        self.assertNotIn("messaging_account_id", digitacao)
        self.assertTrue(path_envio.endswith("/222/messages"))
        self.assertEqual(envio["messaging_account_id"], "300")
```

## 62. `utilitarios/monitoring/blocked_users.py` (alterar)

```python
"""Comparação de bloqueios do WhatsApp e do banco, somente para leitura.

O escopo é deliberadamente limitado às unidades e WABAs cadastradas no
banco. A ferramenta não altera a Meta nem o PostgreSQL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utilitarios.bootstrap import configurar_ambiente_local
from core.repositories.seguranca.comparacao_bloqueios import (
    iniciar_leitura_consistente,
    listar_unidades_para_comparacao,
    listar_bloqueios_para_comparacao,
)


def carregar_estado_banco(*, connection_factory=None):
    """Carrega unidades e bloqueios locais em uma única fotografia read-only."""
    if connection_factory is None:
        configurar_ambiente_local()
        from core.database.connection_aws import get_conn

        connection_factory = get_conn

    conn = connection_factory(
        application_name="utilitarios_blocked_users_readonly",
    )
    try:
        cursor = conn.cursor()
        iniciar_leitura_consistente(cursor)
        linhas_unidades = listar_unidades_para_comparacao(cursor)
        unidades = [
            {
                "id_unidade": linha[0],
                "nome_unidade": linha[1],
                "waba_id": _normalizar_id(linha[2]),
                "phone_id_unidade": _normalizar_id(linha[3]),
            }
            for linha in linhas_unidades
        ]

        linhas_bloqueios = listar_bloqueios_para_comparacao(cursor)
        bloqueios = [
            {
                "wa_id_cliente": _normalizar_id(linha[0]),
                "id_unidade": linha[1],
                "nome_unidade": linha[2],
                "waba_id": _normalizar_id(linha[3]),
                "phone_id_unidade": _normalizar_id(linha[4]),
                "phone_id_registrado": _normalizar_id(linha[4]),
                "id_cliente": linha[5],
                "nome_cliente": linha[6],
            }
            for linha in linhas_bloqueios
        ]
        return unidades, bloqueios
    finally:
        try:
            conn.rollback()
        finally:
            conn.close()


def listar_usuarios_bloqueados_meta(phone_id_unidade):
    """Lista todos os bloqueados de um phone ID usando paginação do PyWa."""
    configurar_ambiente_local()
    from core.integrations.whatsapp.tools.usuarios import cliente_de_bloqueio

    cliente_wa = cliente_de_bloqueio(phone_id_unidade)
    return cliente_wa.get_blocked_users().all(sleep=0.2)


def coletar_bloqueios_meta(unidades, *, list_factory=None):
    """Coleta cada unidade isoladamente; uma falha não apaga as demais."""
    list_factory = list_factory or listar_usuarios_bloqueados_meta
    resultado = []

    for unidade in unidades:
        item = {
            **unidade,
            "status_meta": "ok",
            "erro_meta": None,
            "wa_ids_bloqueados": [],
        }
        try:
            bloqueados = list_factory(unidade["phone_id_unidade"])
            item["wa_ids_bloqueados"] = sorted({
                wa_id
                for wa_id in (
                    _extrair_wa_id_bloqueado(usuario)
                    for usuario in bloqueados
                )
                if wa_id
            })
        except Exception as exc:
            item["status_meta"] = "erro"
            item["erro_meta"] = f"{type(exc).__name__}: {exc}"

        resultado.append(item)

    return resultado


def comparar_bloqueios(bloqueios_meta, bloqueios_banco):
    """Compara bloqueios por WABA, phone ID e WA ID do cliente."""
    meta_por_chave = {}
    banco_por_chave = {}
    escopos_ok = set()
    escopos_com_erro = set()
    falhas_meta = []
    vinculos_unidade_divergentes = []

    for unidade in bloqueios_meta:
        escopo = _escopo(unidade)
        if unidade["status_meta"] != "ok":
            escopos_com_erro.add(escopo)
            falhas_meta.append({
                "id_unidade": unidade["id_unidade"],
                "nome_unidade": unidade["nome_unidade"],
                "waba_id": unidade["waba_id"],
                "phone_id_unidade": unidade["phone_id_unidade"],
                "erro_meta": unidade["erro_meta"],
            })
            continue

        escopos_ok.add(escopo)
        for wa_id_cliente in unidade["wa_ids_bloqueados"]:
            chave = (*escopo, _normalizar_id(wa_id_cliente))
            meta_por_chave[chave] = {
                "wa_id_cliente": chave[2],
                "id_unidade": unidade["id_unidade"],
                "nome_unidade": unidade["nome_unidade"],
                "waba_id": chave[0],
                "phone_id_unidade": chave[1],
                "origem": "meta",
            }

    for bloqueio in bloqueios_banco:
        phone_atual = _normalizar_id(bloqueio["phone_id_unidade"])
        phone_registrado = _normalizar_id(
            bloqueio.get("phone_id_registrado", phone_atual)
        )
        if phone_registrado != phone_atual:
            vinculos_unidade_divergentes.append(dict(bloqueio))
            continue

        chave = (
            _normalizar_id(bloqueio["waba_id"]),
            phone_atual,
            _normalizar_id(bloqueio["wa_id_cliente"]),
        )
        banco_por_chave[chave] = dict(bloqueio)

    chaves_meta = set(meta_por_chave)
    chaves_banco = set(banco_por_chave)
    chaves_sincronizadas = chaves_meta & chaves_banco
    chaves_somente_meta = chaves_meta - chaves_banco
    chaves_somente_banco = {
        chave
        for chave in chaves_banco - chaves_meta
        if chave[:2] in escopos_ok
    }
    chaves_nao_comparadas = {
        chave
        for chave in chaves_banco - chaves_meta
        if chave[:2] not in escopos_ok
    }

    sincronizados = [
        {
            **banco_por_chave[chave],
            "origens": ("banco", "meta"),
        }
        for chave in _ordenar_chaves(chaves_sincronizadas)
    ]
    somente_meta = [
        meta_por_chave[chave]
        for chave in _ordenar_chaves(chaves_somente_meta)
    ]
    somente_banco = [
        banco_por_chave[chave]
        for chave in _ordenar_chaves(chaves_somente_banco)
    ]
    nao_comparados_banco = [
        banco_por_chave[chave]
        for chave in _ordenar_chaves(chaves_nao_comparadas)
    ]

    return {
        "sincronizados": sincronizados,
        "somente_meta": somente_meta,
        "somente_banco": somente_banco,
        "nao_comparados_banco": nao_comparados_banco,
        "vinculos_unidade_divergentes": sorted(
            vinculos_unidade_divergentes,
            key=_ordem_registro,
        ),
        "falhas_meta": sorted(falhas_meta, key=_ordem_unidade),
        "escopos_meta_ok": sorted(escopos_ok),
        "escopos_meta_com_erro": sorted(escopos_com_erro),
    }


def reconciliar_bloqueios_meta_banco(
    *,
    imprimir=True,
    mostrar_wa_id=False,
    connection_factory=None,
    meta_list_factory=None,
):
    """Executa e opcionalmente imprime a reconciliação Meta × banco."""
    unidades, bloqueios_banco = carregar_estado_banco(
        connection_factory=connection_factory,
    )
    bloqueios_meta = coletar_bloqueios_meta(
        unidades,
        list_factory=meta_list_factory,
    )
    resultado = comparar_bloqueios(bloqueios_meta, bloqueios_banco)
    resultado["unidades_consultadas"] = bloqueios_meta

    if imprimir:
        imprimir_reconciliacao_bloqueios(
            resultado,
            mostrar_wa_id=mostrar_wa_id,
        )

    return resultado


def listar_bloqueados_de_cada_unidade(
    *,
    imprimir=True,
    mostrar_wa_id=False,
    connection_factory=None,
    meta_list_factory=None,
):
    """Lista o estado Meta por unidade sem compará-lo ao banco."""
    unidades, _ = carregar_estado_banco(
        connection_factory=connection_factory,
    )
    resultado = coletar_bloqueios_meta(
        unidades,
        list_factory=meta_list_factory,
    )

    if imprimir:
        print("===== BLOQUEADOS NA META POR UNIDADE =====")
        for unidade in resultado:
            print(_descricao_unidade(unidade))
            if unidade["status_meta"] != "ok":
                print(f"   ERRO META: {unidade['erro_meta']}")
                continue
            if not unidade["wa_ids_bloqueados"]:
                print("   - nenhum número bloqueado")
            for wa_id in unidade["wa_ids_bloqueados"]:
                print(
                    "   - "
                    + _formatar_wa_id(wa_id, mostrar=mostrar_wa_id)
                )

    return resultado


def imprimir_reconciliacao_bloqueios(resultado, *, mostrar_wa_id=False):
    print("===== RECONCILIAÇÃO DE BLOQUEIOS META × BANCO =====")
    print(
        "Escopo: somente WABAs e unidades atualmente cadastradas no banco."
    )
    print(f"sincronizados: {len(resultado['sincronizados'])}")
    print(f"somente_na_meta: {len(resultado['somente_meta'])}")
    print(f"somente_no_banco: {len(resultado['somente_banco'])}")
    print(
        "não_comparados_por_falha_meta: "
        f"{len(resultado['nao_comparados_banco'])}"
    )
    print(
        "vínculos_de_unidade_divergentes: "
        f"{len(resultado['vinculos_unidade_divergentes'])}"
    )
    print(f"falhas_meta: {len(resultado['falhas_meta'])}")

    _imprimir_grupo(
        "SINCRONIZADOS NO BANCO E NA META",
        resultado["sincronizados"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "SOMENTE NA META",
        resultado["somente_meta"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "SOMENTE NO BANCO / PENDENTES NA META",
        resultado["somente_banco"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "NÃO COMPARADOS POR FALHA DA META",
        resultado["nao_comparados_banco"],
        mostrar_wa_id,
    )
    _imprimir_grupo(
        "VÍNCULO LOCAL DE UNIDADE DIVERGENTE",
        resultado["vinculos_unidade_divergentes"],
        mostrar_wa_id,
    )

    if resultado["falhas_meta"]:
        print("\nFALHAS DE COLETA META:")
        for falha in resultado["falhas_meta"]:
            print(
                f"   - {_descricao_unidade(falha)} | "
                f"erro={falha['erro_meta']}"
            )

    if _bloqueios_sincronizados(resultado):
        print("\nOK: banco e Meta estão sincronizados no escopo consultado.")


def criar_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Compara clientes bloqueados na Meta e no banco por unidade."
        ),
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)
    bloqueios = subparsers.add_parser(
        "blocked-users",
        help="compara bloqueados na Meta e em cliente_bloqueado_meta",
    )
    bloqueios.add_argument(
        "--show-wa-id",
        action="store_true",
        help="exibe o WA ID completo; por padrão mostra somente os 4 finais",
    )
    return parser


def executar_monitoramento_bloqueios():
    """Atalho local: executar o arquivo no PyCharm já gera o relatório."""
    configurar_ambiente_local()
    return reconciliar_bloqueios_meta_banco(
        imprimir=True,
        mostrar_wa_id=True,
    )


def main(argv=None):
    argumentos = sys.argv[1:] if argv is None else list(argv)
    if not argumentos:
        argumentos = ["blocked-users", "--show-wa-id"]

    args = criar_parser().parse_args(argumentos)
    try:
        resultado = reconciliar_bloqueios_meta_banco(
            mostrar_wa_id=args.show_wa_id,
        )
    except Exception as exc:
        print(
            f"RECONCILIACAO_FALHOU: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 2

    if resultado["falhas_meta"]:
        return 2
    if not _bloqueios_sincronizados(resultado):
        return 1
    return 0


def _bloqueios_sincronizados(resultado):
    return not any((
        resultado["somente_meta"],
        resultado["somente_banco"],
        resultado["nao_comparados_banco"],
        resultado["vinculos_unidade_divergentes"],
        resultado["falhas_meta"],
    ))


def _imprimir_grupo(titulo, itens, mostrar_wa_id):
    if not itens:
        return
    print(f"\n{titulo}:")
    for item in itens:
        wa_id = _formatar_wa_id(
            item.get("wa_id_cliente"),
            mostrar=mostrar_wa_id,
        )
        nome = item.get("nome_cliente") or "nome não disponível"
        print(
            f"   - wa_id={wa_id} | nome={nome} | "
            f"{_descricao_unidade(item)}"
        )


def _descricao_unidade(item):
    return (
        f"unidade {item.get('id_unidade')} "
        f"{item.get('nome_unidade')} | "
        f"WABA ({item.get('waba_id')}) | "
        f"phone_id ({item.get('phone_id_unidade')})"
    )


def _extrair_wa_id_bloqueado(usuario):
    if isinstance(usuario, dict):
        wa_id = usuario.get("wa_id") or usuario.get("user_id") or usuario.get("id")
    else:
        wa_id = getattr(usuario, "wa_id", None) or getattr(usuario, "bsuid", None) or (usuario if isinstance(usuario, str) else None)
    return _normalizar_id(wa_id)


def _normalizar_id(valor):
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _escopo(item):
    return (
        _normalizar_id(item["waba_id"]),
        _normalizar_id(item["phone_id_unidade"]),
    )


def _ordenar_chaves(chaves):
    return sorted(chaves, key=lambda item: tuple(valor or "" for valor in item))


def _ordem_registro(item):
    return (
        item.get("id_unidade") or 0,
        item.get("wa_id_cliente") or "",
    )


def _ordem_unidade(item):
    return (
        item.get("id_unidade") or 0,
        item.get("waba_id") or "",
    )


def _formatar_wa_id(valor, *, mostrar):
    texto = _normalizar_id(valor) or "-"
    if mostrar or len(texto) <= 4:
        return texto
    return "*" * (len(texto) - 4) + texto[-4:]


if __name__ == "__main__":
    if len(sys.argv) == 1:
        executar_monitoramento_bloqueios()
    else:
        raise SystemExit(main())
```

## 63. `core/etapas_pos_venda.py` (alterar)

```python
"""IDs do pós-venda. O mapa no PostgreSQL autoriza as transições.

A etapa 1 é saudação/coleta de nome; 3 é produto; 7 é encerramento.
Não há etapa técnica de abertura nem coleta de cidade.
"""

ETAPA_NOME = 1
ETAPA_CPF = 2
ETAPA_PRODUTO = 3
ETAPA_ASSUNTO = 4
ETAPA_PEDIDOS = 5
ETAPA_DETALHES = 6
ETAPA_ENCAMINHAMENTO = 7

EVENTO_SITUACAO_INFORMADA = "situacao_informada"

EVENTO_NOME_VALIDO_FALTA_CPF = "nome_valido_falta_cpf"
EVENTO_CPF_VALIDO = "cpf_valido"
EVENTO_PRODUTO_ESCOLHIDO = "produto_escolhido"
EVENTO_ASSUNTO_ESCOLHIDO = "assunto_escolhido"
EVENTO_PEDIDOS_ASSISTENCIA = "pedidos_assistencia"
EVENTO_PEDIDOS_DEMAIS_ASSUNTOS = "pedidos_demais_assuntos"
EVENTO_NOTA_PERDIDA_ASSISTENCIA = "nota_perdida_assistencia"
EVENTO_NOTA_PERDIDA_DEMAIS_ASSUNTOS = "nota_perdida_demais_assuntos"
EVENTO_HUMANO_SOLICITADO = "humano_solicitado"
EVENTO_LIMITE_SEM_AVANCO = "limite_sem_avanco"

EVENTOS_ENCAMINHAMENTO = frozenset({
    EVENTO_HUMANO_SOLICITADO, EVENTO_LIMITE_SEM_AVANCO,
})
```

## 64. `core/database/deploy_database/catalogo.sql` (alterar)

```sql
-- Fluxo sequencial de pós-venda. Apenas o encaminhamento bloqueia por 90 dias.
INSERT INTO chatbot.etapa (id_etapa, nome_etapa, encerra_automaticamente, bloqueio_dias) VALUES
    (1, 'nome_titular', false, 0),
    (2, 'cpf_titular', false, 0),
    (3, 'produto', false, 0),
    (4, 'assunto', false, 0),
    (5, 'pedidos', false, 0),
    (6, 'detalhes', false, 0),
    (7, 'encaminhamento', true, 90);

INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino) VALUES
    (1, 'nome_valido_falta_cpf', 2),
    (2, 'cpf_valido', 3),
    (3, 'produto_escolhido', 4),
    (4, 'assunto_escolhido', 5),
    (5, 'pedidos_assistencia', 6),
    (5, 'nota_perdida_assistencia', 6),
    (5, 'pedidos_demais_assuntos', 6),
    (5, 'nota_perdida_demais_assuntos', 6),
    (6, 'situacao_informada', 7),
    (1, 'humano_solicitado', 7),
    (1, 'limite_sem_avanco', 7),
    (2, 'humano_solicitado', 7),
    (2, 'limite_sem_avanco', 7),
    (3, 'humano_solicitado', 7),
    (3, 'limite_sem_avanco', 7),
    (4, 'humano_solicitado', 7),
    (4, 'limite_sem_avanco', 7),
    (5, 'humano_solicitado', 7),
    (5, 'limite_sem_avanco', 7),
    (6, 'humano_solicitado', 7),
    (6, 'limite_sem_avanco', 7);

INSERT INTO chatbot.cache_controle (nome) VALUES ('centrais_pos_venda');

INSERT INTO chatbot.filial_compra (codigo, nome, grupo) VALUES
    ('01', 'SFB TANCREDO NEVES - APENAS CONSULTA', 'Baratão'),
    ('02', 'SFB CRUZ - APENAS CONSULTA', 'Baratão'),
    ('03', 'SFB SAJ - APENAS CONSULTA!', 'Baratão'),
    ('05', 'DEPÓSITO - SFB', 'Baratão'),
    ('06', 'BARATÃO DOS MÓVEIS - VERA CRUZ - APENAS CONSULTA', 'Baratão'),
    ('07', 'SFB VALENÇA - APENAS CONSULTA', 'Baratão'),
    ('08', 'BARATÃO DOS MÓVEIS - DIAS DAVILA', 'Baratão'),
    ('09', 'ATACADÃO DO SOFÁ - IRECÊ', 'Atacadão'),
    ('10', 'ATACADÃO DO SOFÁ - ST ESTEVÃO', 'Atacadão'),
    ('11', 'ATACADÃO DO SOFÁ - JEQUIÉ', 'Atacadão'),
    ('12', 'ATACADÃO DO SOFÁ - SR DO BONFIM', 'Atacadão'),
    ('13', 'ATACADÃO DO SOFÁ - JUAZEIRO', 'Atacadão'),
    ('14', 'ATACADÃO DO SOFÁ - SERRINHA', 'Atacadão'),
    ('15', 'ATACADÃO DO SOFÁ - COITÉ', 'Atacadão'),
    ('16', 'ATACADÃO DO SOFÁ - ILHÉUS', 'Atacadão'),
    ('17', 'ATACADÃO DO SOFÁ - POMBAL', 'Atacadão'),
    ('18', 'ATACADÃO DO SOFÁ - JACOBINA', 'Atacadão'),
    ('19', 'ATACADÃO DO SOFÁ - ATC VERA CRUZ', 'Atacadão'),
    ('21', 'ATACADÃO DO SOFÁ - CAPIM GROSSO', 'Atacadão'),
    ('22', 'ATACADÃO DO SOFÁ - EUCLIDES', 'Atacadão'),
    ('23', 'ATACADÃO DO SOFÁ - FEIRA DE SANTANA', 'Atacadão'),
    ('25', 'ATACADÃO DO SOFÁ - PAULO AFONSO', 'Atacadão'),
    ('26', 'BARATÃO DOS MÓVEIS - SAJ (FEIRÃO)', 'Baratão'),
    ('27', 'BARATÃO DOS MÓVEIS - PTN (FEIRÃO)', 'Baratão'),
    ('28', 'BARATÃO DOS MÓVEIS - CRUZ DAS ALMAS (FEIRÃO)', 'Baratão'),
    ('29', 'BARATÃO DOS MÓVEIS - VALENÇA (FEIRÃO)', 'Baratão');
```

## 65. `workers/worker_flow/transacoes/encerramento_atendimento.py` (alterar)

```python
from core.repositories.atendimento.conversas import encerrar_conversa
from core.repositories.fluxo.politicas import buscar_politica_etapa

MOTIVOS_EVENTO = {
    "midia_recebida": "encaminhamento_midia",
    "humano_solicitado": "encaminhamento_humano",
    "limite_sem_avanco": "encaminhamento_sem_avanco",
}


def resolver_intencao_encerramento(contexto_historico, contexto_envio, cursor):
    etapa = contexto_envio["id_etapa_resultante"]
    politica = buscar_politica_etapa(etapa, cursor)
    if not politica.encerra_automaticamente:
        return None
    # Pode haver uma resposta terminal confirmada antes da migração e ainda na fila.
    if contexto_envio.get("resposta_ja_existia") and contexto_envio.get("evento_transicao") == "loja_nao_visitada":
        return {"motivo_encerramento": "visita_pendente", "bloqueio_dias": 0}
    motivo = MOTIVOS_EVENTO.get(
        contexto_envio.get("evento_transicao"), "encaminhamento")
    return {"motivo_encerramento": motivo, "bloqueio_dias": politica.bloqueio_dias}


def aplicar_encerramento_se_necessario(id_conversa, intencao, cursor):
    if not intencao:
        return {"atendimento_encerrado": False}
    finalizou = encerrar_conversa(id_conversa, intencao["motivo_encerramento"], cursor)
    return {"atendimento_encerrado": True, "finalizou_em": finalizou,
            "bloqueio_dias": intencao["bloqueio_dias"]}
```

## 66. `deploy/migrations/20261126_pendencias_baratao_etapas_sequenciais.sql` (aplicar)

```sql
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
```

## 67. `deploy/migrations/20261126_baratao_sete_etapas.sql` (aplicar)

```sql
-- Aplicar na base de nove etapas, após a migração de WAAC e BSUID.
-- Parar webhook e workers durante a troca. Executar o arquivo inteiro no DBeaver.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '2min';
LOCK TABLE chatbot.etapa, chatbot.etapa_transicao, chatbot.conversa,
           chatbot.historico_mensagens, chatbot.solicitacao_contato IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE mapa_anterior (origem int, evento text, destino int) ON COMMIT DROP;
INSERT INTO mapa_anterior VALUES
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
CREATE TEMP TABLE mapa_final (origem int, evento text, destino int) ON COMMIT DROP;
INSERT INTO mapa_final VALUES
(1, 'nome_valido_falta_cpf', 2),
    (1, 'nome_valido_cpf_presente', 3),
    (2, 'cpf_valido', 3),
    (3, 'produto_escolhido', 4),
    (4, 'assunto_escolhido', 5),
    (5, 'pedidos_assistencia', 6),
    (5, 'nota_perdida_assistencia', 6),
    (5, 'pedidos_demais_assuntos', 6),
    (5, 'nota_perdida_demais_assuntos', 6),
    (6, 'situacao_informada', 7),
    (1, 'midia_recebida', 7),
    (1, 'humano_solicitado', 7),
    (1, 'limite_sem_avanco', 7),
    (2, 'midia_recebida', 7),
    (2, 'humano_solicitado', 7),
    (2, 'limite_sem_avanco', 7),
    (3, 'midia_recebida', 7),
    (3, 'humano_solicitado', 7),
    (3, 'limite_sem_avanco', 7),
    (4, 'midia_recebida', 7),
    (4, 'humano_solicitado', 7),
    (4, 'limite_sem_avanco', 7),
    (5, 'midia_recebida', 7),
    (5, 'humano_solicitado', 7),
    (5, 'limite_sem_avanco', 7),
    (6, 'midia_recebida', 7),
    (6, 'humano_solicitado', 7),
    (6, 'limite_sem_avanco', 7);

DO $migrar$
DECLARE
    nomes text[];
BEGIN
    SELECT array_agg(nome_etapa ORDER BY id_etapa) INTO nomes FROM chatbot.etapa;
    IF nomes = ARRAY['nome_titular','cpf_titular','produto','assunto','pedidos','detalhes','encaminhamento'] THEN
        RETURN;  -- A conferência abaixo também verifica a reaplicação.
    END IF;
    IF nomes IS DISTINCT FROM ARRAY['nome_titular','cpf_titular','produto','assunto','pedidos',
                                     'visita_loja','visita_pendente','detalhes','encaminhamento']
       OR (SELECT array_agg(id_etapa ORDER BY id_etapa) FROM chatbot.etapa) <> ARRAY[1,2,3,4,5,6,7,8,9]
       OR (SELECT count(*) FROM chatbot.etapa_transicao) <> (SELECT count(*) FROM mapa_anterior)
       OR EXISTS (SELECT * FROM mapa_anterior EXCEPT
                  SELECT id_etapa_origem, evento, id_etapa_destino FROM chatbot.etapa_transicao)
       OR EXISTS (SELECT FROM chatbot.etapa WHERE encerra_automaticamente <> (id_etapa IN (7,9))
                  OR bloqueio_dias <> CASE WHEN id_etapa=9 THEN 90 ELSE 0 END) THEN
        RAISE EXCEPTION 'Base divergente do catálogo de nove etapas. Nenhuma mudança confirmada.';
    END IF;

    -- A próxima resposta à antiga pergunta de sim/não precisa receber a pergunta aberta.
    -- Guardar a origem histórica, inclusive de mensagens que mantêm o mesmo ID numérico.
    UPDATE chatbot.historico_mensagens
    SET interativo = coalesce(interativo, '{}'::jsonb)
        || jsonb_build_object('_etapa_antes_sete', id_etapa)
        || CASE WHEN id_etapa=6 AND quem_enviou='bot'
                THEN '{"_reapresentar_detalhes":true}'::jsonb ELSE '{}'::jsonb END,
        id_etapa = CASE WHEN id_etapa IN (6,8) THEN 6 ELSE 7 END
    WHERE id_etapa IN (6,7,8,9);

    UPDATE chatbot.conversa SET turnos_sem_avanco=0 WHERE id_etapa_atual=6 AND status_ativa;
    UPDATE chatbot.conversa SET id_etapa_atual=CASE id_etapa_atual WHEN 8 THEN 6 ELSE 7 END
    WHERE id_etapa_atual IN (8,9);
    UPDATE chatbot.solicitacao_contato SET id_etapa_retomada=CASE id_etapa_retomada WHEN 8 THEN 6 ELSE 7 END
    WHERE id_etapa_retomada IN (8,9);

    DELETE FROM chatbot.etapa_transicao WHERE id_etapa_origem=6;
    UPDATE chatbot.etapa_transicao SET id_etapa_origem=6 WHERE id_etapa_origem=8;
    UPDATE chatbot.etapa_transicao SET id_etapa_destino=CASE id_etapa_destino WHEN 8 THEN 6 ELSE 7 END
    WHERE id_etapa_destino IN (8,9);
    INSERT INTO chatbot.etapa_transicao (id_etapa_origem,evento,id_etapa_destino)
    VALUES (6,'humano_solicitado',7),(6,'limite_sem_avanco',7);

    DELETE FROM chatbot.etapa WHERE id_etapa IN (8,9);
    UPDATE chatbot.etapa SET nome_etapa='detalhes' WHERE id_etapa=6;
    UPDATE chatbot.etapa SET nome_etapa='encaminhamento', bloqueio_dias=90 WHERE id_etapa=7;
END
$migrar$;

DO $conferir$
BEGIN
    IF (SELECT array_agg(id_etapa ORDER BY id_etapa) FROM chatbot.etapa) IS DISTINCT FROM ARRAY[1,2,3,4,5,6,7]
       OR EXISTS (SELECT FROM chatbot.etapa WHERE encerra_automaticamente <> (id_etapa=7)
                  OR bloqueio_dias <> CASE WHEN id_etapa=7 THEN 90 ELSE 0 END)
       OR (SELECT count(*) FROM chatbot.etapa_transicao) <> (SELECT count(*) FROM mapa_final)
       OR EXISTS (SELECT * FROM mapa_final EXCEPT
                  SELECT id_etapa_origem,evento,id_etapa_destino FROM chatbot.etapa_transicao) THEN
        RAISE EXCEPTION 'Falha na conferência das sete etapas ou das transições.';
    END IF;
END
$conferir$;
COMMIT;

SELECT (SELECT array_agg(id_etapa ORDER BY id_etapa) FROM chatbot.etapa) AS etapas,
       (SELECT count(*) FROM chatbot.etapa_transicao) AS transicoes,
       (SELECT nome_etapa FROM chatbot.etapa WHERE id_etapa=6) AS etapa_6,
       (SELECT nome_etapa FROM chatbot.etapa WHERE id_etapa=7) AS etapa_7,
       (SELECT bloqueio_dias FROM chatbot.etapa WHERE id_etapa=7) AS bloqueio_dias;
```

## 68. `workers/worker_flow/response_flow/etapas/resolver_etapa6_detalhes.py` (usar)

```python
"""Coleta o relato e encaminha o atendimento para os setores escolhidos."""
from core.etapas_pos_venda import ETAPA_ENCAMINHAMENTO, EVENTO_SITUACAO_INFORMADA
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa6_detalhes import enviar_etapa6_detalhes
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from workers.worker_flow.response_flow.etapas.validadores_contexto.valida_detalhes_etapa6 import validar_contexto_detalhes
from workers.worker_flow.response_flow.tratamento_universal_pos_venda import repetir_etapa, resolver_tratamento_universal
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def resolve_etapa6_detalhes(contexto):
    entrada = contexto["mensagem_cliente_atual"]
    telefone = contexto.get("destinatario_envio", entrada.get("cliente_telefone"))
    central = entrada["id_phone_unidade"]
    if contexto.get("apresentacao_pendente"):
        return enviar_etapa6_detalhes(telefone, central)
    tratamento = resolver_tratamento_universal(contexto)
    if tratamento is not None:
        return tratamento
    detalhes = validar_contexto_detalhes(contexto)
    if not detalhes:
        return repetir_etapa(contexto, enviar_etapa6_detalhes, telefone, central, repetir=True)
    evento = EVENTO_SITUACAO_INFORMADA
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento({**contexto, "detalhes": detalhes}, evento)
    envio["detalhes"] = detalhes
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)
```

## 69. `workers/worker_flow/response_flow/etapas/validadores_contexto/valida_detalhes_etapa6.py` (usar)

```python
"""O relato é livre. O tratamento universal tem prioridade sobre a coleta."""


def validar_contexto_detalhes(contexto):
    entrada = contexto["mensagem_cliente_atual"]
    texto = entrada.get("conteudo_texto")
    if entrada.get("tipo_mensagem") == "text" and isinstance(texto, str):
        return texto.strip() or None
    return None
```

## 70. `core/integrations/whatsapp/pywa_functions/pywa_senders/etapa6_detalhes.py` (usar)

```python
"""Apresenta a pergunta aberta sobre a situação."""
from core.etapas_pos_venda import ETAPA_DETALHES
from core.integrations.whatsapp.messages.etapa6_detalhes_messages import MENSAGEM_DETALHES
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa6_detalhes(cliente_telefone, phone_id_unidade, *, repetir=False):
    envio = enviar_texto_pos_venda(cliente_telefone, phone_id_unidade, MENSAGEM_DETALHES, ETAPA_DETALHES)
    if repetir:
        envio.update(tratamento=True, tipo_tratamento="detalhes_ausentes")
    return envio
```

## 71. `core/integrations/whatsapp/messages/etapa6_detalhes_messages.py` (usar)

```python
"""Coleta do relato de pós-venda."""

MENSAGEM_DETALHES = (
    "Certo, estamos quase lá! 😁\n\n"
    "Para podermos te ajudar da melhor forma possível, descreva com o máximo de detalhes "
    "a sua situação e o que você precisa."
)
```

## 72. `core/integrations/whatsapp/messages/encaminhamento_pos_venda.py` (usar)

```python
"""Textos compartilhados do encaminhamento humano, fora das etapas de coleta."""

from core.integrations.whatsapp.pywa_functions.saudacao import obter_saudacao_por_horario

ROTULOS_POS_VENDA = {
    "atacadao": "Pós-venda Atacadão",
    "baratao": "Pós-venda Baratão",
}
MENSAGEM_POR_GRUPO = {
    "atacadao": "Sua compra é do Atacadão. Toque no botão abaixo para falar com o pós-venda do Atacadão.",
    "baratao": "Sua compra é do Baratão. Toque no botão abaixo para falar com o pós-venda do Baratão.",
}
MENSAGEM_SEM_NOTA = (
    "Vou te passar os contatos do pós-venda do Atacadão e do Baratão. "
    "Deslize para o lado e toque no botão da rede onde você fez a compra."
)
MENSAGEM_NOTA_PERDIDA = (
    "Tudo bem se você perdeu a nota. Deslize para o lado para ver os dois contatos "
    "e toque no pós-venda da rede onde você fez a compra: Atacadão ou Baratão."
)
MENSAGEM_DUAS_REDES = (
    "Suas notas são de compras no Atacadão e no Baratão. "
    "Deslize para o lado e escolha o pós-venda da rede com que deseja falar primeiro."
)
AVISO_ASSISTENCIA = (
    "Olha, vale lembra que em caso de avarias, o protocolo é tirar fotos e vídeos e ir pessoalmente à loja "
    "em que realizou a compra para abrir um chamado. Lembrando que a garantia é de 90 dias "
    "desde o recebimento do produto.Desconsidere esse aviso caso você já tenha ido à loja pessoalmente e seu "
    "produto esteja dentro da garantia."
)


def mensagem_de_contato(texto, assunto):
    return f"{AVISO_ASSISTENCIA}\n\n{texto}" if assunto in {"assistencia", "misto"} else texto


def montar_resumo_encaminhamento(cadastro, produto=None, assunto=None, *,
                                 pedidos_com_filial=(), perdeu_nota=None, detalhes=None):
    rotulos = {"moveis": "Móveis", "estofados": "Estofados", "ambos": "Móveis e Estofados"}
    campos = [
        ("Titular da compra", cadastro.get("nome_titular")),
        ("CPF do titular", cadastro.get("cpf_titular")),
        ("Produto", rotulos.get(produto)),
        ("Assunto", "Assistência" if assunto == "assistencia" else (assunto or "").capitalize()),
    ]
    linhas = [f"- {campo}: {valor}" for campo, valor in campos if valor]
    notas = ["Perdi a nota"] if perdeu_nota else [
        f"{numero} ({filial})" if filial else numero for numero, filial in pedidos_com_filial
    ]
    if len(notas) == 1:
        linhas.append(f"- Número da nota: {notas[0]}")
    elif notas:
        linhas.append("- Números das notas:")
        linhas.extend(f"  • {nota}" for nota in notas)
    saudacao = obter_saudacao_por_horario().lower()
    abertura = f"Olá, {saudacao}! Fui encaminhado(a) pelo assistente Theo e gostaria de atendimento humano."
    lista = "\n".join(linhas)
    return "\n\n".join(bloco for bloco in (abertura, lista, detalhes) if bloco)
```

## 73. `core/repositories/atendimento/pos_venda.py` (usar)

```python
"""Dados do atendimento por conversa; o worker controla commit e rollback."""


def atualizar_produto_do_atendimento(id_conversa, produto, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET produto = %s WHERE id_conversa = %s;
    """, (produto, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar produto.")


def atualizar_assunto_do_atendimento(id_conversa, assunto, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET assunto = %s::chatbot.assunto WHERE id_conversa = %s;
    """, (assunto, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar assunto.")


def atualizar_nome_do_atendimento(id_conversa, nome_titular, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET nome_titular = %s WHERE id_conversa = %s;
    """, (nome_titular, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar nome.")


def atualizar_cpf_do_atendimento(id_conversa, cpf_titular, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET cpf_titular = %s WHERE id_conversa = %s;
    """, (cpf_titular, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar CPF.")


def registrar_contatos_encaminhados(id_conversa, telefone_baratao, telefone_atacadao, cursor):
    """A gravação dos destinos aciona a situação de encaminhamento na mesma transação."""
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda
        SET encaminhado_baratao = %s, encaminhado_atacadao = %s
        WHERE id_conversa = %s;
    """, (telefone_baratao, telefone_atacadao, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar contatos.")


def registrar_detalhes(id_conversa, detalhes, cursor):
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda SET detalhes = %s WHERE id_conversa = %s;
    """, (detalhes, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Atendimento ausente ao confirmar os detalhes.")
```

## 74. `core/validacoes/nome_titular.py` (usar)

```python
"""Validação de formato do nome completo; não consulta listas de nomes."""

import re
import unicodedata

from core.validacoes.apresentacao_nome import NAO_NOMES


# A apresentação é opcional. Uma vez reconhecida, só o trecho que sobra
# pode ser o nome. Isso evita gravar "Eu me chamo" quando falta o sobrenome.
_SAUDACAO = re.compile(r"^(?:ol[áa]|oi|bom dia|boa tarde|boa noite)[ ,!.:-]+", re.I)
_APRESENTACAO = re.compile(
    r"^(?:(?:pode me chamar de|(?:o|a) titular(?: da compra)? se chama)|(?:eu\s+)?me\s+chamo|(?:ele|ela)\s+se\s+chama|"
    r"(?:o\s+)?(?:meu\s+nome(?:\s+completo)?|nome(?:\s+completo)?\s+"
    r"(?:dele|dela|d[oa]\s+titular(?:\s+da\s+compra)?))\s+(?:é|e|eh)|"
    r"(?:eu\s+)?sou(?:\s+[oa])?|(?:[oa]\s+)?titular(?:\s+da\s+compra)?\s+(?:é|e)|"
    r"aqui\s+(?:quem\s+fala\s+)?(?:é|e)(?:\s+[oa])?|"
    r"nome(?:\s+completo)?(?=\s*:))(?=\s|:|$)\s*:?\s*", re.I,
)
_CONECTORES = {"da", "de", "do", "das", "dos", "e"}
_TERMOS_DE_FRASE = {"eu", "me", "chamo", "meu", "minha", "nome", "titular", "compra",
                    "sou", "ele", "ela", "dele", "dela", "quero", "preciso", "não",
                    "ajuda", "pedido", "esqueci", "sei", "gostaria", "quem", "é"}


def normalizar_nome_titular(texto):
    """Retorna o nome aceito sem ponto final, ou None para entrada inválida."""
    if not isinstance(texto, str):
        return None
    nome = unicodedata.normalize("NFC", texto).strip()
    nome = _SAUDACAO.sub("", nome)
    apresentacao = _APRESENTACAO.match(nome)
    if apresentacao:
        nome = nome[apresentacao.end():]
        nome = re.sub(r"^[oa]\s+", "", nome, flags=re.I)
        nome = re.split(r"\s+e\s+(?:quero|queria|preciso|gostaria|vim)\b", nome,
                        maxsplit=1, flags=re.I)[0]
    if nome.endswith("."):
        nome = nome[:-1]
    if not nome or nome != nome.strip():
        return None
    for indice, caractere in enumerate(nome):
        if caractere.isalpha() or caractere.isspace():
            continue
        if (caractere == "-" and 0 < indice < len(nome) - 1
                and nome[indice - 1].isalpha() and nome[indice + 1].isalpha()):
            continue
        return None
    partes = nome.split()
    palavras = [p.casefold() for p in partes]
    primeiro = "".join(c for c in unicodedata.normalize("NFD", palavras[0])
                       if not unicodedata.combining(c)) if palavras else ""
    if (primeiro in NAO_NOMES or len(partes) < 2 or palavras[0] in _CONECTORES or palavras[-1] in _CONECTORES
            or _TERMOS_DE_FRASE.intersection(palavras)):
        return None
    return " ".join(partes)
```

## 75. `workers/worker_flow/response_flow/etapas/validadores_contexto/valida_etapa1.py` (aplicar)

```python
"""Interpreta a resposta ao nome; a entrada de saudação não passa aqui."""

from core.etapas_pos_venda import EVENTO_NOME_VALIDO_FALTA_CPF
from core.validacoes.nome_titular import normalizar_nome_titular


def validar_contexto_etapa1(contexto):
    nome = normalizar_nome_titular(contexto["mensagem_cliente_atual"].get("conteudo_texto"))
    if nome is None:
        return None
    return {"evento": EVENTO_NOME_VALIDO_FALTA_CPF, "nome_titular": nome}
```

## 76. `core/repositories/atendimento/clientes.py` (aplicar)

```python
import logging

from core.logging_config import short_value


logger = logging.getLogger("db.atendimento.clientes")


def inserindo_em_cliente_caso_seja_novo(waid_telefone, cursor):
    cursor.execute("""
        INSERT INTO chatbot.cliente (waid_telefone)
        VALUES (%s)
        ON CONFLICT (waid_telefone) DO NOTHING;
    """, (waid_telefone,))

    inserido = cursor.rowcount == 1

    cursor.execute("""
        SELECT id_cliente
        FROM chatbot.cliente
        WHERE waid_telefone = %s;
    """, (waid_telefone,))
    resultado = cursor.fetchone()

    if resultado:
        logger.debug(
            "cliente_insert_resultado | acao=obter_cliente telefone=%s id_cliente=%s inserido=%s",
            short_value(waid_telefone),
            resultado[0],
            inserido,
        )
        return resultado[0], inserido

    raise ValueError(
        "Anomalia Crítica: Cliente do telefone "
        f"{waid_telefone} desapareceu da base durante a verificação!"
    )


def atualizar_nome_titular(id_cliente, nome_titular, cursor):
    """Confirma o nome global usando a transação do worker."""
    cursor.execute(
        "UPDATE chatbot.cliente SET nome_titular = %s WHERE id_cliente = %s",
        (nome_titular, id_cliente),
    )
    if cursor.rowcount != 1:
        raise ValueError("Cliente não encontrado ao confirmar nome.")


def atualizar_cpf_titular(id_cliente, cpf_titular, cursor):
    """Confirma o CPF global usando a transação do worker."""
    cursor.execute(
        "UPDATE chatbot.cliente SET cpf_titular = %s WHERE id_cliente = %s",
        (cpf_titular, id_cliente),
    )
    if cursor.rowcount != 1:
        raise ValueError("Cliente não encontrado ao confirmar CPF.")
```

## 77. `core/repositories/atendimento/conciliacao_cliente.py` (aplicar)

```python
"""Prova do telefone por conversa e reassociação do cadastro provisório."""


def guardar_telefone_compartilhado(conversa, telefone, cursor):
    """Um valor nulo encerra a conferência após a fusão."""
    cursor.execute("""
        UPDATE chatbot.atendimento_pos_venda SET telefone_compartilhado=%s
        WHERE id_conversa=%s
    """, (telefone, conversa))


def telefone_em_conferencia(central, uid, cursor):
    """Prova oficial mantida somente para o atendimento ativo desse BSUID."""
    cursor.execute("""
        SELECT a.telefone_compartilhado FROM chatbot.identidade_bsuid i
        JOIN chatbot.chat ch USING (id_cliente, id_central)
        JOIN chatbot.conversa c USING (id_chat)
        JOIN chatbot.atendimento_pos_venda a USING (id_conversa)
        WHERE i.id_central=%s AND i.user_id=%s AND i.vigente AND NOT i.suspender_telefone
          AND c.status_ativa AND a.telefone_compartilhado IS NOT NULL
    """, (central, uid))
    row = cursor.fetchone()
    return row[0] if row else None


def candidatos_para_cpf(origem, cpf, telefone, conversa, cursor):
    """O ID sequencial desempata fichas com a mesma prioridade."""
    cursor.execute("""
        SELECT cl.id_cliente, cl.cpf_titular, cl.waid_telefone,
               cl.id_cliente=%s AND EXISTS (
                   SELECT FROM chatbot.chat ch JOIN chatbot.conversa c USING (id_chat)
                   WHERE ch.id_cliente=cl.id_cliente AND c.id_conversa<>%s
               ) AS origem_com_historico
        FROM chatbot.cliente cl
        WHERE cl.id_cliente=%s OR cl.cpf_titular=%s OR cl.waid_telefone=%s
        ORDER BY cl.id_cliente FOR UPDATE OF cl
    """, (origem, conversa, origem, cpf, telefone))
    return cursor.fetchall()


def bloquear_chats(clientes, cursor):
    cursor.execute("""
        SELECT id_chat, id_cliente, id_central FROM chatbot.chat
        WHERE id_cliente=ANY(%s) ORDER BY id_chat FOR UPDATE
    """, (clientes,))
    cursor.fetchall()


def bloquear_aliases(clientes, cursor):
    cursor.execute("""
        SELECT id_central, user_id, id_cliente, vigente, suspender_telefone
        FROM chatbot.identidade_bsuid WHERE id_cliente=ANY(%s)
        ORDER BY id_central, user_id FOR UPDATE
    """, (clientes,))
    return cursor.fetchall()


def ha_trabalho_em_andamento(clientes, telefones, conversa, fila, cursor):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM chatbot.conversa c JOIN chatbot.chat ch USING (id_chat)
            WHERE ch.id_cliente=ANY(%s) AND c.id_conversa<>%s AND (c.status_ativa OR c.processing)
        ) OR EXISTS (
            SELECT FROM chatbot.fila_mensagens f
            LEFT JOIN chatbot.conversa c USING (id_conversa)
            LEFT JOIN chatbot.chat ch USING (id_chat)
            WHERE (f.id_cliente=ANY(%s) OR ch.id_cliente=ANY(%s)
                   OR (f.id_cliente IS NULL AND f.cliente_telefone=ANY(%s)))
              AND f.id_mensagem<>%s AND f.status IN ('pending','processing')
        )
    """, (clientes, conversa, clientes, clientes, telefones, fila))
    return cursor.fetchone()[0]


def identificador_bloqueado(telefones, clientes, cursor):
    cursor.execute("""
        SELECT EXISTS (SELECT FROM chatbot.contato_interno WHERE waid_telefone=ANY(%s))
            OR EXISTS (SELECT FROM chatbot.cliente_bloqueado_meta b
                       WHERE b.wa_id_cliente=ANY(%s) OR EXISTS (
                           SELECT FROM chatbot.identidade_bsuid a WHERE a.id_cliente=ANY(%s)
                             AND a.id_central=b.id_central AND a.user_id=b.wa_id_cliente))
    """, (telefones, telefones, clientes))
    return cursor.fetchone()[0]


def ha_bloqueio_temporario(clientes, cursor):
    cursor.execute("""
        SELECT EXISTS (
            SELECT FROM chatbot.chat ch JOIN chatbot.conversa c USING (id_chat)
            JOIN chatbot.etapa e ON e.id_etapa=c.id_etapa_atual
            WHERE ch.id_cliente=ANY(%s) AND NOT c.status_ativa
              AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente'
              AND e.bloqueio_dias>0 AND c.finalizou_em + e.bloqueio_dias * interval '1 day' > now()
        )
    """, (clientes,))
    return cursor.fetchone()[0]


def garantir_chats_do_vencedor(vencedor, perdedores, cursor):
    cursor.execute("""
        INSERT INTO chatbot.chat (id_cliente, id_central)
        SELECT DISTINCT %s::integer, id_central FROM chatbot.chat WHERE id_cliente=ANY(%s)
        ON CONFLICT (id_cliente,id_central) DO NOTHING
    """, (vencedor, perdedores))


def mover_fila(perdedores, vencedor, cursor):
    cursor.execute("""
        UPDATE chatbot.fila_mensagens f SET id_cliente=%s WHERE f.id_cliente=ANY(%s)
            OR (f.id_cliente IS NULL AND EXISTS (
                SELECT FROM chatbot.conversa c JOIN chatbot.chat ch USING (id_chat)
                WHERE c.id_conversa=f.id_conversa AND ch.id_cliente=ANY(%s)))
    """, (vencedor, perdedores, perdedores))


def mover_conversas(perdedores, vencedor, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa c SET id_chat=destino.id_chat
        FROM chatbot.chat origem JOIN chatbot.chat destino USING (id_central)
        WHERE c.id_chat=origem.id_chat AND origem.id_cliente=ANY(%s) AND destino.id_cliente=%s
    """, (perdedores, vencedor))


def mover_aliases(perdedores, vencedor, cursor):
    cursor.execute("""
        UPDATE chatbot.identidade_bsuid SET id_cliente=%s WHERE id_cliente=ANY(%s)
    """, (vencedor, perdedores))


def liberar_telefone(perdedores, telefone, cursor):
    cursor.execute("""
        UPDATE chatbot.cliente SET waid_telefone=NULL WHERE id_cliente=ANY(%s) AND waid_telefone=%s
    """, (perdedores, telefone))


def atualizar_cadastro_pela_conversa(conversa, vencedor, telefone, cursor):
    """Somente um perfil observado nesta conversa pode substituir o do vencedor."""
    cursor.execute("""
        UPDATE chatbot.cliente cl SET nome_titular=a.nome_titular, waid_telefone=%s,
            username=CASE WHEN perfil.observado_em IS NOT NULL AND
                (cl.username_observado_em IS NULL OR perfil.observado_em>=cl.username_observado_em)
                THEN perfil.username ELSE cl.username END,
            username_observado_em=greatest(cl.username_observado_em, perfil.observado_em)
        FROM chatbot.atendimento_pos_venda a LEFT JOIN LATERAL (
            SELECT f.username_origem AS username, f.received_data_hora AS observado_em
            FROM chatbot.fila_mensagens f WHERE f.id_conversa=a.id_conversa
              AND nullif(btrim(f.username_origem),'') IS NOT NULL
            ORDER BY f.received_data_hora DESC, f.id_mensagem DESC LIMIT 1
        ) perfil ON true
        WHERE cl.id_cliente=%s AND a.id_conversa=%s
    """, (telefone, vencedor, conversa))
    if cursor.rowcount != 1:
        raise ValueError("Dados da conversa ausentes ao consolidar o cadastro.")


def excluir_chats_vazios(perdedores, cursor):
    cursor.execute("DELETE FROM chatbot.chat WHERE id_cliente=ANY(%s)", (perdedores,))


def excluir_cadastros_redundantes(perdedores, cursor):
    cursor.execute("DELETE FROM chatbot.cliente WHERE id_cliente=ANY(%s)", (perdedores,))
    if cursor.rowcount != len(perdedores):
        raise ValueError("Um dos cadastros mudou durante a conciliação.")
```

## 78. `deploy/migrations/20261126_recoleta_titular.sql` (aplicar)

```sql
-- Base Baratão de sete etapas. Executar o arquivo inteiro no DBeaver com os serviços pausados.
BEGIN;
SET LOCAL lock_timeout = '8s';
LOCK TABLE chatbot.etapa, chatbot.etapa_transicao IN SHARE ROW EXCLUSIVE MODE;
DO $validar$
BEGIN
    IF (SELECT array_agg(nome_etapa::text ORDER BY id_etapa) FROM chatbot.etapa)
         IS DISTINCT FROM ARRAY['nome_titular','cpf_titular','produto','assunto','pedidos','detalhes','encaminhamento']
       OR NOT EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem=1
                      AND evento='nome_valido_falta_cpf' AND id_etapa_destino=2) THEN
        RAISE EXCEPTION 'Aplicar primeiro a migração de sete etapas.';
    END IF;
END
$validar$;

DELETE FROM chatbot.etapa_transicao
WHERE id_etapa_origem=1 AND evento='nome_valido_cpf_presente' AND id_etapa_destino=3;

DO $conferir$
BEGIN
    IF (SELECT count(*) FROM chatbot.etapa_transicao) <> 27
       OR EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem=1 AND id_etapa_destino=3) THEN
        RAISE EXCEPTION 'Mapa de etapas divergente. Transação revertida.';
    END IF;
END
$conferir$;
COMMIT;

SELECT (SELECT count(*) FROM chatbot.etapa) AS etapas,
       (SELECT count(*) FROM chatbot.etapa_transicao) AS transicoes,
       EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem=1 AND id_etapa_destino=3) AS pula_cpf;
```

## 79. `core/repositories/atendimento/conversas.py` (aplicar)

```python
"""Persistência de conversas do pós-venda; transações pertencem ao worker."""

MOTIVOS_ENCERRAMENTO_VALIDOS = {
    "visita_pendente", "encaminhamento", "encaminhamento_midia",
    "encaminhamento_humano", "encaminhamento_sem_avanco",
}


def inserindo_em_conversa_caso_seja_nova(id_cliente, id_unidade, cursor):
    cursor.execute("""
        INSERT INTO chatbot.chat (id_cliente, id_central) VALUES (%s, %s)
        ON CONFLICT (id_cliente, id_central) DO UPDATE SET id_cliente=EXCLUDED.id_cliente
        RETURNING id_chat;
    """, (id_cliente, id_unidade))
    id_chat = cursor.fetchone()[0]
    cursor.execute("""
        INSERT INTO chatbot.conversa (id_chat, id_central, id_etapa_atual)
        VALUES (%s, %s, 1)
        ON CONFLICT (id_chat) WHERE status_ativa DO NOTHING
        RETURNING id_conversa;
    """, (id_chat, id_unidade))
    row = cursor.fetchone()
    if not row:
        cursor.execute("SELECT id_conversa FROM chatbot.conversa WHERE id_chat = %s AND status_ativa", (id_chat,))
        row = cursor.fetchone()
    if not row:
        raise RuntimeError("Não foi possível criar ou localizar a conversa ativa.")
    cursor.execute("""
        INSERT INTO chatbot.atendimento_pos_venda (id_conversa) VALUES (%s)
        ON CONFLICT (id_conversa) DO NOTHING;
    """, (row[0],))
    return row[0]


def tentar_lock_conversa(id_conversa, cursor):
    cursor.execute("SELECT lock_ok, lock_version_atual FROM chatbot.lock_conversa(%s)", (id_conversa,))
    return cursor.fetchone() or (False, None)


def unlock_conversa(id_conversa, lock_version, cursor):
    if lock_version is None:
        return False
    cursor.execute("SELECT chatbot.unlock_conversa(%s, %s)", (id_conversa, lock_version))
    row = cursor.fetchone()
    return bool(row and row[0])


def buscar_estado_conversa(id_cliente, id_unidade, cursor):
    cursor.execute("""
        SELECT c.id_conversa, c.id_etapa_atual, c.status_ativa, c.finalizou_em,
               CASE WHEN c.status_ativa THEN 'ativa'
                    WHEN e.bloqueio_dias > 0 AND c.motivo_encerramento IS DISTINCT FROM 'visita_pendente' AND c.finalizou_em >
                         CURRENT_TIMESTAMP - e.bloqueio_dias * INTERVAL '1 day'
                    THEN 'bloqueada' ELSE 'liberada' END,
               c.last_message_from, c.turnos_sem_avanco
        FROM chatbot.conversa c
        JOIN chatbot.chat ch ON ch.id_chat = c.id_chat
        JOIN chatbot.etapa e ON e.id_etapa = c.id_etapa_atual
        WHERE ch.id_cliente = %s AND c.id_central = %s
        ORDER BY c.status_ativa DESC, c.iniciou_em DESC, c.id_conversa DESC LIMIT 1;
    """, (id_cliente, id_unidade))
    row = cursor.fetchone()
    return dict(zip(("id_conversa", "id_etapa_atual", "status_ativa", "finalizou_em",
                     "estado", "last_message_from", "turnos_sem_avanco"), row)) if row else None


def atualizar_conversa_mensagem_cliente(id_conversa, data_interacao, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa SET last_interaction_at = %s, last_message_from = 'cliente'
        WHERE id_conversa = %s AND status_ativa;
    """, (data_interacao, id_conversa))


def atualizar_conversa_resposta_bot_sem_avancar(id_conversa, data_interacao, cursor):
    cursor.execute("""
        UPDATE chatbot.conversa SET last_interaction_at = %s, last_message_from = 'bot'
        WHERE id_conversa = %s AND status_ativa;
    """, (data_interacao, id_conversa))
    if cursor.rowcount != 1:
        raise ValueError("Conversa deixou de estar ativa.")


def atualizar_conversa_por_transicao(id_conversa, origem, evento, destino, data_interacao, cursor, *, permitir_reaplicacao=False):
    cursor.execute("""
        UPDATE chatbot.conversa c SET id_etapa_atual = %s,
            last_interaction_at = %s, last_message_from = 'bot'
        WHERE c.id_conversa = %s AND c.status_ativa
          AND (c.id_etapa_atual = %s OR (%s AND c.id_etapa_atual = %s))
          AND EXISTS (SELECT FROM chatbot.etapa_transicao
                      WHERE id_etapa_origem = %s AND evento = %s AND id_etapa_destino = %s);
    """, (destino, data_interacao, id_conversa, origem, permitir_reaplicacao, destino, origem, evento, destino))
    if cursor.rowcount != 1:
        raise ValueError("Transição recusada pelo estado atual ou mapa de etapas.")


def encerrar_conversa(id_conversa, motivo_encerramento, cursor):
    if motivo_encerramento not in MOTIVOS_ENCERRAMENTO_VALIDOS:
        raise ValueError("Motivo de encerramento inválido.")
    cursor.execute("""
        UPDATE chatbot.conversa SET status_ativa = false,
            finalizou_em = clock_timestamp(), motivo_encerramento = %s
        WHERE id_conversa = %s AND status_ativa RETURNING finalizou_em;
    """, (motivo_encerramento, id_conversa))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("SELECT finalizou_em FROM chatbot.conversa WHERE id_conversa = %s AND NOT status_ativa", (id_conversa,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Conversa ausente ao finalizar.")
    return row[0]
```

## 80. `core/integrations/whatsapp/tools/validando_phone_waba.py` (aplicar)

```python
import logging
import re

import requests

from core.integrations.whatsapp.tools.config import (
    construir_url_graph_api,
    get_meta_http_timeout,
    get_token_usuario_meta,
)
from core.logging_config import short_value


logger = logging.getLogger("whatsapp.waba")


def validar_phone_number_id_da_waba(waba_id, phone_number_id, *, waac_id=None, telefone=None):
    """Confirma na Graph API que o phone ID pertence à WABA informada."""
    waba_id = str(waba_id or "").strip()
    phone_number_id = str(phone_number_id or "").strip()

    if not waba_id:
        raise ValueError("waba_id nao informado para validacao")

    if not phone_number_id:
        raise ValueError("phone_number_id nao informado para validacao")

    url = construir_url_graph_api(f"{waba_id}/phone_numbers")
    headers = {
        "Authorization": f"Bearer {get_token_usuario_meta()}",
    }
    params = {
        "fields": "id,display_phone_number" if waac_id or telefone else "id",
        "limit": 100,
    }
    paginas_consultadas = 0

    while url:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=get_meta_http_timeout(),
        )
        paginas_consultadas += 1
        resposta = _normalizar_resposta(response)

        # print(response)
        # print(resposta)

        if not 200 <= response.status_code < 300:
            logger.error(
                "whatsapp_phone_waba_validacao_falhou | "
                "motivo=erro_http acao=bloquear_cadastro "
                "waba_id=%s phone_number_id=%s status=%s",
                short_value(waba_id),
                short_value(phone_number_id),
                response.status_code,
            )
            return response.status_code, {
                "success": False,
                "belongs": False,
                "reason": "meta_http_error",
                "meta": resposta,
            }

        numeros = resposta.get("data")

        if not isinstance(numeros, list):
            logger.error(
                "whatsapp_phone_waba_validacao_falhou | "
                "motivo=resposta_invalida acao=bloquear_cadastro "
                "waba_id=%s phone_number_id=%s status=%s",
                short_value(waba_id),
                short_value(phone_number_id),
                response.status_code,
            )
            return response.status_code, {
                "success": False,
                "belongs": False,
                "reason": "invalid_meta_response",
            }

        for numero in numeros:
            if not isinstance(numero, dict) or str(numero.get("id")) != phone_number_id:
                continue
            telefone_waba = re.sub(r"\D", "", str(numero.get("display_phone_number") or ""))
            if telefone and telefone_waba != re.sub(r"\D", "", telefone):
                return response.status_code, {"success": False, "reason": "telefone_divergente"}
            if waac_id:
                # Antes de registrar um recurso diferente, exija da Meta o mesmo
                # telefone do recurso listado na WABA. Uma resposta sem número é inconclusiva.
                consulta = requests.get(
                    construir_url_graph_api(waac_id), headers=headers,
                    params={"fields": "display_phone_number"}, timeout=get_meta_http_timeout(),
                )
                telefone_waac = _normalizar_resposta(consulta).get("display_phone_number")
                if (not consulta.ok or not telefone_waba
                        or telefone_waba != re.sub(r"\D", "", str(telefone_waac or ""))):
                    return consulta.status_code, {"success": False, "reason": "waac_nao_confirmado"}
            logger.info(
                "whatsapp_phone_waba_validacao_ok | "
                "acao=permitir_cadastro waba_id=%s "
                "phone_number_id=%s paginas=%s",
                short_value(waba_id),
                short_value(phone_number_id),
                paginas_consultadas,
            )
            return response.status_code, {
                "success": True,
                "belongs": True,
                "waba_id": waba_id,
                "phone_number_id": phone_number_id,
            }

        url = (
            resposta.get("paging", {}).get("next")
            if isinstance(resposta.get("paging"), dict)
            else None
        )
        params = None

    logger.warning(
        "whatsapp_phone_waba_validacao_negada | "
        "motivo=phone_id_nao_pertence_waba acao=bloquear_cadastro "
        "waba_id=%s phone_number_id=%s paginas=%s",
        short_value(waba_id),
        short_value(phone_number_id),
        paginas_consultadas,
    )
    return 200, {
        "success": False,
        "belongs": False,
        "reason": "phone_number_not_in_waba",
        "waba_id": waba_id,
        "phone_number_id": phone_number_id,
    }


def _normalizar_resposta(response):
    try:
        dados = response.json()

        if isinstance(dados, dict):
            return dados

        if isinstance(dados, list):
            return {"data": dados}

        return {
            "success": response.ok,
            "data": dados,
        }

    except ValueError:
        return {
            "success": response.ok,
            "text": response.text,
        }

# validar_phone_number_id_da_waba(1334896588725096,1238343616032627)
```

## 81. `core/integrations/whatsapp/tools/ativando_waba_id.py` (aplicar)

```python
import logging

import requests

from core.integrations.whatsapp.tools.config import (
    construir_url_graph_api,
    get_meta_http_timeout,
    get_token_usuario_meta,
)
from core.logging_config import short_value


logger = logging.getLogger("whatsapp.waba")


def ativar_waba_id(waba_id):
    """Assina o App atual aos webhooks da WABA recebida como argumento.

    A URL pública e o verify token do webhook continuam configurados uma única
    vez no App Meta. Na arquitetura atual, o mesmo token de usuário do sistema
    administra todas as WABAs previamente autorizadas para esse App. A WABA
    nunca é obtida do ambiente global: o identificador vem da unidade criada
    no Django Admin.
    """
    waba_id = str(waba_id or "").strip()

    if not waba_id:
        raise ValueError("waba_id nao informado para ativacao")

    url = construir_url_graph_api(f"{waba_id}/subscribed_apps")

    headers = {
        "Authorization": f"Bearer {get_token_usuario_meta()}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        timeout=get_meta_http_timeout(),
    )
    resposta = _normalizar_resposta(response)

    # print(resposta)
    # print(response)

    logger.info(
        "whatsapp_waba_subscribe_resposta | acao=subscribe_apps "
        "waba_id=%s status=%s sucesso=%s",
        short_value(waba_id),
        response.status_code,
        resposta.get("success"),
    )

    return response.status_code, resposta


def _normalizar_resposta(response):
    try:
        dados = response.json()

        if isinstance(dados, dict):
            return dados

        return {
            "success": False,
            "data": dados,
        }

    except ValueError:
        return {
            "success": False,
            "text": response.text,
        }

# ativar_waba_id(2301489160662354)
```

## 82. `callback/webhook/forms.py` (aplicar)

```python
"""Validação e provisionamento do remetente no cadastro de centrais."""

import logging
import re

from django import forms
from requests.exceptions import RequestException

from core.cache.cache_unidade import CacheUnidadesIndisponivel, validar_cache_unidades_disponivel_ou_erro
from core.integrations.whatsapp.tools.ativando_numero import registrar_numero_whatsapp
from core.integrations.whatsapp.tools.ativando_waba_id import ativar_waba_id
from core.integrations.whatsapp.tools.validando_phone_waba import validar_phone_number_id_da_waba
from .models import CentralPosVenda


logger = logging.getLogger("admin.central")


def _meta_confirmou(resultado):
    status, resposta = resultado
    return 200 <= status < 300 and isinstance(resposta, dict) and resposta.get("success") is True


class CentralPosVendaForm(forms.ModelForm):
    class Meta:
        model = CentralPosVenda
        fields = "__all__"

    def clean_telefone(self):
        valor = self.cleaned_data["telefone"]
        digitos = re.sub(r"[+ ().-]", "", valor)
        if not re.fullmatch(r"[1-9][0-9]{7,14}", digitos):
            raise forms.ValidationError("Informe o telefone da central com o código do país e DDD.")
        return digitos

    def _post_clean(self):
        super()._post_clean()
        # A validação do modelo e a de unicidade já terminaram. Edições de
        # atendimento (inclusive suspender a central) dispensam provisionamento.
        mudou_remetente = {"waba_id", "phone_number_id", "waac_id"}.intersection(self.changed_data)
        provisionar = self.instance._state.adding or bool(mudou_remetente)
        if self.errors or not (provisionar or "telefone" in self.changed_data):
            return

        central = self.instance
        try:
            validar_cache_unidades_disponivel_ou_erro()
        except CacheUnidadesIndisponivel:
            self.add_error(None, "O Redis está indisponível. Tente cadastrar o remetente novamente.")
            return

        try:
            vinculo = validar_phone_number_id_da_waba(
                central.waba_id, central.phone_number_id, waac_id=central.waac_id, telefone=central.telefone,
            )
            if not _meta_confirmou(vinculo):
                self.add_error(None, "A Meta não confirmou o telefone e os identificadores do remetente desta central.")
                return
            if not provisionar:
                return
            if not _meta_confirmou(ativar_waba_id(central.waba_id)):
                self.add_error("waba_id", "A Meta não confirmou a assinatura da conta para receber webhooks.")
                return
            registro = registrar_numero_whatsapp(
                central.phone_number_id, id_registro=central.waac_id or central.phone_number_id,
            )
            if not _meta_confirmou(registro):
                self.add_error("phone_number_id", "A conta foi assinada, mas a Meta não confirmou o registro do número.")
        except (RequestException, RuntimeError, ValueError):
            logger.exception("provisionamento_central_sem_confirmacao")
            self.add_error(None, "Não foi possível confirmar o cadastro completo na Meta. Confira o registro e tente novamente.")
```

## 83. `core/cache/cache_unidade.py` (aplicar)

```python
import logging
import threading
import time
from redis.exceptions import WatchError

from core.database.connection_aws import get_conn
from core.cache.redis_client import get_redis_safe
from core.logging_config import short_value
from core.repositories.unidades.cache_control import buscar_versao_cache_unidades
from core.repositories.unidades.consultas import (
    buscar_id_unidade_por_phone_id,
    exigir_unidade_habilitada_por_phone_id,
    pegar_unidades,
)


logger = logging.getLogger("cache.unidades")

REDIS_KEY = "baratao:centrais_cache"
CACHE_VERSION_KEY = "baratao:centrais_cache_version"
CACHE_DB_VERSION_KEY = "baratao:centrais_cache_db_version"
CACHE_TEMP_KEY = f"{REDIS_KEY}:tmp"
VERSAO_CHECK_INTERVAL_SEGUNDOS = 300

_redis_unidades_falhou = False
_ultima_checagem_versao = 0
_versao_lock = threading.Lock()


class UnidadeNaoEncontrada(Exception):
    pass


class CacheUnidadesIndisponivel(Exception):
    pass


class ValidacaoUnidadeIndisponivel(Exception):
    pass


def recarregar_cache_unidades():
    conn = None

    try:
        conn = get_conn(application_name="cache_chatbot")
        cursor = conn.cursor()
        return carregar_cache_redis(cursor)

    except Exception as exc:
        logger.exception("cache_recarregar_falhou | origem=admin acao=manter_cache_atual erro=%s", exc)
        return None

    finally:
        if conn:
            conn.close()


def validar_cache_unidades_disponivel_ou_erro():
    try:
        r = get_redis_safe(retries=1, delay=0, validate=True)
        key = f"{REDIS_KEY}:admin_preflight"
        r.set(key, "ok", ex=10)
        r.delete(key)

        logger.debug("cache_unidades_preflight_ok | acao=permitir_admin")
        return True

    except Exception as exc:
        _marcar_redis_falhou()
        logger.exception(
            "cache_unidades_preflight_falhou | acao=bloquear_admin erro=%s",
            exc,
        )
        raise CacheUnidadesIndisponivel(
            "Redis indisponivel para atualizar cache de unidades"
        ) from exc


def recarregar_cache_unidades_ou_erro(cursor=None):
    conn = None

    try:
        cursor_uso = cursor

        if cursor_uso is None:
            conn = get_conn(application_name="cache_chatbot")
            cursor_uso = conn.cursor()

        return carregar_cache_redis(
            cursor_uso,
            redis_retries=1,
            redis_delay=0,
        )

    except Exception as exc:
        _marcar_redis_falhou()
        logger.exception(
            "cache_recarregar_falhou | origem=admin acao=sinalizar_cache_pendente erro=%s",
            exc,
        )
        raise CacheUnidadesIndisponivel(
            "Redis falhou ao recriar cache de unidades"
        ) from exc

    finally:
        if conn:
            conn.close()


def carregar_cache_redis(cursor, redis_retries=3, redis_delay=2):
    r = get_redis_safe(retries=redis_retries, delay=redis_delay)
    # Outro processo pode publicar uma edição do Admin enquanto lemos o banco.
    # Se isso ocorrer, releia os dados antes de substituir o mapa inteiro.
    for tentativa in range(2):
        with r.pipeline() as pipe:
            try:
                pipe.watch(CACHE_DB_VERSION_KEY)
                versao_banco = buscar_versao_cache_unidades(cursor)
                unidades = _normalizar_unidades(pegar_unidades(cursor))
                pipe.multi()
                total = _salvar_cache(pipe, unidades, versao_banco)
                break
            except WatchError:
                if tentativa == 1:
                    raise

    _marcar_versao_conferida()
    logger.info("cache_atualizado | acao=salvar_redis unidades=%s versao=%s", total, versao_banco)
    return total


def obter_id_unidade_redis_ou_plsql(id_phone_unidade, cursor, *, central_da_fila=None):
    phone_key = _normalizar_phone_number_id(id_phone_unidade)

    if phone_key is None:
        raise UnidadeNaoEncontrada("phone_number_id invalido")

    try:
        r = get_redis_safe(retries=1, delay=0, validate=False)
        _sincronizar_cache_unidades_por_versao(r, origem="worker", cursor=cursor)

        if _cache_valido(r):
            id_unidade = r.hget(REDIS_KEY, phone_key)

            if _id_unidade_valido(id_unidade) and (central_da_fila is None or int(id_unidade) == central_da_fila):
                return int(id_unidade)

            logger.info("cache_central_miss | acao=confirmar_no_banco origem=worker phone_number_id=%s",
                        short_value(phone_key))
        else:
            logger.warning("cache_invalido | acao=fallback_banco origem=worker phone_number_id=%s",
                           short_value(phone_key))

    except Exception as exc:
        _marcar_redis_falhou()
        logger.warning(
            "cache_indisponivel | acao=fallback_banco origem=worker phone_number_id=%s erro=%s",
            short_value(phone_key),
            exc,
        )

    # O banco distingue ausência de suspensão, que preserva a mensagem pendente.
    id_unidade = exigir_unidade_habilitada_por_phone_id(phone_key, cursor)
    if central_da_fila is not None and id_unidade != central_da_fila:
        # O número pode ter sido alterado no Admin depois do dequeue. No retry,
        # o dequeue volta a ler o remetente da central vinculada à mensagem.
        raise RuntimeError("Remetente da central mudou durante o processamento da fila")
    if id_unidade is None:
        raise UnidadeNaoEncontrada(f"Unidade nao encontrada: {phone_key}")

    _tentar_recarregar_cache(cursor, origem="worker")
    return id_unidade


def unidade_esta_ativa(phone_number_id):
    phone_key = _normalizar_phone_number_id(phone_number_id)

    if phone_key is None:
        return False

    try:
        r = get_redis_safe(retries=1, delay=0, validate=False)
        _sincronizar_cache_unidades_por_versao(r, origem="webhook")

        if _cache_valido(r):
            if r.hexists(REDIS_KEY, phone_key):
                return True

            logger.info(
                "cache_unidade_miss | acao=confirmar_no_banco origem=webhook phone_number_id=%s",
                short_value(phone_key),
            )
            return _unidade_esta_ativa_banco_e_repara_cache(
                phone_key,
                reparar_cache_se_ausente=False,
            )

        logger.warning(
            "cache_invalido | acao=fallback_banco origem=webhook phone_number_id=%s",
            short_value(phone_key),
        )

    except ValidacaoUnidadeIndisponivel:
        raise

    except Exception as exc:
        _marcar_redis_falhou()
        logger.warning(
            "cache_indisponivel | acao=fallback_banco origem=webhook phone_number_id=%s erro=%s",
            short_value(phone_key),
            exc,
        )

    return _unidade_esta_ativa_banco_e_repara_cache(
        phone_key,
        reparar_cache_se_ausente=True,
    )


def _unidade_esta_ativa_banco_e_repara_cache(
    phone_key,
    reparar_cache_se_ausente=True,
):
    conn = None

    try:
        conn = get_conn(application_name="webhook_chatbot")
        cursor = conn.cursor()

        id_unidade = buscar_id_unidade_por_phone_id(phone_key, cursor)
        unidade_encontrada = _id_unidade_valido(id_unidade)

        if unidade_encontrada or reparar_cache_se_ausente:
            _tentar_recarregar_cache(cursor, origem="webhook")

        return unidade_encontrada

    except Exception as exc:
        logger.exception(
            "fallback_banco_unidade_falhou | origem=webhook acao=levantar_indisponibilidade phone_number_id=%s erro=%s",
            short_value(phone_key),
            exc,
        )
        raise ValidacaoUnidadeIndisponivel(
            "Nao foi possivel validar a unidade no Redis nem no banco"
        ) from exc

    finally:
        if conn:
            conn.close()


def _sincronizar_cache_unidades_por_versao(r, origem, cursor=None):
    if not _deve_conferir_versao():
        return None

    with _versao_lock:
        if not _deve_conferir_versao():
            return None

        conn = None

        try:
            cursor_uso = cursor

            if cursor_uso is None:
                conn = get_conn(application_name=_application_name_por_origem(origem))
                cursor_uso = conn.cursor()

            versao_banco = buscar_versao_cache_unidades(cursor_uso)
            versao_redis = _int_ou_none(r.get(CACHE_DB_VERSION_KEY))

            if versao_redis != versao_banco or not _cache_valido(r):
                logger.info(
                    "cache_versao_divergente | origem=%s redis=%s banco=%s acao=recarregar",
                    origem,
                    versao_redis,
                    versao_banco,
                )
                return carregar_cache_redis(cursor_uso, redis_retries=1, redis_delay=0)

            _marcar_versao_conferida()
            return None

        except Exception as exc:
            _marcar_checagem_tentada()
            logger.warning(
                "cache_versao_checar_falhou | origem=%s acao=manter_cache_atual erro=%s",
                origem,
                exc,
            )
            return None

        finally:
            if conn:
                conn.close()


def _tentar_recarregar_cache(cursor, origem):
    try:
        return carregar_cache_redis(cursor, redis_retries=1, redis_delay=0)

    except Exception as exc:
        _marcar_redis_falhou()
        logger.warning(
            "cache_reparo_falhou | origem=%s acao=manter_cache_atual erro=%s",
            origem,
            exc,
        )
        return None


def _salvar_cache(pipe, unidades, versao_banco):
    total = len(unidades)

    pipe.delete(CACHE_TEMP_KEY)

    if total > 0:
        pipe.hset(CACHE_TEMP_KEY, mapping=unidades)
        pipe.rename(CACHE_TEMP_KEY, REDIS_KEY)
    else:
        pipe.delete(REDIS_KEY)

    pipe.set(CACHE_VERSION_KEY, total)
    pipe.set(CACHE_DB_VERSION_KEY, versao_banco)
    pipe.execute()

    return total


def _cache_valido(r):
    try:
        versao = r.get(CACHE_VERSION_KEY)

        if versao is None:
            return False

        total_esperado = int(versao)

        return r.hlen(REDIS_KEY) == total_esperado

    except Exception as exc:
        logger.warning(
            "cache_validacao_erro | acao=considerar_invalido_e_usar_fallback erro=%s",
            exc,
        )
        return False


def _deve_conferir_versao():
    agora = time.monotonic()

    if _redis_unidades_falhou:
        return True

    if _ultima_checagem_versao == 0:
        return True

    return (agora - _ultima_checagem_versao) >= VERSAO_CHECK_INTERVAL_SEGUNDOS


def _marcar_redis_falhou():
    global _redis_unidades_falhou
    _redis_unidades_falhou = True


def _marcar_versao_conferida():
    global _redis_unidades_falhou, _ultima_checagem_versao
    _redis_unidades_falhou = False
    _ultima_checagem_versao = time.monotonic()


def _marcar_checagem_tentada():
    global _ultima_checagem_versao
    _ultima_checagem_versao = time.monotonic()


def _int_ou_none(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _application_name_por_origem(origem):
    if origem == "worker":
        return "worker_chatbot"

    if origem == "webhook":
        return "webhook_chatbot"

    return "cache_chatbot"


def _normalizar_unidades(unidades_raw):
    if isinstance(unidades_raw, dict):
        return {
            str(phone_number_id).strip(): int(id_unidade)
            for phone_number_id, id_unidade in unidades_raw.items()
            if phone_number_id and _id_unidade_valido(id_unidade)
        }

    if isinstance(unidades_raw, list):
        unidades = {}

        for unidade in unidades_raw:
            if isinstance(unidade, dict):
                phone_number_id = unidade.get("phone_number_id")
                id_unidade = unidade.get("id_unidade")
            else:
                try:
                    phone_number_id, id_unidade = unidade[0], unidade[1]
                except (TypeError, IndexError):
                    continue

            if phone_number_id and _id_unidade_valido(id_unidade):
                unidades[str(phone_number_id).strip()] = int(id_unidade)

        return unidades

    return {}


def _id_unidade_valido(id_unidade):
    try:
        return int(id_unidade) > 0
    except (TypeError, ValueError):
        return False


def _normalizar_phone_number_id(id_phone_unidade):
    if id_phone_unidade is None:
        return None

    phone_key = str(id_phone_unidade).strip()
    return phone_key or None
```

## 84. `tests/admin_central_postgres.py` (aplicar)

```python
"""Cadastro pelo ModelAdmin real, com banco exclusivo do script testar_ubuntu.sh."""
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

import django
from django.db import connection, transaction


class CadastroCentralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv("DB_NAME") != "baratao_admin_teste" or os.getenv("DB_HOST") != "127.0.0.1":
            raise RuntimeError("Execute com o PostgreSQL temporário de testar_ubuntu.sh.")
        django.setup()
        from django.contrib import admin
        from webhook.models import CentralPosVenda

        cls.central = CentralPosVenda
        cls.admin = admin.site.get_model_admin(CentralPosVenda)
        ddl = Path(__file__).resolve().parents[1] / "core/database/deploy_database/schema.sql"
        with connection.cursor() as cur:
            cur.execute("CREATE SCHEMA chatbot")
        from django.core.management import call_command
        call_command("migrate", interactive=False, verbosity=0)
        with connection.cursor() as cur:
            cur.execute(ddl.read_text(encoding="utf-8"))

    def setUp(self):
        self.central.objects.all().delete()
        self.request = Mock()
        self.dados = dict(nome="Central QA", nome_agente="Theo", genero_agente="masculino",
                          ativa=True, waba_id="100", phone_number_id="101", telefone="551199990001",
                          telefone_baratao="551199990002", telefone_atacadao="551199990003")
        self.chamadas = Mock()
        for funcao in ("validar_cache_unidades_disponivel_ou_erro", "validar_phone_number_id_da_waba",
                       "ativar_waba_id", "registrar_numero_whatsapp"):
            mock = self.enterContext(patch("webhook.forms." + funcao, return_value=(200, {"success": True})))
            self.chamadas.attach_mock(mock, funcao)
        self.publicar = self.enterContext(patch("webhook.admin.recarregar_cache_unidades_ou_erro"))

    def formulario(self, obj=None):
        classe = self.admin.get_form(self.request, obj)
        return classe(data=self.dados, instance=obj)

    def salvar(self, obj=None):
        form = self.formulario(obj)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        obj = form.save(commit=False)
        self.admin.save_model(self.request, obj, form, not obj._state.adding)
        return obj

    def test_provisiona_antes_de_salvar_e_publica_depois_do_commit(self):
        self.dados["waac_id"] = "901"
        with transaction.atomic():
            self.salvar()
            self.assertTrue(self.central.objects.filter(waac_id="901").exists())
            self.publicar.assert_not_called()
        self.assertEqual(self.chamadas.mock_calls, [
            call.validar_cache_unidades_disponivel_ou_erro(),
            call.validar_phone_number_id_da_waba("100", "101", waac_id="901", telefone=self.dados["telefone"]),
            call.ativar_waba_id("100"), call.registrar_numero_whatsapp("101", id_registro="901"),
        ])
        self.publicar.assert_called_once()

    def test_rollback_descarta_publicacao_e_central(self):
        with transaction.atomic():
            self.salvar()
            transaction.set_rollback(True)
        self.chamadas.registrar_numero_whatsapp.assert_called_once_with("101", id_registro="101")
        self.assertFalse(self.central.objects.exists())
        self.publicar.assert_not_called()

    def test_vinculo_recusado_impede_assinatura(self):
        self.chamadas.validar_phone_number_id_da_waba.return_value = (200, {"success": False})
        self.assertFalse(self.formulario().is_valid())
        self.chamadas.ativar_waba_id.assert_not_called()
        self.assertFalse(self.central.objects.exists())

    def test_falha_no_preflight_impede_chamar_a_meta(self):
        from core.cache.cache_unidade import CacheUnidadesIndisponivel

        self.chamadas.validar_cache_unidades_disponivel_ou_erro.side_effect = CacheUnidadesIndisponivel()
        self.assertFalse(self.formulario().is_valid())
        self.chamadas.validar_phone_number_id_da_waba.assert_not_called()
        self.assertFalse(self.central.objects.exists())

    def test_numero_ja_cadastrado_falha_antes_do_provisionamento(self):
        self.salvar()
        self.chamadas.reset_mock()
        self.assertIn("phone_number_id", self.formulario().errors)
        self.assertEqual(self.chamadas.mock_calls, [])

    def test_sem_confirmacao_da_assinatura_ou_registro(self):
        self.chamadas.ativar_waba_id.return_value = (403, {"success": True})
        self.assertIn("waba_id", self.formulario().errors)
        self.chamadas.registrar_numero_whatsapp.assert_not_called()
        self.chamadas.ativar_waba_id.return_value = (200, {"success": True})
        self.chamadas.registrar_numero_whatsapp.return_value = (200, {})
        self.assertIn("phone_number_id", self.formulario().errors)
        self.assertFalse(self.central.objects.exists())
        self.publicar.assert_not_called()

    def test_suspender_com_redis_fora_preserva_decisao_no_banco(self):
        from core.cache.cache_unidade import CacheUnidadesIndisponivel

        obj = self.salvar()
        self.chamadas.reset_mock()
        self.dados["ativa"] = False
        self.publicar.side_effect = CacheUnidadesIndisponivel()
        with patch.object(self.admin, "message_user") as aviso, transaction.atomic():
            self.salvar(obj)
        obj.refresh_from_db()
        self.assertFalse(obj.ativa)
        self.assertEqual(self.chamadas.mock_calls, [])
        aviso.assert_called_once()

    def test_troca_de_remetente_exige_nova_validacao(self):
        obj = self.salvar()
        self.chamadas.reset_mock()
        self.dados["phone_number_id"] = "202"
        self.chamadas.validar_phone_number_id_da_waba.return_value = (403, {})
        self.assertFalse(self.formulario(obj).is_valid())
        obj.refresh_from_db()
        self.assertEqual(obj.phone_number_id, "101")
        self.chamadas.registrar_numero_whatsapp.assert_not_called()

    def test_rotas_graph_do_cadastro_com_waac(self):
        from core.integrations.whatsapp.tools import ativando_numero, ativando_waba_id, validando_phone_waba

        self.chamadas.validar_phone_number_id_da_waba.side_effect = validando_phone_waba.validar_phone_number_id_da_waba
        self.chamadas.ativar_waba_id.side_effect = ativando_waba_id.ativar_waba_id
        self.chamadas.registrar_numero_whatsapp.side_effect = ativando_numero.registrar_numero_whatsapp
        self.dados["waac_id"] = "901"

        def resposta(dados):
            http = Mock(status_code=200, ok=True)
            http.json.return_value = dados
            return http

        numeros = {"data": [{"id": "101", "display_phone_number": "+55 11 9999-0001"}]}
        get = self.enterContext(patch("requests.get", side_effect=[
            resposta(numeros), resposta({"display_phone_number": "551199990009"}),
            resposta(numeros), resposta({"display_phone_number": "551199990001"}),
        ]))
        post = self.enterContext(patch("requests.post", return_value=resposta({"success": True})))
        self.enterContext(patch.object(ativando_numero, "get_phone_registration_pin", return_value="123456"))
        self.assertFalse(self.formulario().is_valid())
        post.assert_not_called()
        self.salvar()
        self.assertEqual([item.args[0].split("/v27.0/")[-1] for item in get.call_args_list],
                         ["100/phone_numbers", "901", "100/phone_numbers", "901"])
        self.assertEqual([item.args[0].split("/v27.0/")[-1] for item in post.call_args_list],
                         ["100/subscribed_apps", "901/register"])
        self.assertEqual(post.call_args.kwargs["json"], {"messaging_product": "whatsapp", "pin": "123456"})

    @unittest.skipUnless(os.getenv("BARATAO_TEST_REDIS_SOCKET"), "Requer socket de Redis exclusivo da suíte.")
    def test_admin_worker_e_webhook_compartilham_mapa_real(self):
        from redis import Redis
        from core.cache import cache_unidade as cache

        redis = Redis(unix_socket_path=os.environ["BARATAO_TEST_REDIS_SOCKET"], decode_responses=True)
        self.addCleanup(redis.close)
        self.enterContext(patch.object(cache, "get_redis_safe", return_value=redis))
        self.publicar.side_effect = cache.recarregar_cache_unidades_ou_erro
        obj = self.salvar()
        self.assertEqual(redis.hget(cache.REDIS_KEY, "101"), str(obj.pk))

        # A quantidade e a versão ainda conferem, mas o número verdadeiro sumiu.
        with redis.pipeline() as pipe:
            pipe.hdel(cache.REDIS_KEY, "101").hset(cache.REDIS_KEY, "espurio", obj.pk).execute()
        with connection.cursor() as cursor:
            self.assertEqual(cache.obter_id_unidade_redis_ou_plsql("101", cursor, central_da_fila=obj.pk), obj.pk)
        self.assertEqual(redis.hgetall(cache.REDIS_KEY), {"101": str(obj.pk)})
        # Uma segunda publicação concorrente invalida WATCH. O primeiro
        # processo precisa reler o catálogo antes de substituir essa versão.
        ler_centrais = cache.pegar_unidades
        def publicar_durante_leitura(cursor):
            if leitura.call_count == 1:
                redis.incr(cache.CACHE_DB_VERSION_KEY)
            return ler_centrais(cursor)
        with patch.object(cache, "pegar_unidades", side_effect=publicar_durante_leitura) as leitura:
            with connection.cursor() as cursor:
                cache.carregar_cache_redis(cursor)
            self.assertEqual(leitura.call_count, 2)
        redis.delete(cache.REDIS_KEY)
        self.assertTrue(cache.unidade_esta_ativa("101"))
        self.assertEqual(redis.hgetall(cache.REDIS_KEY), {"101": str(obj.pk)})

        self.dados["ativa"] = False
        with transaction.atomic():
            self.salvar(obj)
            self.assertTrue(redis.hexists(cache.REDIS_KEY, "101"))
        self.assertFalse(redis.hexists(cache.REDIS_KEY, "101"))
        self.assertFalse(cache.unidade_esta_ativa("101"))

    def navegador_admin(self):
        from django.contrib.auth import get_user_model
        from django.test import Client

        gestor, _ = get_user_model().objects.get_or_create(
            username="gestor-qa", defaults={"is_staff": True, "is_superuser": True},
        )
        navegador = Client()
        navegador.force_login(gestor)
        return navegador

    def test_modelos_cobrem_as_colunas_e_telas_listam_no_schema_vigente(self):
        from django.apps import apps
        from django.contrib import admin
        from django.urls import reverse

        app = apps.get_app_config("webhook")
        navegador = self.navegador_admin()
        with connection.cursor() as cur:
            tabelas = set(connection.introspection.table_names(cur))
            self.assertEqual({m._meta.db_table for m in app.get_models()},
                             {t for t in tabelas if not t.startswith(("auth_", "django_"))})
            for modelo in app.get_models():
                with self.subTest(modelo=modelo.__name__):
                    campos = {c.column for c in modelo._meta.local_concrete_fields if c.column}
                    descricao = connection.introspection.get_table_description(cur, modelo._meta.db_table)
                    self.assertEqual(campos, {c.name for c in descricao})
                    list(modelo.objects.all()[:1])
                    if admin.site.is_registered(modelo):
                        url = reverse(f"admin:webhook_{modelo._meta.model_name}_changelist")
                        self.assertEqual(navegador.get(url).status_code, 200)
        self.assertEqual(navegador.get(reverse("admin:webhook_centralposvenda_add")).status_code, 200)

    def test_exclusao_admin_preserva_historico_e_libera_central_sem_atendimento(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse
        from django.utils.timezone import now
        from webhook.models import Chat, Cliente, ConsumoMetaColeta, MonitoramentoAcesso

        central = self.salvar()
        navegador = self.navegador_admin()
        url = reverse("admin:webhook_centralposvenda_delete", args=(central.pk,))
        titular = Cliente.objects.create(nome_titular="Titular de teste")
        chat = Chat.objects.create(central=central, cliente=titular)
        self.addCleanup(Chat.objects.filter(pk=chat.pk).delete)
        self.publicar.reset_mock()
        previa = navegador.get(url)
        self.assertEqual(previa.status_code, 200)
        self.assertIn("chat", previa.content.decode().lower())
        self.assertTrue(self.central.objects.filter(pk=central.pk).exists())
        self.publicar.assert_not_called()
        chat.delete()
        MonitoramentoAcesso.objects.create(central=central, usuario=get_user_model().objects.get(username="gestor-qa"))
        ConsumoMetaColeta.objects.create(central=central, periodo="conta", proxima_consulta_em=now())
        self.assertEqual(navegador.post(url, {"post": "yes"}).status_code, 302)
        self.assertFalse(self.central.objects.filter(pk=central.pk).exists())
        self.assertFalse(MonitoramentoAcesso.objects.filter(central=central).exists())
        self.assertFalse(ConsumoMetaColeta.objects.filter(central=central).exists())
        self.publicar.assert_called_once()

    def test_consultas_e_permissoes_de_acesso_por_central(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from django.urls import reverse
        from webhook.models import MonitoramentoAcesso

        central = self.salvar()
        navegador = self.navegador_admin()
        for tipo in self.admin.consultas:
            url = reverse("admin:webhook_centralposvenda_consultar", args=(central.pk, tipo))
            self.assertEqual(navegador.get(url).status_code, 200)
        url = reverse("admin:webhook_centralposvenda_consultar", args=(central.pk, "acessos"))
        operador, _ = get_user_model().objects.get_or_create(username="operador-qa")
        leitor, _ = get_user_model().objects.get_or_create(username="leitor-qa", defaults={"is_staff": True})
        self.assertEqual(navegador.post(url, {"acao": "vincular", "usuario": operador.pk}).status_code, 302)
        navegador.force_login(leitor)
        leitor.user_permissions.add(*Permission.objects.filter(content_type__app_label="webhook",
            codename__in=("view_centralposvenda", "view_monitoramentoacesso")))
        self.assertEqual(navegador.get(url).status_code, 200)
        self.assertEqual(navegador.post(url, {"acao": "remover", "chave": operador.pk}).status_code, 403)
        self.assertTrue(MonitoramentoAcesso.objects.filter(central=central, usuario=operador).exists())
        self.assertEqual(self.navegador_admin().post(url, {"acao": "remover", "chave": operador.pk}).status_code, 302)
        self.assertFalse(MonitoramentoAcesso.objects.filter(central=central, usuario=operador).exists())


    def test_corrigir_telefone_confere_numero_da_meta_sem_registrar_de_novo(self):
        from core.integrations.whatsapp.tools.validando_phone_waba import validar_phone_number_id_da_waba

        obj = self.salvar()
        self.chamadas.reset_mock()
        self.chamadas.validar_phone_number_id_da_waba.side_effect = validar_phone_number_id_da_waba
        self.dados["telefone"] = "+55 (11) 9999-0009"
        resposta = Mock(status_code=200)
        resposta.json.return_value = {"data": [{"id": "101", "display_phone_number": "+55 11 9999-0001"}]}
        self.enterContext(patch("requests.get", return_value=resposta))
        self.assertFalse(self.formulario(obj).is_valid())
        obj.refresh_from_db()
        self.assertEqual(obj.telefone, "551199990001")
        resposta.json.return_value["data"][0]["display_phone_number"] = "+55 11 9999-0009"
        self.salvar(obj)
        obj.refresh_from_db()
        self.assertEqual(obj.telefone, "551199990009")
        self.chamadas.ativar_waba_id.assert_not_called()
        self.chamadas.registrar_numero_whatsapp.assert_not_called()

    def test_desbloqueio_por_central_exige_confirmacao_da_meta(self):
        from django.urls import reverse
        from webhook.models import ClienteBloqueadoMeta

        central = self.salvar()
        bloqueio = ClienteBloqueadoMeta.objects.create(central=central, wa_id_cliente="551199990005")
        self.addCleanup(ClienteBloqueadoMeta.objects.filter(pk=bloqueio.pk).delete)
        navegador = self.navegador_admin()
        url = reverse("admin:webhook_centralposvenda_consultar", args=(central.pk, "bloqueios"))
        desbloquear = self.enterContext(patch("webhook.admin_relacoes.desbloquear_usuario_meta"))
        desbloquear.side_effect = RuntimeError("Falha simulada")
        dados = {"acao": "desbloquear", "chave": bloqueio.wa_id_cliente}
        self.assertEqual(navegador.post(url, dados).status_code, 302)
        self.assertTrue(ClienteBloqueadoMeta.objects.filter(pk=bloqueio.pk).exists())
        desbloquear.side_effect = None
        self.assertEqual(navegador.post(url, dados).status_code, 302)
        self.assertFalse(ClienteBloqueadoMeta.objects.filter(pk=bloqueio.pk).exists())
        desbloquear.assert_called_with("551199990005", "101")
```

## 85. `deploy/testar_ubuntu.sh` (aplicar)

```bash
#!/usr/bin/env bash
# pg_virtualenv cria e remove um PostgreSQL exclusivo para esta execução.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="$PWD"
export PYTHONDONTWRITEBYTECODE=1
export PYTHON_DOTENV_DISABLED=1
export BARATAO_PYTHON="${BARATAO_PYTHON:-/opt/chatbot/venv/bin/python}"
exec pg_virtualenv bash -eu -o pipefail -c '
    export PGHOST=127.0.0.1
    createdb baratao_fluxo_teste
    createdb baratao_consumo_teste
    export BARATAO_TEST_DSN="host=$PGHOST port=$PGPORT user=$PGUSER dbname=baratao_fluxo_teste"
    export BARATAO_CONSUMO_TEST_DSN="host=$PGHOST port=$PGPORT user=$PGUSER dbname=baratao_consumo_teste"
    export DB_HOST="$PGHOST" DB_PORT="$PGPORT" DB_USER="$PGUSER" DB_PASSWORD="$PGPASSWORD" DB_NAME=baratao_fluxo_teste
    export DB_SSLMODE=disable DB_SSLROOTCERT="" REDIS_HOST=127.0.0.1 REDIS_PORT=1
    export META_ACCESS_TOKEN=token-de-teste META_GRAPH_API_VERSION=27.0 META_WEBHOOK_VERIFY_TOKEN=teste
    export META_APP_SECRET=teste DJANGO_SECRET_KEY=chave-local-de-teste DJANGO_ALLOWED_HOSTS=localhost,testserver
    "$BARATAO_PYTHON" -m unittest discover -s tests -v
    createdb baratao_admin_teste
    cd callback
    DB_NAME=baratao_admin_teste PYTHONPATH="$PWD:$PWD/.." DJANGO_SETTINGS_MODULE=callback.settings \
        "$BARATAO_PYTHON" -m unittest -v tests.admin_central_postgres
'
```

## 86. `core/integrations/whatsapp/messages/tratamentos/midia.py` (aplicar)

```python
"""Orientação de formato para entradas não suportadas no pós-venda."""
from core.etapas_pos_venda import ETAPA_NOME, ETAPA_CPF, ETAPA_DETALHES

AVISO_MIDIA = "Olha, só consigo entender mensagens de texto."

PERGUNTAS_POR_TEXTO = {
    ETAPA_NOME: "Me informe novamente o nome completo do titular da compra.",
    ETAPA_CPF: "Em uma única mensagem, me informe o CPF do titular da compra.",
    ETAPA_DETALHES: "Descreva em texto a sua situação e o que você precisa.",
}


def avisar_sobre_midia(pergunta):
    return f"{AVISO_MIDIA}\n\n{pergunta}"
```

## 87. `core/integrations/whatsapp/pywa_functions/pywa_senders/etapa3.py` (aplicar)

```python
"""Apresentação e repetição da pergunta de produto; sem validar a entrada."""

from pywa.types import Button

from core.integrations.whatsapp.messages.tratamentos.midia import avisar_sobre_midia
from core.etapas_pos_venda import ETAPA_PRODUTO
from core.integrations.whatsapp.messages.etapa3_messages import (
    montar_mensagem_etapa3, BOTOES_PRODUTO, MENSAGEM_PRODUTO_INVALIDO, RODAPE_PRODUTO,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa3(cliente_telefone, phone_id_unidade, *, nome_titular=None, invalido=False, midia=False):
    botoes = [
        Button(title=titulo, callback_data=identificador)
        for titulo, identificador in BOTOES_PRODUTO
    ]
    mensagem = MENSAGEM_PRODUTO_INVALIDO if invalido else montar_mensagem_etapa3(nome_titular)
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade,
        avisar_sobre_midia(mensagem) if midia else mensagem,
        ETAPA_PRODUTO, botoes=botoes, rodape=RODAPE_PRODUTO,
    )
    if invalido:
        envio.update(tratamento=True, tipo_tratamento="produto_invalido")
    return envio
```

## 88. `core/integrations/whatsapp/pywa_functions/pywa_senders/etapa4.py` (aplicar)

```python
"""Envia a lista de assuntos; não interpreta nem persiste a escolha."""

from pywa.types import Section, SectionList, SectionRow
from core.integrations.whatsapp.messages.tratamentos.midia import avisar_sobre_midia
from core.etapas_pos_venda import ETAPA_ASSUNTO
from core.integrations.whatsapp.messages.etapa4_messages import (
    MENSAGEM_ASSUNTO, MENSAGEM_ASSUNTO_INVALIDO, OPCOES_ASSUNTO,
)
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa4(cliente_telefone, phone_id_unidade, *, invalido=False, midia=False):
    lista = SectionList(button_title="Escolher assunto", sections=[Section(
        title="Assunto do atendimento",
        rows=[SectionRow(title=titulo, callback_data=f"assunto:{valor}", description=descricao)
              for titulo, valor, descricao in OPCOES_ASSUNTO],
    )])
    mensagem = MENSAGEM_ASSUNTO_INVALIDO if invalido else MENSAGEM_ASSUNTO
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade,
        avisar_sobre_midia(mensagem) if midia else mensagem,
        ETAPA_ASSUNTO, botoes=lista,
    )
    if invalido:
        envio.update(tratamento=True, tipo_tratamento="assunto_invalido")
    return envio
```

## 89. `core/integrations/whatsapp/pywa_functions/pywa_senders/etapa5_pedidos.py` (aplicar)

```python
"""Envia a pergunta de pedidos após a escolha do assunto."""
from pywa.types import Button

from core.integrations.whatsapp.messages.tratamentos.midia import avisar_sobre_midia
from core.etapas_pos_venda import ETAPA_PEDIDOS
from core.integrations.whatsapp.messages.etapa5_pedidos_messages import (
    BOTAO_NOTA_PERDIDA, MENSAGEM_PEDIDOS, MENSAGEM_PEDIDO_INVALIDO, MENSAGEM_PEDIDOS_INVALIDOS,
)
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa5_pedidos(cliente_telefone, phone_id_unidade, *, quantidade_para_correcao=None, midia=False):
    mensagem = MENSAGEM_PEDIDOS
    if quantidade_para_correcao is not None:
        mensagem = MENSAGEM_PEDIDOS_INVALIDOS if quantidade_para_correcao >= 2 else MENSAGEM_PEDIDO_INVALIDO
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade, avisar_sobre_midia(mensagem) if midia else mensagem,
        ETAPA_PEDIDOS,
        botoes=[Button(title=BOTAO_NOTA_PERDIDA, callback_data="pedidos:nota_perdida")],
    )
    if quantidade_para_correcao is not None:
        envio.update(tratamento=True, tipo_tratamento="pedido_invalido")
    return envio
```

## 90. `core/integrations/whatsapp/pywa_functions/pywa_senders/repeticao_midia.py` (aplicar)

```python
"""Repete a pergunta com o mesmo controle interativo oferecido pela etapa."""
from core.etapas_pos_venda import ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS
from core.integrations.whatsapp.messages.tratamentos.midia import PERGUNTAS_POR_TEXTO, avisar_sobre_midia
from .etapa3 import enviar_etapa3
from .etapa4 import enviar_etapa4
from .etapa5_pedidos import enviar_etapa5_pedidos
from .texto_pos_venda import enviar_texto_pos_venda

_INTERATIVOS = {
    ETAPA_PRODUTO: enviar_etapa3,
    ETAPA_ASSUNTO: enviar_etapa4,
    ETAPA_PEDIDOS: enviar_etapa5_pedidos,
}


def enviar_repeticao_midia(destinatario, remetente, etapa):
    if etapa in _INTERATIVOS:
        envio = _INTERATIVOS[etapa](destinatario, remetente, midia=True)
    else:
        texto = avisar_sobre_midia(PERGUNTAS_POR_TEXTO[etapa])
        envio = enviar_texto_pos_venda(destinatario, remetente, texto, etapa)
    return dict(envio, tratamento=True, tipo_tratamento="midia_na_etapa")
```

## 91. `core/validacoes/encaminhamento_pos_venda.py` (aplicar)

```python
"""Classificação da entrada e destino do encaminhamento humano."""
from core.etapas_pos_venda import ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS
from core.validacoes.produto_pos_venda import TIPOS_INTERATIVOS_PRODUTO
from core.validacoes.assunto_pos_venda import TIPOS_INTERATIVOS_ASSUNTO
from core.validacoes.pedidos_pos_venda import TIPOS_INTERATIVOS_PEDIDO

LIMITE_TURNOS_SEM_AVANCO = 3

_INTERATIVOS_POR_ETAPA = {
    ETAPA_PRODUTO: TIPOS_INTERATIVOS_PRODUTO,
    ETAPA_ASSUNTO: TIPOS_INTERATIVOS_ASSUNTO,
    ETAPA_PEDIDOS: TIPOS_INTERATIVOS_PEDIDO,
}


def entrada_nao_suportada(etapa, tipo):
    return tipo != "text" and tipo not in _INTERATIVOS_POR_ETAPA.get(etapa, ())


def pediu_humano(tipo, texto):
    return tipo == "text" and "humano" in (texto or "").casefold()


def grupos_encaminhamento(contexto):
    """Usa todas as notas aceitas da conversa, inclusive no encaminhamento antecipado."""
    grupos = contexto.get("grupos_das_notas") or set()
    if not contexto.get("perdeu_nota"):
        if grupos == {"Atacadão"}:
            return ("atacadao",)
        if grupos == {"Baratão"}:
            return ("baratao",)
    return ("atacadao", "baratao")
```

## 92. `deploy/migrations/20261127_midia_repete_etapa.sql` (aplicar)

```sql
-- Beta V0.2.0. Reaplicável na base Baratão de sete etapas.
BEGIN;
SET LOCAL lock_timeout = '8s';
LOCK TABLE chatbot.etapa_transicao IN SHARE ROW EXCLUSIVE MODE;

DELETE FROM chatbot.etapa_transicao
WHERE id_etapa_origem BETWEEN 1 AND 6 AND evento = 'midia_recebida' AND id_etapa_destino = 7;

DO $conferir$
BEGIN
    IF (SELECT array_agg(nome_etapa::text ORDER BY id_etapa) FROM chatbot.etapa)
        IS DISTINCT FROM ARRAY['nome_titular','cpf_titular','produto','assunto','pedidos','detalhes','encaminhamento']
        OR (SELECT count(*) FROM chatbot.etapa_transicao) <> 21
        OR EXISTS (SELECT FROM chatbot.etapa_transicao WHERE evento='midia_recebida')
        OR (SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem BETWEEN 1 AND 6
            AND evento IN ('humano_solicitado','limite_sem_avanco') AND id_etapa_destino=7) <> 12 THEN
        RAISE EXCEPTION 'Catálogo incompatível com o fluxo de mídia da Beta V0.2.0';
    END IF;
END
$conferir$;
COMMIT;
```

## 93. `tests/test_arquitetura_pos_venda.py` (aplicar)

```python
"""Contrato das camadas e efeitos autorizados por etapa, sem serviços externos."""

import ast
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa

ROOT = Path(__file__).resolve().parents[1]


def contexto_efeitos(etapa):
    mapas = {
        1: {"nome_valido_falta_cpf": 2},
        2: {"cpf_valido": 3},
    }
    return {
        "id_cliente": 7, "id_conversa": 8, "id_etapa_origem_transicao": etapa,
        "transicoes_permitidas": dict(mapas.get(etapa, {}), humano_solicitado=7, limite_sem_avanco=7),
    }


class EfeitosPorEtapaTests(unittest.TestCase):
    def setUp(self):
        self.cursor = MagicMock()
        self.cursor.rowcount = 1

    def persistir(self, etapa, **envio):
        return atualizar_banco_conforme_transicao_de_etapa(
            contexto_efeitos(etapa), envio, self.cursor,
        )

    def test_nome_confirmado_grava_cliente_e_atendimento(self):
        efeito = self.persistir(
            1, evento_transicao="nome_valido_falta_cpf", id_etapa_resultante=2,
            nome_titular="João da Silva",
        )
        self.assertEqual(efeito, {"nome_titular": "João da Silva"})
        self.assertEqual([c.args[1] for c in self.cursor.execute.call_args_list],
                         [("João da Silva", 7), ("João da Silva", 8)])

    def test_cpf_confirmado_grava_global_e_snapshot_para_ambos_destinos(self):
        for evento, destino in (("cpf_valido", 3),):
            with self.subTest(evento=evento):
                self.cursor.reset_mock()
                efeito = self.persistir(
                    2, evento_transicao=evento, id_etapa_resultante=destino,
                    cpf_titular="01234567890",
                )
                self.assertEqual(efeito, {"cpf_titular": "01234567890"})
                self.assertEqual([c.args[1] for c in self.cursor.execute.call_args_list],
                                 [("01234567890", 7), ("01234567890", 8)])

    def test_saudacao_e_repeticoes_nao_gravam_dados_ou_contam_turnos_aqui(self):
        for etapa, envio in (
            (1, {"id_etapa_resultante": 1}),
            (1, {"tratamento": True, "id_etapa_resultante": 1}),
            (2, {"tratamento": True, "id_etapa_resultante": 2}),
        ):
            with self.subTest(etapa=etapa):
                self.assertEqual(self.persistir(etapa, **envio), {})
        self.cursor.execute.assert_not_called()

    def test_replay_nao_reaplica_dados_do_envio(self):
        self.assertEqual(self.persistir(
            2, resposta_ja_existia=True, cpf_titular="99999999999",
            id_etapa_resultante=3,
        ), {})
        self.cursor.execute.assert_not_called()

    def test_universal_das_duas_etapas_persiste_apenas_contatos(self):
        for etapa in (1, 2):
            for evento in ("humano_solicitado", "limite_sem_avanco"):
                with self.subTest(etapa=etapa, evento=evento):
                    self.cursor.reset_mock()
                    self.assertEqual(self.persistir(
                        etapa, evento_transicao=evento, id_etapa_resultante=7,
                        encaminhado_baratao="557582467000", encaminhado_atacadao="557592087803",
                    ), {"encaminhado": True})
                    self.cursor.execute.assert_called_once()
                    self.assertEqual(self.cursor.execute.call_args.args[1],
                                     ("557582467000", "557592087803", 8))

    def test_presenca_de_chave_na_etapa_errada_nao_autoriza_escrita(self):
        casos = (
            (7, {"evento_transicao": "nome_ausente", "id_etapa_resultante": 1,
                  "nome_titular": "João da Silva"}),
            (1, {"evento_transicao": "nome_valido_falta_cpf", "id_etapa_resultante": 2,
                 "cpf_titular": "01234567890"}),
            (2, {"evento_transicao": "cpf_valido", "id_etapa_resultante": 3,
                 "nome_titular": "João da Silva", "cpf_titular": "01234567890"}),
            (1, {"id_etapa_resultante": 1, "nome_titular": "João da Silva"}),
            (2, {"id_etapa_resultante": 2, "cpf_titular": "01234567890"}),
            (3, {"id_etapa_resultante": 3, "cpf_titular": "01234567890"}),
        )
        for etapa, envio in casos:
            with self.subTest(etapa=etapa, envio=envio):
                with self.assertRaises(ValueError):
                    self.persistir(etapa, **envio)
        self.cursor.execute.assert_not_called()

    def test_evento_destino_origem_e_mapa_incompativeis_impedem_escrita(self):
        base = {"evento_transicao": "cpf_valido",
                "id_etapa_resultante": 3, "cpf_titular": "01234567890"}
        for alteracao in (
            {"evento_transicao": "nome_valido_falta_cpf"},
            {"id_etapa_resultante": 4},
            {"id_etapa_origem_transicao": 1},
            {"tratamento": True},
        ):
            with self.subTest(alteracao=alteracao), self.assertRaises(ValueError):
                self.persistir(2, **dict(base, **alteracao))
        contexto = contexto_efeitos(2)
        contexto["transicoes_permitidas"] = {}
        with self.assertRaises(ValueError):
            atualizar_banco_conforme_transicao_de_etapa(contexto, base, self.cursor)
        self.cursor.execute.assert_not_called()

    def test_dado_obrigatorio_ausente_ou_cpf_nao_normalizado_impede_escrita(self):
        for valor in (None, "", " ", "012.345.678-90", "0123456789A", "１２３４５６７８９０１"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                self.persistir(2, evento_transicao="cpf_valido",
                               id_etapa_resultante=3, cpf_titular=valor)
        with self.assertRaises(ValueError):
            self.persistir(1, evento_transicao="nome_valido_falta_cpf", id_etapa_resultante=2)
        with self.assertRaises(ValueError):
            self.persistir(1, evento_transicao="humano_solicitado", id_etapa_resultante=7,
                           encaminhado_baratao="557582467000")
        self.cursor.execute.assert_not_called()

    def test_registro_ausente_falha_para_worker_reverter_a_transacao(self):
        self.cursor.rowcount = 0
        with self.assertRaises(ValueError):
            self.persistir(2, evento_transicao="cpf_valido",
                           id_etapa_resultante=3, cpf_titular="01234567890")


class FronteirasArquiteturaTests(unittest.TestCase):
    def test_sql_executavel_fica_nos_repositorios(self):
        desvios = []
        for pasta in ("workers", "callback", "core", "utilitarios"):
            for path in (ROOT / pasta).rglob("*.py"):
                relativo = path.relative_to(ROOT).as_posix()
                if relativo.startswith(("core/repositories/", "core/database/deploy_database/")):
                    continue
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in {"execute", "executemany", "callproc"}
                            and node.args):
                        # Redis Pipeline.execute() não recebe SQL e não entra aqui.
                        desvios.append(f"{relativo}:{node.lineno}")
        self.assertEqual(desvios, [])

    def test_camadas_internas_nao_assumem_commit_ou_rollback(self):
        desvios = []
        pastas = ("core/repositories", "core/validacoes",
                  "core/integrations/whatsapp/messages",
                  "core/integrations/whatsapp/pywa_functions/pywa_senders",
                  "workers/worker_flow/response_flow/etapas",
                  "workers/worker_flow/transacoes")
        for pasta in pastas:
            for path in (ROOT / pasta).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8-sig"))
                for node in ast.walk(tree):
                    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                            and node.func.attr in {"commit", "rollback"}):
                        desvios.append(f"{path.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(desvios, [])


if __name__ == "__main__":
    unittest.main()
```

## 94. `tests/test_etapa3_pos_venda.py` (aplicar)

```python
"""Produto: texto, botões, tratamentos, contrato dos efeitos e transporte simulado."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.produto_pos_venda import extrair_produto
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa
from tests.test_etapa1_pos_venda import contexto, ENV, PATCH_TEXTO, PATCH_CARTOES


def contexto_produto(texto="Móveis", **kwargs):
    ctx = contexto(etapa=3, texto=texto, **kwargs)
    ctx["transicoes_permitidas"] = {
        "produto_escolhido": 4,
        "humano_solicitado": 7, "limite_sem_avanco": 7,
    }
    return ctx


class ProdutoExtratorTests(unittest.TestCase):
    def test_palavras_em_frases_sem_acento_e_com_limites(self):
        casos = {
            "Quero falar sobre meus MÓVEIS.": "moveis",
            "apenas moveis": "moveis", "Meu móvel": "moveis",
            "Sobre os estofados da compra": "estofados", "Meu sofá": "estofados",
            "Estofados e Móveis": "ambos", "móveis e estofados": "ambos",
            "quero falar dos dois": "ambos", "ambos": "ambos",
            "das duas opções": "ambos", "dos dois setores": "ambos",
            "nao recebi meus moveis": "moveis",
            "não entregaram o estofado": "estofados",
            "meus móveis não chegaram": "moveis",
            "não só móveis, mas também estofados": "ambos",
            "Os móveis e os estofados não chegaram": "ambos",
        }
        for texto, produto in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(extrair_produto(texto), produto)

    def test_negacao_de_setor_e_de_ambos(self):
        casos = {
            "não quero falar de móveis": "estofados",
            "não quero falar de estofados": "moveis",
            "não é sobre móveis": "estofados",
            "Não móveis, estofados": "estofados",
            "Estofados sim, móveis não": "estofados",
            "móveis não, estofados sim": "estofados",
            "não quero móveis, quero estofados": "estofados",
            "quero móveis e não estofados": "moveis",
            "não quero falar dos dois": None,
            "não quero ambos": None,
            "não quero móveis nem estofados": None,
            "não quero falar de móveis e estofados": None,
            "nem móveis nem estofados": None,
            "nenhum dos dois": None,
            "não quero móveis, mas quero móveis": None,
        }
        for texto, produto in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(extrair_produto(texto), produto)

    def test_ausencia_ou_ambiguidade_requer_correcao(self):
        for texto in (None, "", " ", "sim", "123", "entrega", "automoveis", "imóveis",
                      "sofamento", "não sei se são móveis", "talvez estofados"):
            with self.subTest(texto=texto):
                self.assertIsNone(extrair_produto(texto))


class Etapa3Tests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.texto")
        self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.cartoes")
        for p in (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                  patch(PATCH_CARTOES, return_value=self.wa)):
            p.start()
            self.addCleanup(p.stop)

    def test_apresentacao_e_correcao_com_tres_botoes_e_rodape(self):
        for apresentacao in (True, False):
            envio = flow_sender(contexto_produto("???", apresentacao=apresentacao))
            self.assertEqual(envio["id_etapa_resultante"], 3)
            texto = ("Sobre qual tipo de produto você quer falar?" if apresentacao
                     else "Não entendi, sobre qual tipo de produto você quer falar?")
            self.assertEqual(envio["mensagem_bot"], texto)
            self.assertEqual(bool(envio.get("tratamento")), not apresentacao)
            botoes = envio["interativo"]["action"]["buttons"]
            self.assertEqual([b["reply"]["title"] for b in botoes],
                             ["Apenas Estofados", "Apenas Móveis", "Estofados e Móveis"])
            self.assertEqual(envio["interativo"]["footer"]["text"], "Selecione apenas uma opção abaixo.")
            self.assertEqual(self.wa.send_message.call_args.kwargs["footer"],
                             "Selecione apenas uma opção abaixo.")

    def test_tres_opcoes_interativas_avancam_com_lista_de_assuntos(self):
        for tipo in ("interactive", "interactive_button", "button"):
            for texto, esperado in (("Apenas Estofados", "estofados"),
                                    ("Apenas Móveis", "moveis"),
                                    ("Estofados e Móveis", "ambos"),
                                    ("produto:ambos", "ambos")):
                with self.subTest(tipo=tipo, texto=texto):
                    envio = flow_sender(contexto_produto(texto, tipo=tipo))
                    self.assertEqual(envio["id_etapa_resultante"], 4)
                    self.assertEqual(envio["produto"], esperado)
                    self.assertEqual(envio["evento_transicao"], "produto_escolhido")
                    self.assertEqual(envio["interativo"]["type"], "list")
                    self.assertEqual(len(envio["interativo"]["action"]["sections"][0]["rows"]), 5)
        self.wa.send_carousel.assert_not_called()

    def test_botao_desconhecido_repete_sem_tratar_como_midia(self):
        for texto in ("assunto:entrega", "quero falar de móveis", "sim", None):
            envio = flow_sender(contexto_produto(texto, tipo="interactive"))
            self.assertTrue(envio["tratamento"])
            self.assertEqual(envio["id_etapa_resultante"], 3)
        self.wa.send_carousel.assert_not_called()

    def test_frase_valida_e_negacao_avancam(self):
        for texto, esperado in (("não quero falar de móveis", "estofados"),
                                ("gostaria de falar dos dois", "ambos")):
            envio = flow_sender(contexto_produto(texto))
            self.assertEqual(envio["produto"], esperado)
            self.assertEqual(envio["id_etapa_resultante"], 4)

    def test_universal_tem_prioridade_sobre_escolha_e_quarto_turno(self):
        for texto, tipo, turnos, evento in (
            (None, "audio", 3, "limite_sem_avanco"),
            (None, "image", 3, "limite_sem_avanco"),
            ("humano para móveis", "text", 0, "humano_solicitado"),
            ("id_desconhecido", "interactive", 3, "limite_sem_avanco"),
            ("talvez", "text", 3, "limite_sem_avanco"),
        ):
            envio = flow_sender(contexto_produto(texto, tipo=tipo, turnos=turnos))
            self.assertEqual(envio["id_etapa_resultante"], 7)
            self.assertEqual(envio["evento_transicao"], evento)
            self.assertNotIn("produto", envio)
            self.assertIn("encaminhado_atacadao", envio)
            self.assertIn("encaminhado_baratao", envio)

    def test_mapa_invalido_impede_envio(self):
        ctx = contexto_produto()
        ctx["transicoes_permitidas"]["produto_escolhido"] = 5
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()

    def test_falha_meta_ou_falta_de_wamid_nao_devolve_produto(self):
        self.wa.send_message.side_effect = RuntimeError("Falha simulada")
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_produto())
        self.wa.send_message.side_effect = None
        self.wa.send_message.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_produto())

    def test_replay_na_etapa4_nao_envia_nem_reinterpreta(self):
        ctx = contexto_produto("Estofados")
        ctx["id_etapa_atual"] = 4
        ctx["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 4, "id_hash_msg": "wamid.confirmado",
            "interativo": {"_fluxo": {"evento": "produto_escolhido"}},
        }
        envio = flow_sender(ctx)
        self.assertTrue(envio["resposta_ja_existia"])
        self.assertNotIn("produto", envio)
        self.wa.send_message.assert_not_called()

    def test_efeito_produto_grava_somente_no_atendimento(self):
        cursor = MagicMock(rowcount=1)
        ctx = contexto_produto()
        envio = flow_sender(ctx)
        efeito = atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor)
        self.assertEqual(efeito, {"produto": "moveis"})
        cursor.execute.assert_called_once()
        self.assertIn("UPDATE chatbot.atendimento_pos_venda", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], ("moveis", 12))

    def test_dado_na_etapa_errada_e_produto_invalido_impedem_gravacao(self):
        cursor = MagicMock(rowcount=1)
        envio = {"id_etapa_resultante": 4, "evento_transicao": "produto_escolhido", "produto": "moveis"}
        for ctx, alteracao in ((contexto(etapa=1), {}), (contexto_produto(), {"produto": "outro"}),
                               (contexto_produto(), {"tratamento": True}),
                               (contexto_produto(), {"cpf_titular": "01234567890"})):
            with self.assertRaises(ValueError):
                atualizar_banco_conforme_transicao_de_etapa(ctx, dict(envio, **alteracao), cursor)
        cursor.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

## 95. `tests/test_etapa4_pos_venda.py` (aplicar)

```python
"""Contrato da lista, texto livre, efeitos por conversa e encaminhamento humano."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from callback.webhook.services.populating_fila_mensagens import extrair_conteudo_texto_mensagem
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.validacoes.assunto_pos_venda import extrair_assunto
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa
from tests.test_etapa1_pos_venda import ENV, PATCH_CARTOES, PATCH_TEXTO, contexto


def contexto_assunto(texto, *, produto="moveis", **kwargs):
    ctx = contexto(etapa=4, texto=texto, **kwargs)
    ctx["produto"] = produto
    ctx["transicoes_permitidas"]["assunto_escolhido"] = 5
    return ctx


class AssuntoTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.qa")
        for p in (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                  patch(PATCH_CARTOES, return_value=self.wa)):
            p.start()
            self.addCleanup(p.stop)

    def test_frases_reconhecem_categorias_distintas(self):
        for texto, esperado in (
            ("Qual é a previsão de entrega?", "entrega"),
            ("Meu sofá veio com avarias. Preciso de ASSISTENCIA.", "assistencia"),
            ("Preciso de um montador para a montagem", "montador"),
            ("Queria falar de outra coisa", "outros"), ("É outro assunto.", "outros"),
            ("Outros", "outros"), ("Quero a previsão e um montador", "misto"),
            ("Montagem, assistência e entrega", "misto"), ("Avarias e outro assunto", "misto"),
            ("Duas ou mais opções acima", "misto"), ("desmontagem", None),
            ("Entregador", None), ("Oi", None), ("123", None), (None, None),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(extrair_assunto(texto), esperado)

    def test_todas_as_linhas_da_lista_passam_pelo_webhook_e_gravam_no_atendimento(self):
        lista = flow_sender(contexto_assunto("", apresentacao=True))
        linhas = lista["interativo"]["action"]["sections"][0]["rows"]
        self.assertEqual([r["id"] for r in linhas], [
            "assunto:entrega", "assunto:assistencia", "assunto:montador", "assunto:misto", "assunto:outros",
        ])
        for linha in linhas:
            self.assertLessEqual(len(linha["title"]), 24)
            for opcao in (linha, {"id": linha["id"]}):
                payload = {"interactive": {"type": "list_reply", "list_reply": opcao}}
                texto = extrair_conteudo_texto_mensagem(payload, "interactive")
                ctx = contexto_assunto(texto, tipo="interactive")
                envio = flow_sender(ctx)
                assunto = linha["id"].split(":")[1]
                self.assertEqual((envio["id_etapa_resultante"], envio["evento_transicao"], envio["assunto"]),
                                 (5, "assunto_escolhido", assunto))
                self.assertEqual(envio["interativo"]["action"]["buttons"][0]["reply"]["title"], "Perdi a nota")
                cursor = MagicMock(rowcount=1)
                self.assertEqual(atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor), {"assunto": assunto})
                self.assertEqual(cursor.execute.call_args.args[1], (assunto, ctx["id_conversa"]))

    def test_entrada_invalida_repete_a_mesma_lista_sem_gravar(self):
        lista = flow_sender(contexto_assunto("", apresentacao=True))["interativo"]["action"]
        for texto, tipo in (("Oi", "text"), ("produto:ambos", "interactive"),
                            ("Mais de um ou outros", "interactive"), ("quero entrega", "interactive")):
            ctx = contexto_assunto(texto, tipo=tipo)
            envio = flow_sender(ctx)
            self.assertEqual(envio["interativo"]["action"], lista)
            self.assertEqual(envio["tipo_tratamento"], "assunto_invalido")
            self.assertTrue(envio["tratamento"])
            self.assertEqual(envio["id_etapa_resultante"], 4)
            cursor = MagicMock()
            self.assertEqual(atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor), {})
            cursor.execute.assert_not_called()

    def test_universal_antes_das_notas_oferece_as_duas_redes(self):
        for produto, entrada, tipo, turnos, evento in (
            ("moveis", "Quero um humano para a entrega", "text", 0, "humano_solicitado"),
            ("estofados", None, "image", 3, "limite_sem_avanco"),
            ("ambos", "x", "interactive", 3, "limite_sem_avanco"),
        ):
            with self.subTest(produto=produto):
                ctx = contexto_assunto(entrada, tipo=tipo, turnos=turnos, produto=produto)
                envio = flow_sender(ctx)
                self.assertEqual((envio["id_etapa_resultante"], envio["evento_transicao"]), (7, evento))
                self.assertNotIn("assunto", envio)
                self.assertEqual({k for k in envio if k.startswith("encaminhado_")},
                                 {"encaminhado_baratao", "encaminhado_atacadao"})
                self.assertEqual(len(envio["interativo"]["action"]["cards"]), 2)

    def test_mapa_e_confirmacao_da_meta_antes_de_qualquer_efeito(self):
        ctx = contexto_assunto("Montagem")
        ctx["transicoes_permitidas"]["assunto_escolhido"] = 6
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()
        ctx["transicoes_permitidas"]["assunto_escolhido"] = 5
        self.wa.send_message.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(ctx)
```

## 96. `tests/test_etapa5_pedidos.py` (aplicar)

```python
"""Contrato da etapa de pedidos da Baratão, com transporte simulado."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.pedidos_pos_venda import extrair_pedidos
from tests.test_etapa1_pos_venda import contexto, ENV, PATCH_TEXTO, PATCH_CARTOES
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa


def contexto_pedidos(texto, assunto="entrega", **opcoes):
    ctx = contexto(etapa=5, texto=texto, **opcoes)
    ctx.update(produto="moveis", assunto=assunto, codigos_filiais={"01", "05", "09", "15", "29"})
    ctx["transicoes_permitidas"].update(
        pedidos_assistencia=6, nota_perdida_assistencia=6,
        pedidos_demais_assuntos=6, nota_perdida_demais_assuntos=6,
    )
    return ctx


class EtapaPedidosTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.qa")
        for p in (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                  patch(PATCH_CARTOES, return_value=self.wa)):
            p.start()
            self.addCleanup(p.stop)

    def test_identificador_inteiro_e_zeros(self):
        for invalido in ("123", "12.9", "12.099", "12,09", "12.0A", "A12.09", "12.09B",
                         "1.2.09", "12#3.09", "12.09-1", "1:234.09", "12(34.09)",
                         "-12.09", "+12.09", "١٢.٠٩", "12/34.09", "12. 09", "12 .09"):
            with self.subTest(invalido=invalido):
                self.assertEqual(extrair_pedidos(invalido), [])
        self.assertEqual(extrair_pedidos("Pedido:0001.09,35.15 e (7.01). Repetindo 0001.09!"),
                         ["0001.09", "35.15", "7.01"])

    def test_sufixo_desconhecido_repete_com_botao_sem_gravacao_parcial(self):
        singular = "Olha, não consegui identificar uma nota válida. Me fala novamente a nota, por favor."
        plural = "Olha, uma ou mais notas estão inválidas. Digite todas novamente, por favor."
        for mensagem_esperada, exemplos in (
            (singular, ("12.00", "12.04", "12.99", "345.1", "123,01", "AB12.09",
                        "476.213543.23", "245.42.3453.23", "23#4.01", "234.0A", "234.01X",
                        "234.01/345.09", "234.01-345.09", "ABC", "@@@", "não entendi")),
            (plural, ("1.04,2.09", "234.01 e 345.1", "345.1 234.01", "234.01,345.1,456.999",
                      "345.1 e 456.4", "234.01 e A345.09", "1.01 e 2.04 e 3.15", "123 456",
                      "nota:123 e a outra nota:234.01", "a nota é 123 e a outra é 234.01",
                      "234.01 e 345 por favor", "234.01 e 23#4.09", "234.01 e 476.213543.23",
                      "234.01 e 245.42.3453.23", "234.01 e AB345.09:", "234.01 e nota ABC",
                      "234.01 e a outra nota é @@@", "234.01 e a outra nota é abc", "ABC e 234.01",
                      "234.01 e ABC", "234.01,ABC", "ABC, 234.01", "234.01 e AB345 aqui")),
        ):
            for texto in exemplos:
                with self.subTest(texto=texto):
                    ctx = contexto_pedidos(texto)
                    envio = flow_sender(ctx)
                    self.assertTrue(envio["tratamento"])
                    self.assertEqual(envio["mensagem_bot"], mensagem_esperada)
                    self.assertEqual(envio["interativo"]["action"]["buttons"][0]["reply"]["title"], "Perdi a nota")
                    self.assertNotIn("numeros_pedido", envio)
                    cursor = MagicMock()
                    self.assertEqual(atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor), {})
                    cursor.execute.assert_not_called()
                    cursor.executemany.assert_not_called()

    def test_quantidades_na_frase_nao_sao_notas_e_lista_valida_avanca(self):
        for texto, esperado in (
            ("Comprei 2 cadeiras no pedido 234.01", ["234.01"]),
            ("O pedido 234.01 tem 2 cadeiras e 1 mesa.", ["234.01"]),
            ("Comprei 2 ou 3 cadeiras no pedido 234.01.", ["234.01"]),
            ("São 2: 234.01 e 345.09.", ["234.01", "345.09"]),
            ("A NOTA FISCAL do pedido é 234.01.", ["234.01"]),
            ("MINHAS NOTAS SÃO 234.01 E 345.09.", ["234.01", "345.09"]),
            ("Nota 234.01, OBRIGADO!", ["234.01"]),
            ("234.01 é a nota correta", ["234.01"]),
            ("Comprei 2 produtos, seguem as notas 234.01 e 345.09", ["234.01", "345.09"]),
            ("Pedidos: (234.01,345.09), repetindo 234.01.", ["234.01", "345.09"]),
            ("Pedidos: (234.01),(345.09).", ["234.01", "345.09"]),
        ):
            with self.subTest(texto=texto):
                envio = flow_sender(contexto_pedidos(texto))
                self.assertEqual(envio["numeros_pedido"], esperado)
                self.assertEqual(envio["id_etapa_resultante"], 6)

    def test_pedidos_e_nota_perdida_seguem_o_assunto_da_conversa(self):
        for assunto in ("entrega", "assistencia", "montador", "outros", "misto"):
            for texto, tipo, esperado in (
                ("Meus pedidos são 001.09 e 001.15.", "text", ["001.09", "001.15"]),
                ("Perdi a nota", "text", []), ("Perdi a nota", "interactive", []),
                ("pedidos:nota_perdida", "interactive", []),
            ):
                with self.subTest(assunto=assunto, texto=texto):
                    ctx = contexto_pedidos(texto, tipo=tipo, assunto=assunto)
                    envio = flow_sender(ctx)
                    self.assertEqual(envio["numeros_pedido"], esperado)
                    self.assertEqual(envio["id_etapa_resultante"], 6)
        for texto, tipo in (("Acho que perdi a nota", "text"), ("pedidos:nota_perdida", "text"),
                            ("001.09", "interactive"), ("assunto:entrega", "interactive")):
            self.assertTrue(flow_sender(contexto_pedidos(texto, tipo=tipo))["tratamento"])

    def test_painel_exibe_opcoes_do_atendimento_registrado(self):
        from callback.monitoramento.apresentacao import botoes_para_mensagem
        mensagem = {"quem_enviou": "bot", "tipo": "interactive", "id_etapa": 5}
        self.assertEqual(botoes_para_mensagem(mensagem), ["Perdi a nota"])
        self.assertEqual(botoes_para_mensagem({**mensagem, "id_etapa": 6}), [])
        self.assertEqual(botoes_para_mensagem({**mensagem, "id_etapa": 7}), [])
        contato = {"action": {"name": "request_contact_info"}}
        self.assertEqual(botoes_para_mensagem({**mensagem, "interativo": contato}), [])
        cta = {"action": {"parameters": {"display_text": "Pós-venda Móveis"}}}
        self.assertEqual(botoes_para_mensagem({**mensagem, "id_etapa": 7, "interativo": cta}), ["Pós-venda Móveis"])

    def test_universal_tem_prioridade_na_etapa5(self):
        for entrada, tipo, turnos, evento in (
            ("1.99", "text", 3, "limite_sem_avanco"), ("humano, pedido 12.09", "text", 0, "humano_solicitado"),
            (None, "document", 3, "limite_sem_avanco"),
        ):
            envio = flow_sender(contexto_pedidos(entrada, tipo=tipo, turnos=turnos))
            self.assertEqual((envio["evento_transicao"], envio["id_etapa_resultante"]), (evento, 7))
            self.assertNotIn("numeros_pedido", envio)

    def test_mapa_divergente_impede_envio(self):
        ctx = contexto_pedidos("1.09")
        ctx["transicoes_permitidas"]["pedidos_demais_assuntos"] = 7
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()
```

## 97. `workers/worker_flow/response_flow/tratamento_universal_pos_venda.py` (aplicar)

```python
"""Encaminha por solicitação ou no quarto turno que de fato repetiria a etapa."""
from core.etapas_pos_venda import (
    ETAPA_ENCAMINHAMENTO, EVENTO_HUMANO_SOLICITADO, EVENTO_LIMITE_SEM_AVANCO,
)
from core.validacoes.encaminhamento_pos_venda import (
    LIMITE_TURNOS_SEM_AVANCO, entrada_nao_suportada, pediu_humano,
)
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from core.integrations.whatsapp.pywa_functions.pywa_senders.repeticao_midia import enviar_repeticao_midia
from workers.worker_flow.response_flow.transicoes.resolver_transicao import (
    resolver_destino_transicao, anexar_transicao_ao_contexto_envio,
)


def _encaminhar(contexto, evento):
    destino = resolver_destino_transicao(contexto, evento, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento(contexto, evento)
    return anexar_transicao_ao_contexto_envio(contexto, envio, evento, destino)


def repetir_etapa(contexto, sender, *args, **kwargs):
    if int(contexto.get("turnos_sem_avanco") or 0) >= LIMITE_TURNOS_SEM_AVANCO:
        return _encaminhar(contexto, EVENTO_LIMITE_SEM_AVANCO)
    return sender(*args, **kwargs)


def resolver_tratamento_universal(contexto):
    entrada = contexto["mensagem_cliente_atual"]
    tipo = entrada.get("tipo_mensagem")
    if pediu_humano(tipo, entrada.get("conteudo_texto")):
        return _encaminhar(contexto, EVENTO_HUMANO_SOLICITADO)
    etapa = contexto["id_etapa_atual"]
    if entrada_nao_suportada(etapa, tipo):
        return repetir_etapa(contexto, enviar_repeticao_midia, contexto["destinatario_envio"],
                             entrada["id_phone_unidade"], etapa)
    return None
```

## 98. `callback/callback/settings.py`

```python
from pathlib import Path

from core.config_env import env_bool, env_csv, env_int, env_optional, env_required


BASE_DIR = Path(__file__).resolve().parent.parent

CSRF_TRUSTED_ORIGINS = env_csv("DJANGO_CSRF_TRUSTED_ORIGINS")
CSRF_FAILURE_VIEW = 'monitoramento.views.falha_csrf'

SECRET_KEY = env_required("DJANGO_SECRET_KEY")

DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = env_csv("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

WEBHOOK_MAX_BODY_BYTES = env_int("WEBHOOK_MAX_BODY_BYTES", 256 * 1024)

META_APP_SECRET = env_optional("META_APP_SECRET")
META_WEBHOOK_SIGNATURE_REQUIRED = env_bool(
    "META_WEBHOOK_SIGNATURE_REQUIRED",
    False,
)

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("DJANGO_SESSION_COOKIE_SECURE", False)
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", False)
SECURE_HSTS_SECONDS = env_int("DJANGO_SECURE_HSTS_SECONDS", 0)

# Habilite somente quando um proxy confiavel sobrescrever X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env_bool("DJANGO_TRUST_X_FORWARDED_PROTO", False)
    else None
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.postgres',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'webhook',
    'monitoramento.apps.MonitoramentoConfig',
]

# As tabelas do webhook pertencem ao DDL versionado. O Django usa os modelos
# vigentes para criar permissões, sem manter uma segunda sequência de migrations.
MIGRATION_MODULES = {"webhook": None}

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'callback.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": "%(asctime)s | %(levelname)-7s | %(name)-32s | %(filename)s:%(lineno)d | %(message)s",
            "datefmt": "%H:%M:%S",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },

    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

WSGI_APPLICATION = 'callback.wsgi.application'

_database_options = {
    "options": "-c search_path=chatbot",
}

_db_sslmode = env_optional("DB_SSLMODE")
_db_sslrootcert = env_optional("DB_SSLROOTCERT")

if _db_sslmode:
    _database_options["sslmode"] = _db_sslmode

if _db_sslrootcert:
    _database_options["sslrootcert"] = _db_sslrootcert

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_required("DB_NAME"),
        "USER": env_required("DB_USER"),
        "PASSWORD": env_required("DB_PASSWORD"),
        "HOST": env_required("DB_HOST"),
        "PORT": env_int("DB_PORT", 5432),
        "OPTIONS": _database_options,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
```

## 99. `callback/webhook/admin_relacoes.py`

```python
"""Consultas paginadas de tabelas com chave composta, no contexto da central ou conversa."""
import logging
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html_join

from core.integrations.whatsapp.tools.usuarios import desbloquear_usuario_meta
from . import models

logger = logging.getLogger(__name__)


class VincularUsuarioForm(forms.Form):
    usuario = forms.ModelChoiceField(
        queryset=get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by("username"),
        label="Usuário do painel",
        help_text="O painel de atendimento aceita contas comuns com uma única central ativa.",
    )


class ConsultasRelacionadasMixin:
    # Cada consulta tem modelo, campos de exibição e ordem estável de paginação.
    consultas = {}
    campo_vinculo = None

    def get_urls(self):
        return [path("<int:pk>/consultas/<slug:tipo>/", self.admin_site.admin_view(self.consultar),
                     name=self._nome_url())] + super().get_urls()

    def _nome_url(self):
        return f"{self.opts.app_label}_{self.opts.model_name}_consultar"

    def consultas_do_registro(self, obj):
        if obj is None or obj.pk is None:
            return "Disponíveis após o cadastro."
        return format_html_join(" · ", '<a href="{}">{}</a>', (
            (reverse(f"{self.admin_site.name}:{self._nome_url()}", args=(obj.pk, tipo)),
             registro._meta.verbose_name.capitalize())
            for tipo, (registro, _, _) in self.consultas.items()
        ))

    consultas_do_registro.short_description = "Consultas vinculadas"

    def consultar(self, request, pk, tipo):
        obj = get_object_or_404(self.get_queryset(request), pk=pk)
        if tipo not in self.consultas:
            raise Http404
        modelo, campos, ordem = self.consultas[tipo]
        if not self.has_view_permission(request, obj) or not request.user.has_perm(
            f"webhook.view_{modelo._meta.model_name}"
        ):
            raise PermissionDenied
        registros = modelo.objects.filter(**{self.campo_vinculo: obj})
        acessos = modelo is models.MonitoramentoAcesso
        bloqueios = modelo is models.ClienteBloqueadoMeta
        pode_vincular = acessos and request.user.has_perm("webhook.add_monitoramentoacesso")
        pode_remover = acessos and request.user.has_perm("webhook.delete_monitoramentoacesso")
        pode_desbloquear = bloqueios and request.user.has_perm("webhook.delete_clientebloqueadometa")
        form = VincularUsuarioForm() if pode_vincular else None

        if request.method == "POST":
            acao = request.POST.get("acao")
            if acao == "vincular" and pode_vincular:
                form = VincularUsuarioForm(request.POST)
                if form.is_valid():
                    with transaction.atomic():
                        usuario = get_user_model().objects.select_for_update().get(pk=form.cleaned_data["usuario"].pk)
                        outra_ativa = models.MonitoramentoAcesso.objects.filter(usuario=usuario, central__ativa=True).exclude(central=obj)
                        if obj.ativa and outra_ativa.exists():
                            form.add_error("usuario", "Remova o vínculo com a outra central ativa antes de transferir o acesso.")
                        else:
                            _, criado = registros.get_or_create(central=obj, usuario=usuario)
                            messages.success(request, "Vínculo salvo." if criado else "Esse usuário já está vinculado.")
                            return HttpResponseRedirect(request.path)
            elif acao == "remover" and pode_remover:
                chave = request.POST.get("chave", "")
                if not chave.isascii() or not chave.isdecimal():
                    raise Http404
                usuario = get_object_or_404(registros, usuario_id=chave)
                usuario.delete()
                messages.success(request, "Acesso removido.")
                return HttpResponseRedirect(request.path)
            elif acao == "desbloquear" and pode_desbloquear:
                with transaction.atomic():
                    bloqueio = get_object_or_404(registros.select_for_update(), wa_id_cliente=request.POST.get("chave"))
                    try:
                        desbloquear_usuario_meta(bloqueio.wa_id_cliente, obj.phone_number_id)
                    except Exception:
                        logger.exception("admin_desbloqueio_meta_sem_confirmacao | central=%s", obj.pk)
                        messages.error(request, "A Meta não confirmou o desbloqueio. O registro foi mantido.")
                    else:
                        models.Conversa.objects.filter(central=obj, status_ativa=True,
                            chat__cliente__waid_telefone=bloqueio.wa_id_cliente).update(turnos_sem_avanco=0)
                        bloqueio.delete()
                        messages.success(request, "Desbloqueio confirmado pela Meta.")
                return HttpResponseRedirect(request.path)
            else:
                raise PermissionDenied
        elif request.method != "GET":
            return HttpResponseNotAllowed(["GET", "POST"])

        pagina = Paginator(registros.order_by(*ordem).values_list(*campos), 50).get_page(request.GET.get("p"))
        return TemplateResponse(request, "admin/webhook/consultas.html", {
            **self.admin_site.each_context(request), "opts": self.opts, "original": obj,
            "voltar": reverse(f"{self.admin_site.name}:{self.opts.app_label}_{self.opts.model_name}_change", args=(pk,)),
            "title": modelo._meta.verbose_name.capitalize(), "pagina": pagina,
            "colunas": [campo.replace("__", " · ").replace("_", " ").capitalize() for campo in campos],
            "form": form, "pode_remover": pode_remover, "pode_desbloquear": pode_desbloquear,
        })
```

## 100. `callback/webhook/templates/admin/webhook/consultas.html`

```html
{% extends "admin/base_site.html" %}
{% block breadcrumbs %}<div class="breadcrumbs"><a href="{% url 'admin:index' %}">Administração</a> &rsaquo; <a href="{{ voltar }}">{{ original }}</a> &rsaquo; {{ title }}</div>{% endblock %}
{% block content %}
<p>{{ original }}</p>
{% if form %}<form method="post">{% csrf_token %}{{ form.as_p }}<button type="submit" name="acao" value="vincular">Conceder acesso</button></form>{% endif %}
<table>
  <thead><tr>{% for coluna in colunas %}<th scope="col">{{ coluna }}</th>{% endfor %}{% if pode_remover or pode_desbloquear %}<th scope="col">Ação</th>{% endif %}</tr></thead>
  <tbody>
  {% for linha in pagina %}
    <tr>{% for valor in linha %}<td>{{ valor|default_if_none:"—" }}</td>{% endfor %}
    {% if pode_remover or pode_desbloquear %}<td><form method="post">{% csrf_token %}<input type="hidden" name="chave" value="{{ linha.0 }}">
      {% if pode_remover %}<button name="acao" value="remover">Remover acesso</button>{% else %}<button name="acao" value="desbloquear">Desbloquear na Meta</button>{% endif %}
    </form></td>{% endif %}</tr>
  {% empty %}<tr><td colspan="12">Nenhum registro.</td></tr>{% endfor %}
  </tbody>
</table>
<p>{% if pagina.has_previous %}<a href="?p={{ pagina.previous_page_number }}">Anterior</a> · {% endif %}Página {{ pagina.number }} de {{ pagina.paginator.num_pages }}{% if pagina.has_next %} · <a href="?p={{ pagina.next_page_number }}">Próxima</a>{% endif %}</p>
{% endblock %}
```

## 101. `deploy/migrations/20261127_contato_conferencia_cpf.sql`

```sql
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
```

## 102. `deploy/migrations/20261127_encaminhamento_por_rede.sql` (criar)

```sql
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
```
