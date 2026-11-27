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
