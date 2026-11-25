-- Base de partida: etapa 4 de assunto. Aplicar como um script no DBeaver.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';

DO $precondicoes$
BEGIN
    IF NOT EXISTS (SELECT FROM chatbot.etapa_transicao WHERE id_etapa_origem=4 AND evento='assunto_escolhido' AND id_etapa_destino=6)
       OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=11 AND encerra_automaticamente AND bloqueio_dias=90)
       OR (SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem=6 AND
           (evento, id_etapa_destino) IN (('pedidos_assistencia',7),('nota_perdida_assistencia',7),
           ('pedidos_demais_assuntos',9),('nota_perdida_demais_assuntos',9),('midia_recebida',11))) <> 5 THEN
        RAISE EXCEPTION 'Confira o catálogo anterior de pedidos e encaminhamento.';
    END IF;
END
$precondicoes$;

CREATE TABLE IF NOT EXISTS chatbot.filial_compra (
    codigo text PRIMARY KEY CHECK (codigo ~ '^[0-9]{2}$'),
    nome text NOT NULL CHECK (btrim(nome) <> '')
);
INSERT INTO chatbot.filial_compra (codigo, nome) VALUES
    ('01', 'SFB TANCREDO NEVES - APENAS CONSULTA'),
    ('02', 'SFB CRUZ - APENAS CONSULTA'),
    ('03', 'SFB SAJ - APENAS CONSULTA!'),
    ('05', 'DEPÓSITO - SFB'),
    ('06', 'BARATÃO DOS MÓVEIS - VERA CRUZ - APENAS CONSULTA'),
    ('07', 'SFB VALENÇA - APENAS CONSULTA'),
    ('08', 'BARATÃO DOS MÓVEIS - DIAS DAVILA'),
    ('09', 'ATACADÃO DO SOFÁ - IRECÊ'),
    ('10', 'ATACADÃO DO SOFÁ - ST ESTEVÃO'),
    ('11', 'ATACADÃO DO SOFÁ - JEQUIÉ'),
    ('12', 'ATACADÃO DO SOFÁ - SR DO BONFIM'),
    ('13', 'ATACADÃO DO SOFÁ - JUAZEIRO'),
    ('14', 'ATACADÃO DO SOFÁ - SERRINHA'),
    ('15', 'ATACADÃO DO SOFÁ - COITÉ'),
    ('16', 'ATACADÃO DO SOFÁ - ILHÉUS'),
    ('17', 'ATACADÃO DO SOFÁ - POMBAL'),
    ('18', 'ATACADÃO DO SOFÁ - JACOBINA'),
    ('19', 'ATACADÃO DO SOFÁ - ATC VERA CRUZ'),
    ('21', 'ATACADÃO DO SOFÁ - CAPIM GROSSO'),
    ('22', 'ATACADÃO DO SOFÁ - EUCLIDES'),
    ('23', 'ATACADÃO DO SOFÁ - FEIRA DE SANTANA'),
    ('25', 'ATACADÃO DO SOFÁ - PAULO AFONSO'),
    ('26', 'BARATÃO DOS MÓVEIS - SAJ (FEIRÃO)'),
    ('27', 'BARATÃO DOS MÓVEIS - PTN (FEIRÃO)'),
    ('28', 'BARATÃO DOS MÓVEIS - CRUZ DAS ALMAS (FEIRÃO)'),
    ('29', 'BARATÃO DOS MÓVEIS - VALENÇA (FEIRÃO)')
ON CONFLICT (codigo) DO NOTHING;

ALTER TABLE chatbot.pedido_conversa ADD COLUMN IF NOT EXISTS
    codigo_filial text GENERATED ALWAYS AS (right(numero, 2)) STORED;

DO $vinculo$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_constraint WHERE conrelid='chatbot.pedido_conversa'::regclass AND conname='pedido_filial_fk') THEN
        ALTER TABLE chatbot.pedido_conversa ADD CONSTRAINT pedido_filial_fk
            FOREIGN KEY (codigo_filial) REFERENCES chatbot.filial_compra(codigo) NOT VALID;
    END IF;
    -- Pedidos históricos sem correspondência permanecem disponíveis para conferência.
    -- A chave estrangeira já exige uma filial cadastrada para todo novo pedido.
    IF NOT EXISTS (SELECT FROM chatbot.pedido_conversa p LEFT JOIN chatbot.filial_compra f
                   ON f.codigo=p.codigo_filial WHERE f.codigo IS NULL) THEN
        ALTER TABLE chatbot.pedido_conversa VALIDATE CONSTRAINT pedido_filial_fk;
    END IF;
END
$vinculo$;

INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino)
VALUES (6, 'humano_solicitado', 11), (6, 'limite_sem_avanco', 11)
ON CONFLICT (id_etapa_origem, evento) DO NOTHING;
DO $destinos$
BEGIN
    IF (SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem=6
        AND evento IN ('humano_solicitado','limite_sem_avanco') AND id_etapa_destino=11) <> 2 THEN
        RAISE EXCEPTION 'Destino incorreto para o tratamento universal da etapa 6.';
    END IF;
END
$destinos$;
COMMIT;

SELECT (SELECT count(*) FROM chatbot.filial_compra) AS filiais,
       (SELECT count(*) FROM chatbot.etapa_transicao WHERE id_etapa_origem=6) AS transicoes_etapa_6,
       (SELECT count(*) FROM chatbot.pedido_conversa p LEFT JOIN chatbot.filial_compra f
        ON f.codigo=p.codigo_filial WHERE f.codigo IS NULL) AS pedidos_antigos_sem_filial;
