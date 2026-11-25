"""Consumo em PostgreSQL LOCAL descartável; Meta e envio são substituídos.

BARATAO_CONSUMO_TEST_DSN deve apontar a localhost, banco baratao_*.
Recria o schema chatbot exclusivamente nesse banco de teste.
"""

import json
import os
import sys
import unittest
from contextlib import ExitStack
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import psycopg
from psycopg.conninfo import conninfo_to_dict

from core.repositories.consumo_meta import coletas
from core.repositories.monitoramento.acessos import buscar_acesso_monitoramento
from workers.worker_consumo_meta import consumo_worker as worker
from workers.worker_consumo_meta.processamento import salvar_coleta, registrar_falha
from tests.consumo_fixtures import AGORA, CONTA, resultado

ROOT = Path(__file__).resolve().parents[1]
MIGRACAO = ROOT / "deploy/migrations/20261122_consumo_meta_varejo.sql"


@unittest.skipUnless(os.getenv("BARATAO_CONSUMO_TEST_DSN"), "Requer PostgreSQL local isolado.")
class ConsumoPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = os.environ["BARATAO_CONSUMO_TEST_DSN"]
        info = conninfo_to_dict(cls.dsn)
        if info.get("host") not in {"localhost", "127.0.0.1", "::1"} or not info.get("dbname", "").startswith("baratao_"):
            raise RuntimeError("Teste recusa banco remoto ou sem prefixo baratao_.")
        cls.adm = psycopg.connect(cls.dsn, autocommit=True)
        cls.adm.execute("DROP SCHEMA IF EXISTS chatbot CASCADE; CREATE SCHEMA chatbot")
        cls.adm.execute("CREATE TABLE chatbot.auth_user (id integer PRIMARY KEY, is_active bool DEFAULT true, is_staff bool DEFAULT false, is_superuser bool DEFAULT false)")
        cls.adm.execute((ROOT / "core/database/deploy_database/schema.sql").read_text(encoding="utf-8"))
        cls.adm.execute((ROOT / "core/database/deploy_database/catalogo.sql").read_text(encoding="utf-8"))
        # Configuração mínima do Django, sem ler o .env ou abrir o banco remoto.
        from django.conf import settings
        sys.path.insert(0, str(ROOT / "callback"))
        if not settings.configured:
            settings.configure(SECRET_KEY="consumo-teste-local", USE_TZ=True,
                               INSTALLED_APPS=["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "webhook", "monitoramento"],
                               DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
                               ALLOWED_HOSTS=["testserver"], ROOT_URLCONF="tests.urls_consumo",
                               STATIC_URL="/static/", TEMPLATES=[{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True}])
        import django
        django.setup()

    @classmethod
    def tearDownClass(cls):
        cls.adm.close()

    def setUp(self):
        self.adm.execute("TRUNCATE chatbot.central_pos_venda RESTART IDENTITY CASCADE")
        self.adm.execute("DELETE FROM chatbot.auth_user")
        self.adm.execute("DELETE FROM chatbot.cliente")
        self.adm.execute("""
            INSERT INTO chatbot.central_pos_venda (nome,nome_agente,genero_agente,waba_id,phone_number_id,telefone,telefone_moveis,telefone_sofas,id_fuso,nome_fuso)
            VALUES ('Central QA','Theo','masculino','100','101','551100000001','557592087803','557582467000',25,'America/Sao_Paulo'),
                   ('Outra central QA','Theo','masculino','100','102','551100000002','557592087803','557582467000',25,'America/Sao_Paulo');
            INSERT INTO chatbot.auth_user (id) VALUES (1),(2);
            INSERT INTO chatbot.monitoramento_acesso VALUES (1,1),(2,2);
        """)

    def ler(self, central=1, mes=date(2026, 11, 1)):
        with self.adm.cursor() as c:
            return coletas.buscar_para_atualizar(c, central, mes)

    def gravar(self, *, central=1, agora=AGORA, **opcoes):
        return salvar_coleta(self.adm, central, resultado(agora=agora, **opcoes), agora, agora + timedelta(hours=1))

    def legado(self, central=1):
        self.adm.execute("""
            INSERT INTO chatbot.consumo_mensal_meta (id_central,mes_referencia,waba_id,phone_number_id,fuso_horario,
                qtd_gratuitas,qtd_cobradas_meta,consultado_ate,consolidado_em,valor_meta,moeda)
            VALUES (%s,'2026-11-01','100',%s,'America/Sao_Paulo',1200,1300,%s,%s,45.50,'BRL')
        """, (central, str(100 + central), AGORA, AGORA))

    def test_fresh_ddl_persiste_divisao_cobertura_e_agenda(self):
        self.assertTrue(self.gravar())
        r = self.ler()
        self.assertEqual((r["qtd_gratuitas"], r["qtd_janela_gratuita"], r["qtd_franquia_consumida"], r["beneficio_esl_mensal"]), (1200, 200, 1000, 1000))
        self.assertEqual(r["status_apuracao"], "em_andamento")
        with self.adm.cursor() as c:
            self.assertEqual(coletas.listar_agenda(c, 1)["2026-11"]["proxima_consulta_em"], AGORA + timedelta(hours=1))

    def test_recoleta_legado_preserva_dinheiro_e_nao_consolida_imediatamente(self):
        self.legado()
        self.gravar()
        r = self.ler()
        self.assertEqual(str(r["valor_meta"]), "45.500000")
        self.assertEqual(r["moeda"], "BRL")
        self.assertIsNone(r["consolidado_em"])
        self.assertEqual(r["status_apuracao"], "em_andamento")

    def test_falha_preserva_totais_e_aumenta_espera_sem_inserir_zeros(self):
        self.gravar()
        anterior = self.ler()
        registrar_falha(self.adm, 1, "2026-11", AGORA, AGORA + timedelta(hours=1), "Falha de teste")
        self.assertEqual(self.ler()["qtd_cobradas_meta"], anterior["qtd_cobradas_meta"])
        registrar_falha(self.adm, 2, "2026-11", AGORA, AGORA + timedelta(hours=1), "Falha de teste")
        self.assertIsNone(self.ler(2))
        with self.adm.cursor() as c:
            self.assertEqual(coletas.listar_agenda(c, 2)["2026-11"]["falhas_consecutivas"], 1)

    def test_falha_legado_preserva_inclusive_consolidacao_original(self):
        self.legado()
        antes = self.ler()
        registrar_falha(self.adm, 1, "2026-11", AGORA, AGORA + timedelta(days=1), "Falha")
        self.assertEqual(antes, self.ler())

    def test_resposta_atrasada_nao_sobrepoe_leitura_nova(self):
        self.gravar()
        self.assertFalse(self.gravar(agora=AGORA-timedelta(minutes=1), cobradas=0))
        self.assertEqual(self.ler()["qtd_cobradas_meta"], 1300)

    def test_edicao_conta_ou_desativacao_durante_http_impede_gravacao(self):
        for alteracao in ("phone_number_id='999'", "ativa=false", "waba_id='200'", "id_fuso=206,nome_fuso='America/Bahia'"):
            with self.subTest(alteracao=alteracao):
                self.adm.execute("UPDATE chatbot.central_pos_venda SET phone_number_id='101',ativa=true,waba_id='100',id_fuso=25,nome_fuso='America/Sao_Paulo' WHERE id_central=1")
                self.adm.execute("UPDATE chatbot.central_pos_venda SET " + alteracao + " WHERE id_central=1")
                with self.assertRaises(ValueError):
                    self.gravar()
                self.assertIsNone(self.ler())

    def test_consolidacao_e_falha_no_dia25(self):
        dia24 = datetime(2026, 12, 24, 15, tzinfo=timezone.utc)
        self.gravar(agora=dia24)
        self.gravar(central=2, phone="102", agora=dia24)
        dia25 = dia24 + timedelta(days=1)
        self.gravar(agora=dia25)
        self.assertEqual(self.ler()["status_apuracao"], "consolidado")
        registrar_falha(self.adm, 2, "2026-11", dia25, dia25 + timedelta(days=1), "Indisponível")
        self.assertEqual(self.ler(2)["data_proxima_consolidacao"], date(2027, 1, 25))
        self.gravar(central=2, phone="102", agora=dia25 + timedelta(days=1))
        self.assertEqual(self.ler(2)["status_apuracao"], "em_conferencia")

    def test_lock_exclusivo_nao_envia_nem_consulta(self):
        self.adm.execute("SELECT pg_advisory_lock(%s)", (worker.LOCK_CONSUMO_META,))
        try:
            with patch.object(worker, "consultar_conta_consumo") as meta:
                r = worker.executar_ciclo_consumo(conectar=lambda: psycopg.connect(self.dsn), session=Mock(), relogio=lambda: AGORA)
            self.assertTrue(r["ocupado"])
            meta.assert_not_called()
        finally:
            self.adm.execute("SELECT pg_advisory_unlock(%s)", (worker.LOCK_CONSUMO_META,))

    def test_ciclo_central_ativa_com_http_fora_de_transacao(self):
        self.adm.execute("UPDATE chatbot.central_pos_venda SET ativa=false WHERE id_central=2")
        conn = psycopg.connect(self.dsn)
        def conta(*args, **kwargs):
            self.assertEqual(conn.info.transaction_status, psycopg.pq.TransactionStatus.IDLE)
            return CONTA
        def metricas(*args, **kwargs):
            self.assertEqual(conn.info.transaction_status, psycopg.pq.TransactionStatus.IDLE)
            return resultado(kwargs["mes"])
        with patch.object(worker, "consultar_conta_consumo", side_effect=conta), patch.object(worker, "consultar_metricas_conta", side_effect=metricas):
            r = worker.executar_ciclo_consumo(conectar=lambda: conn, session=Mock(), relogio=lambda: AGORA)
        self.assertEqual(r, {"coletados": 2, "falhas": 0, "ocupado": False})
        self.assertIsNone(self.ler(2))
        with patch.object(worker, "consultar_conta_consumo") as meta:
            r = worker.executar_ciclo_consumo(conectar=lambda: psycopg.connect(self.dsn), session=Mock(), relogio=lambda: AGORA)
        meta.assert_not_called()
        self.assertEqual(r["coletados"], 0)

    def test_erro_de_uma_central_nao_impede_a_outra(self):
        def metrica(*args, **kw):
            if kw["phone_number_id"] == "101":
                raise RuntimeError("Métrica incompleta")
            return resultado(kw["mes"], phone="102")
        with patch.object(worker, "consultar_conta_consumo", return_value=CONTA), patch.object(worker, "consultar_metricas_conta", side_effect=metrica):
            r = worker.executar_ciclo_consumo(conectar=lambda: psycopg.connect(self.dsn), session=Mock(), relogio=lambda: AGORA)
        self.assertEqual((r["coletados"], r["falhas"]), (2, 2))
        self.assertIsNone(self.ler())
        self.assertEqual(self.ler(2)["qtd_cobradas_meta"], 1300)

    def test_acesso_exige_vinculo_unico_ativo_sem_bypass_admin(self):
        with self.adm.cursor() as c:
            self.assertEqual(buscar_acesso_monitoramento(1, c).id_central, 1)
            self.assertIsNone(buscar_acesso_monitoramento(99, c))
            self.adm.execute("UPDATE chatbot.auth_user SET is_staff=true WHERE id=1")
            self.assertIsNone(buscar_acesso_monitoramento(1, c))
            self.adm.execute("UPDATE chatbot.auth_user SET is_staff=false WHERE id=1")
            self.adm.execute("INSERT INTO chatbot.monitoramento_acesso VALUES(1,2)")
            self.assertIsNone(buscar_acesso_monitoramento(1, c))

    def test_servico_filtro_mensal_e_escopo_sem_consulta_meta(self):
        from callback.monitoramento import consumo_services as services
        self.gravar()
        self.gravar(central=2, phone="102", cobradas=9000)
        with self.adm.cursor() as c:
            acesso = buscar_acesso_monitoramento(1, c)
        with patch.object(services, "connection", self.adm):
            dados = services.carregar_consumo(acesso, "2026-11", agora=AGORA)
            self.assertEqual(dados["central"]["nome"], "Central QA")
            self.assertEqual(dados["selecionado"]["qtd_cobradas_meta"], 1300)
            self.assertEqual(len(dados["historico"]), 1)
            for mes in ("2026-13", "2026-09", "2026-12", "2026-10", "1;SELECT"):
                with self.subTest(mes=mes), self.assertRaises(ValueError):
                    services.carregar_consumo(acesso, mes, agora=AGORA)

    def test_endpoints_autorizados_json_pdf_e_negacoes(self):
        from django.test import RequestFactory
        from monitoramento import consumo_views, consumo_services, monitoramento_guard
        self.gravar()
        fabrica = RequestFactory()
        usuario = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=False, is_superuser=False, pk=1)
        with ExitStack() as stack:
            stack.enter_context(patch.object(consumo_services, "connection", self.adm))
            stack.enter_context(patch.object(monitoramento_guard, "connection", self.adm))
            relogio = stack.enter_context(patch.object(consumo_services, "datetime", wraps=datetime))
            relogio.now.return_value = AGORA
            for view, url in ((consumo_views.dados_consumo, "/dados/consumo/?mes=2026-11&id_central=2"),
                              (consumo_views.consumo_pdf, "/consumo.pdf?mes=2026-11")):
                request = fabrica.get(url); request.user = usuario
                resposta = view(request)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn("no-store", resposta["Cache-Control"])
                if view == consumo_views.dados_consumo:
                    self.assertEqual(json.loads(resposta.content)["central"]["nome"], "Central QA")
                else:
                    self.assertTrue(resposta.content.startswith(b"%PDF"))
                request.user = SimpleNamespace(is_authenticated=False)
                self.assertEqual(view(request).status_code, 401)
                request.user = SimpleNamespace(**(vars(usuario) | {"pk": 99}))
                self.assertEqual(view(request).status_code, 403)
            request = fabrica.get("/dados/consumo/?mes=invalido"); request.user=usuario
            self.assertEqual(consumo_views.dados_consumo(request).status_code, 400)

    def test_migracao_agregada_idempotente_preserva_dados_e_reagenda_so_ativa(self):
        antes_colunas = self.colunas_consumo()
        self.adm.execute("DROP TABLE chatbot.consumo_mensal_meta")
        self.adm.execute((ROOT / "tests/fixtures/consumo_meta_agregado.sql").read_text(encoding="utf-8"))
        try:
            self.legado(1); self.legado(2)
            self.adm.execute("UPDATE chatbot.central_pos_venda SET ativa=false WHERE id_central=2")
            for _ in range(2):
                self.adm.execute(MIGRACAO.read_text(encoding="utf-8"))
            self.assertEqual(antes_colunas, self.colunas_consumo())
            for central in (1, 2):
                r = self.ler(central)
                self.assertEqual((r["qtd_gratuitas"], r["qtd_cobradas_meta"], r["consolidado_em"]), (1200, 1300, AGORA))
                self.assertEqual(r["status_apuracao"], "pendente_detalhamento")
                self.assertIsNone(r["qtd_janela_gratuita"])
            with self.adm.cursor() as c:
                self.assertIn("2026-11", coletas.listar_agenda(c, 1))
                self.assertEqual(coletas.listar_agenda(c, 2), {})
            self.gravar()
            self.adm.execute(MIGRACAO.read_text(encoding="utf-8"))
            self.assertEqual(self.ler()["status_apuracao"], "em_andamento")
            self.assertEqual(self.ler()["qtd_janela_gratuita"], 200)
        finally:
            self.adm.execute("ROLLBACK")
            self.adm.execute(MIGRACAO.read_text(encoding="utf-8"))

    def test_constraints_rejeitam_divisao_incoerente_e_estado_incompleto(self):
        self.gravar()
        for sql in ("qtd_gratuitas=0", "qtd_franquia_consumida=1001", "qtd_janela_gratuita=NULL",
                    "status_apuracao='consolidado'", "beneficio_esl_mensal=-1"):
            with self.subTest(sql=sql), self.assertRaises(psycopg.errors.CheckViolation):
                self.adm.execute("UPDATE chatbot.consumo_mensal_meta SET " + sql + " WHERE id_central=1")

    def colunas_consumo(self):
        return self.adm.execute("""
            SELECT column_name, data_type, is_nullable, column_default, numeric_precision, numeric_scale
            FROM information_schema.columns WHERE table_schema='chatbot' AND table_name='consumo_mensal_meta'
            ORDER BY column_name
        """).fetchall()

    def test_recursos_de_outra_central_nao_autorizam_acesso(self):
        self.adm.execute("""
            INSERT INTO chatbot.cliente (waid_telefone) VALUES ('5511888880000') ON CONFLICT DO NOTHING;
            INSERT INTO chatbot.chat (id_cliente,id_central)
                SELECT id_cliente, c FROM chatbot.cliente CROSS JOIN generate_series(1,2) c;
            INSERT INTO chatbot.conversa (id_chat,id_central,id_etapa_atual)
                SELECT id_chat,id_central,1 FROM chatbot.chat;
        """)
        conversa = self.adm.execute("SELECT id_conversa FROM chatbot.conversa WHERE id_central=2 LIMIT 1").fetchone()[0]
        with self.adm.cursor() as c:
            self.assertIsNone(buscar_acesso_monitoramento(1, c, id_conversa=conversa))
            self.assertEqual(buscar_acesso_monitoramento(2, c, id_conversa=conversa).id_central, 2)

    def test_indisponibilidade_banco_no_guard_retorna503_sem_dados(self):
        from django.db import DatabaseError
        from django.test import RequestFactory
        from monitoramento import consumo_views, monitoramento_guard
        request = RequestFactory().get("/dados/consumo/")
        request.user = SimpleNamespace(is_authenticated=True, is_active=True, is_staff=False, is_superuser=False, pk=1)
        falha = Mock(); falha.cursor.side_effect = DatabaseError("falha simulada")
        with patch.object(monitoramento_guard, "connection", falha):
            for view in (consumo_views.dados_consumo, consumo_views.consumo_pdf):
                resposta = view(request)
                self.assertEqual(resposta.status_code, 503)
                self.assertIn("no-store", resposta["Cache-Control"])
                self.assertNotIn(b"falha simulada", resposta.content)


if __name__ == "__main__":
    unittest.main()
