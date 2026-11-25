-- Aplicar após os complementos de 18/11, com webhook/worker parados.
-- Reutiliza o schema existente. Preserva dados, WAMIDs, filas e datas de bloqueio.
-- Reaplicável; não executar as migrações antigas depois desta.
BEGIN;
SET LOCAL lock_timeout = '8s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(81024, 1);
LOCK TABLE chatbot.etapa, chatbot.etapa_transicao, chatbot.conversa,
           chatbot.historico_mensagens, chatbot.fila_mensagens
    IN ACCESS EXCLUSIVE MODE;

DO $migrar$
DECLARE abertura_antiga boolean;
BEGIN
    IF EXISTS (SELECT FROM chatbot.conversa WHERE processing) THEN
        RAISE EXCEPTION 'Há conversas em processamento. Concluir a recuperação e parar os serviços antes de migrar.';
    END IF;
    SELECT nome_etapa = 'abertura' INTO abertura_antiga
    FROM chatbot.etapa WHERE id_etapa = 11;
    IF abertura_antiga IS NULL OR NOT (
        abertura_antiga OR EXISTS (
            SELECT FROM chatbot.etapa
            WHERE id_etapa = 11 AND nome_etapa = 'encaminhamento'
              AND encerra_automaticamente AND bloqueio_dias = 90
        )
    ) THEN
        RAISE EXCEPTION 'Catálogo não reconhecido; conferir as migrações anteriores.';
    END IF;
    IF EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa NOT IN (1,2,3,4,5,6,7,8,9,10,11)) THEN
        RAISE EXCEPTION 'Há etapas adicionais; revisar o mapa antes de substituir o catálogo.';
    END IF;

    IF abertura_antiga THEN
        IF NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=3 AND nome_etapa='cidade_loja_compra')
           OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=4 AND nome_etapa='produto')
           OR NOT EXISTS (SELECT FROM chatbot.etapa WHERE id_etapa=10 AND nome_etapa='encaminhamento') THEN
            RAISE EXCEPTION 'Catálogo anterior incompleto; migração cancelada.';
        END IF;
        -- Quem aguardava cidade recebe a pergunta de produto no próximo turno.
        -- O marcador é interno e perde efeito quando uma nova resposta é confirmada.
        UPDATE chatbot.historico_mensagens h
        SET interativo = coalesce(h.interativo, '{}'::jsonb)
                         || '{"_migracao_produto_pendente":true}'::jsonb
        WHERE h.id_etapa=3 AND h.quem_enviou='bot' AND h.status_envio='sent'
          AND EXISTS (SELECT FROM chatbot.conversa c
                      WHERE c.id_conversa=h.id_conversa AND c.status_ativa
                        AND c.id_etapa_atual=3);
        UPDATE chatbot.conversa c SET id_etapa_atual =
            CASE c.id_etapa_atual
                WHEN 11 THEN CASE WHEN nullif(btrim(cl.nome_titular),'') IS NULL THEN 1
                                  WHEN cl.cpf_titular IS NULL THEN 2 ELSE 3 END
                WHEN 10 THEN 11 WHEN 4 THEN 3 ELSE c.id_etapa_atual END
        FROM chatbot.chat ch JOIN chatbot.cliente cl ON cl.id_cliente=ch.id_cliente
        WHERE ch.id_chat=c.id_chat AND c.id_etapa_atual IN (4,10,11);
        -- Guardar o ID anterior facilita interpretar as mensagens históricas.
        UPDATE chatbot.historico_mensagens
        SET interativo = coalesce(interativo, '{}'::jsonb)
                         || jsonb_build_object('_etapa_antes_20261122', id_etapa),
            id_etapa = CASE id_etapa
                WHEN 11 THEN coalesce((
                    SELECT c.id_etapa_atual FROM chatbot.conversa c
                    WHERE c.id_conversa=historico_mensagens.id_conversa
                      AND NOT EXISTS (SELECT FROM chatbot.historico_mensagens b
                                      WHERE b.id_conversa=c.id_conversa
                                        AND b.quem_enviou='bot' AND b.status_envio='sent')
                ), 1)
                WHEN 10 THEN 11 WHEN 4 THEN 3 ELSE id_etapa END
        WHERE id_etapa IN (3,4,10,11);
    END IF;
END
$migrar$;

DELETE FROM chatbot.etapa_transicao;
DELETE FROM chatbot.etapa WHERE id_etapa IN (4,10);
UPDATE chatbot.etapa SET nome_etapa='produto', encerra_automaticamente=false, bloqueio_dias=0
WHERE id_etapa=3;
UPDATE chatbot.etapa SET nome_etapa='encaminhamento', encerra_automaticamente=true, bloqueio_dias=90
WHERE id_etapa=11;

-- O bloco INSERT abaixo reproduz o mapa do catálogo canônico.
INSERT INTO chatbot.etapa_transicao (id_etapa_origem, evento, id_etapa_destino) VALUES
    (1, 'nome_valido_falta_cpf', 2),
    (1, 'nome_valido_cpf_presente', 3),
    (2, 'cpf_valido', 3),
    (3, 'produto_escolhido', 5),
    (5, 'assunto_escolhido', 6),
    (6, 'pedidos_assistencia', 7),
    (6, 'nota_perdida_assistencia', 7),
    (6, 'pedidos_demais_assuntos', 9),
    (6, 'nota_perdida_demais_assuntos', 9),
    (7, 'loja_nao_visitada', 8),
    (7, 'loja_visitada', 9),
    (9, 'situacao_informada', 11),
    (1, 'midia_recebida', 11),
    (1, 'humano_solicitado', 11),
    (1, 'limite_sem_avanco', 11),
    (2, 'midia_recebida', 11),
    (2, 'humano_solicitado', 11),
    (2, 'limite_sem_avanco', 11),
    (3, 'midia_recebida', 11),
    (5, 'midia_recebida', 11),
    (6, 'midia_recebida', 11),
    (7, 'midia_recebida', 11),
    (9, 'midia_recebida', 11);

COMMIT;

SELECT id_etapa, nome_etapa, encerra_automaticamente, bloqueio_dias
FROM chatbot.etapa ORDER BY id_etapa;
