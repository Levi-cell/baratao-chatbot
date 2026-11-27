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
                          telefone_moveis="551199990002", telefone_sofas="551199990003")
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
