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
