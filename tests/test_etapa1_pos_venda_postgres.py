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
                (nome, nome_agente, genero_agente, waba_id, phone_number_id, telefone, telefone_sofas, telefone_moveis)
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

    def test_so_bsuid_nome_compartilhamento_cpf(self):
        for texto in ("Oi","Ana Maria da Silva"):
            self.assertEqual(self.entrada_privada(texto)["status"],"inserted")
            self.ciclo()
        self.wa.request_contact_info.assert_called_once()
        self.assertIn("Ana,",self.wa.request_contact_info.call_args.kwargs["text"])
        for _ in range(3):
            self.entrada_privada("ainda nao")
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
            SELECT produto, encaminhado_sofas, encaminhado_moveis FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, "557592087803", "557582467000"))
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
        item = self.fila(None, "audio")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (1, 0, True))
        self.assertEqual(self.adm.execute("""
            SELECT count(*) FROM chatbot.historico_mensagens WHERE id_mensagem_fila=%s AND quem_enviou='bot'
        """, (item,)).fetchone()[0], 0)
        self.assertEqual(self.adm.execute("SELECT status FROM chatbot.fila_mensagens WHERE id_mensagem=%s", (item,)).fetchone()[0], "pending")

    def test_queda_apos_commit_da_resposta_recupera_fechamento_sem_reenviar(self):
        self.preparar()
        item = self.fila(None, "image")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda antes da finalização"))
        self.assertEqual(self.conversa()[:3], (7, 0, True))
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_midia"))
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

    def test_etapa2_pedido_humano_e_midia_usam_encerramento_universal(self):
        for tipo, texto, motivo in (("text", "Quero atendimento humano", "encaminhamento_humano"),
                                    ("document", None, "encaminhamento_midia")):
            with self.subTest(tipo=tipo):
                self.setUp()
                self.preparar_cpf()
                self.fila(texto, tipo)
                self.ciclo()
                self.assertEqual(self.conversa()[:4], (7, 0, False, motivo))
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

    def test_contato_comprovado_reconcilia_conversa_provisoria_com_o_chat_antigo(self):
        self.preparar_produto()
        self.encerrar_fixture_ha_91_dias()
        for texto in ("Oi", "Ana da Silva"):
            self.entrada_privada(texto)
            self.ciclo()
        def ids():
            return self.adm.execute("SELECT id_cliente FROM chatbot.cliente ORDER BY id_cliente").fetchall()
        canonico, provisorio = ids()
        conversa = self.adm.execute("SELECT id_conversa FROM chatbot.conversa WHERE status_ativa").fetchone()
        telefone = "5511999990000"
        self.assertEqual(self.entrada_privada(cartao=True, telefone=telefone, assinada=False)["status"], "ignored")
        self.assertEqual(ids(), [canonico, provisorio])
        self.assertEqual(self.entrada_privada(cartao=True, telefone=telefone, envelope_wa=telefone)["status"], "inserted")
        self.ciclo()
        self.assertEqual(ids(), [canonico])
        self.assertEqual(self.adm.execute("SELECT id_conversa FROM chatbot.conversa WHERE status_ativa").fetchone(), conversa)
        self.assertEqual(self.adm.execute("SELECT count(DISTINCT id_chat) FROM chatbot.conversa").fetchone(), (1,))
        self.assertEqual(self.adm.execute("SELECT DISTINCT id_cliente FROM chatbot.fila_mensagens WHERE user_id_origem IS NOT NULL").fetchall(), [canonico])
        self.assertEqual(self.adm.execute("SELECT id_cliente FROM chatbot.identidade_bsuid WHERE vigente").fetchone(), canonico)
        self.assertEqual(self.adm.execute("SELECT nome_titular,cpf_titular FROM chatbot.atendimento_pos_venda ORDER BY id_conversa").fetchall(),
                         [("João da Silva", "01234567890"), ("Ana da Silva", None)])
        self.assertIn("CPF do titular", self.wa.send_message.call_args.kwargs["text"])
        self.entrada_privada("12345678901")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT cpf_titular FROM chatbot.cliente").fetchone(), ("12345678901",))

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
        self.assertEqual(self.entrada_privada(cartao=True, telefone="5511999990000")["reason"],
                         "contato_exige_conciliacao")
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
        for texto in ("Duas ou mais opções acima", "0010.09 e 0010.15"):
            self.fila(texto)
            self.ciclo()
        relato = "O sofá rasgou.\nA mesa veio riscada."
        entrada = self.fila(relato)
        with patch("core.integrations.whatsapp.messages.encaminhamento_pos_venda.obter_saudacao_por_horario",
                   return_value="Boa tarde"):
            self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento"))
        self.assertEqual(self.adm.execute(
            "SELECT detalhes,encaminhado_sofas,encaminhado_moveis FROM chatbot.atendimento_pos_venda"
        ).fetchone(), (relato, "557592087803", "557582467000"))
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
                "  • 0010.15 (ATACADÃO DO SOFÁ - COITÉ)\n\n"
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
            SELECT detalhes, encaminhado_sofas, encaminhado_moveis FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, None, None))
        self.assertEqual(self.adm.execute("""
            SELECT count(*) FROM chatbot.historico_mensagens WHERE id_mensagem_fila=%s AND quem_enviou='bot'
        """, (item,)).fetchone(), (0,))

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
        resumo = parse_qs(urlsplit(interativo["action"]["parameters"]["url"]).query)["text"][0]
        self.assertEqual(len(resumo.split("\n\n")), 2)
        self.assertTrue(resumo.endswith("- Assunto: Entrega\n- Número da nota: Perdi a nota"))
        self.assertNotIn("5511999990000", resumo)

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

    def test_quarto_turno_na_lista_encaminha_apenas_estofados_e_bloqueia(self):
        self.preparar_assunto("Apenas Estofados")
        for turno in range(1, 4):
            self.fila("?", "text")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (4, turno, True))
        self.fila("Outros", "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.assertEqual(self.adm.execute("""
            SELECT assunto, encaminhado_moveis, encaminhado_sofas FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, None, "557592087803"))
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)

    def test_produto_quarta_entrada_encaminha_sem_salvar_escolha(self):
        self.preparar_produto()
        for n in range(1, 4):
            self.fila("???")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (3, n, True))
        self.fila("Estofados e Móveis", "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_sem_avanco"))
        self.assertIsNone(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0])
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)

    def test_produto_midia_usa_universal_e_dois_contatos(self):
        self.preparar_produto()
        self.fila(None, "video")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (7, 0, False, "encaminhamento_midia"))
        self.assertEqual(self.adm.execute("""
            SELECT produto,encaminhado_sofas,encaminhado_moveis FROM chatbot.atendimento_pos_venda
        """).fetchone(), (None, "557592087803", "557582467000"))

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
