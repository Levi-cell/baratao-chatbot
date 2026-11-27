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
