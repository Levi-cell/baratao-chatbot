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
from core.repositories.unidades.consultas import buscar_id_unidade_por_phone_id
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
        self.wa.send_message.side_effect = resposta
        self.wa.send_carousel.side_effect = resposta
        self.cache = MagicMock()
        self.entrada = 0

    def carregar_catalogo(self, caminho):
        self.adm.execute("DELETE FROM chatbot.etapa_transicao")
        self.adm.execute("DELETE FROM chatbot.etapa")
        texto = (ROOT / caminho).read_text(encoding="utf-8")
        self.adm.execute(texto.split("INSERT INTO chatbot.cache_controle")[0])

    def migrar_catalogo(self):
        self.adm.execute((ROOT / "deploy/migrations/20261122_etapas_produto_encerramento.sql").read_text(encoding="utf-8"))

    def fila(self, texto, tipo="text", central=1):
        self.entrada += 1
        return self.adm.execute("""
            INSERT INTO chatbot.fila_mensagens
                (id_central, cliente_telefone, id_hash_msg, received_data_hora, tipo_mensagem, conteudo_texto)
            VALUES (%s, '5511999990000', %s, clock_timestamp(), %s, %s) RETURNING id_mensagem;
        """, (central, f"wamid.cliente.{self.entrada}", tipo, texto)).fetchone()[0]

    def ciclo(self, **patches):
        conn = psycopg.connect(self.dsn)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, ENV))
            stack.enter_context(patch.object(runtime, "get_conn", side_effect=[conn, PararWorker()]))
            stack.enter_context(patch.object(runtime, "confirmar_cache_cliente_se_pendente"))
            stack.enter_context(patch.object(runtime, "indicar_digitacao"))
            stack.enter_context(patch.object(runtime, "registrar_cache_bloqueio_apos_commit", self.cache))
            stack.enter_context(patch("workers.worker_flow.valida_banco.buscar_cliente_cache", return_value=None))
            stack.enter_context(patch("workers.worker_flow.valida_banco.obter_id_unidade_redis_ou_plsql",
                                      side_effect=buscar_id_unidade_por_phone_id))
            stack.enter_context(patch("workers.worker_flow.tratar_bloqueio.registrar_bloqueio_conversa_cache"))
            stack.enter_context(patch("workers.tratamento_erros_externos.erro_generico.time.sleep"))
            stack.enter_context(patch(PATCH_TEXTO, return_value=self.wa))
            stack.enter_context(patch(PATCH_CARTOES, return_value=self.wa))
            for nome, efeito in patches.items():
                stack.enter_context(patch.object(runtime, nome, side_effect=efeito))
            with redirect_stdout(io.StringIO()), self.assertRaises(PararWorker):
                runtime.worker_flow()

    def conversa(self):
        return self.adm.execute("""
            SELECT id_etapa_atual, turnos_sem_avanco, status_ativa, motivo_encerramento, finalizou_em
            FROM chatbot.conversa ORDER BY id_conversa LIMIT 1;
        """).fetchone()

    def preparar(self):
        self.fila(None, "audio")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (1, 0, True))

    def test_saudacao_tres_repeticoes_e_quarto_encaminhamento(self):
        self.preparar()
        for n in range(1, 4):
            self.fila("123")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (1, n, True))
        self.fila("???")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_sem_avanco"))
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
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_humano"))
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
        self.assertEqual(self.conversa()[:3], (11, 0, True))
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_midia"))
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
        # A identificação é global; uma nova conversa herda os dados já salvos.
        from core.repositories.atendimento.conversas import inserindo_em_conversa_caso_seja_nova
        nova = inserindo_em_conversa_caso_seja_nova(1, 2, self.adm.cursor())
        self.assertEqual(self.adm.execute("SELECT cpf_titular FROM chatbot.atendimento_pos_venda WHERE id_conversa=%s", (nova,)).fetchone()[0], "01234567890")

    def test_etapa2_tres_erros_e_quarto_encaminhamento_sem_cpf(self):
        self.preparar_cpf()
        for n, invalido in enumerate(("1234567890", "123456789012", "1234567890A"), 1):
            self.fila(invalido)
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (2, n, True))
            self.assertIsNone(self.adm.execute("SELECT cpf_titular FROM chatbot.cliente").fetchone()[0])
        self.fila("não sei")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_sem_avanco"))
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
                self.assertEqual(self.conversa()[:4], (11, 0, False, motivo))
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
            SET id_etapa_atual=11, iniciou_em=now()-interval '92 days',
                finalizou_em=now()-interval '91 days', status_ativa=false,
                motivo_encerramento='encaminhamento';
        """)

    def test_retorno_com_cpf_nome_sem_cidade_ja_abre_na_etapa3(self):
        self.preparar_cpf()
        self.fila("01234567890")
        self.ciclo()
        self.encerrar_fixture_ha_91_dias()
        self.fila("Oi, voltei")
        self.ciclo()
        self.assertEqual(self.adm.execute(
            "SELECT id_etapa_atual,status_ativa FROM chatbot.conversa ORDER BY id_conversa DESC LIMIT 1"
        ).fetchone(), (3, True))
        self.assertIn("Sobre qual tipo de produto você quer falar?", self.wa.send_message.call_args.kwargs["text"])
        self.assertEqual(self.adm.execute(
            "SELECT nome_titular,cpf_titular,cidade_loja_compra FROM chatbot.cliente"
        ).fetchone(), ("João da Silva", "01234567890", None))
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.chat").fetchone()[0], 1)
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.conversa").fetchone()[0], 2)

    def test_retorno_nome_sem_cpf_abre_na_etapa2(self):
        self.preparar_cpf()
        self.encerrar_fixture_ha_91_dias()
        self.fila("Oi, voltei")
        self.ciclo()
        self.assertEqual(self.adm.execute(
            "SELECT id_etapa_atual FROM chatbot.conversa ORDER BY id_conversa DESC LIMIT 1"
        ).fetchone()[0], 2)
        self.assertEqual(self.wa.send_message.call_args.kwargs["text"],
                         "Olá, João da Silva! Em uma única mensagem me informe seu CPF.")

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
        self.assertIn("Olá eu sou o Theo", self.wa.send_message.call_args.kwargs["text"])

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
        self.assertEqual(self.conversa()[:3], (6, 0, True))

    def test_pedidos_rejeita_filial_desconhecida_grava_varias_filiais_e_recupera_fila(self):
        self.preparar_pedidos("avarias")
        for turno, texto in enumerate(("10.24 e 10.09", "10.09 e 25.1 e 456.999"), start=1):
            self.fila(texto)
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (6, turno, True))
            self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.pedido_conversa").fetchone(), (0,))
            self.assertEqual(self.adm.execute("SELECT perdeu_nota FROM chatbot.atendimento_pos_venda").fetchone(), (None,))
        item = self.fila("Na nota: 0010.09, 0010.15 e 0010.09.")
        self.ciclo(finalizar_mensagem_processada=RuntimeError("queda após commit de pedidos"))
        self.wa.reset_mock()
        self.adm.execute("UPDATE chatbot.fila_mensagens SET next_attempt_at=now() WHERE id_mensagem=%s", (item,))
        self.ciclo()
        self.wa.send_message.assert_not_called()
        self.assertEqual(self.conversa()[:3], (7, 0, True))
        self.assertEqual(self.adm.execute("""
            SELECT p.numero, f.nome FROM chatbot.pedido_conversa p
            JOIN chatbot.filial_compra f ON f.codigo=p.codigo_filial ORDER BY p.numero
        """).fetchall(), [("0010.09", "ATACADÃO DO SOFÁ - IRECÊ"), ("0010.15", "ATACADÃO DO SOFÁ - COITÉ")])
        self.assertEqual(self.adm.execute("SELECT perdeu_nota FROM chatbot.atendimento_pos_venda").fetchone(), (False,))

    def test_nota_perdida_avanca_para_relato_sem_criar_pedido(self):
        self.preparar_pedidos("entrega")
        self.fila("Perdi a nota", "interactive")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (9, 0, True))
        self.assertEqual(self.adm.execute("SELECT perdeu_nota FROM chatbot.atendimento_pos_venda").fetchone(), (True,))
        self.assertEqual(self.adm.execute("SELECT count(*) FROM chatbot.pedido_conversa").fetchone(), (0,))

    def test_correcao_com_uma_nota_processa_apenas_a_nova_resposta(self):
        self.preparar_pedidos("entrega")
        self.fila("0010.09 e 25.1 e 33.4")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (6, 1, True))
        self.fila("25.01")
        self.ciclo()
        self.assertEqual(self.conversa()[:3], (9, 0, True))
        self.assertEqual(self.adm.execute("SELECT numero FROM chatbot.pedido_conversa").fetchall(), [("25.01",)])

    def test_repetir_filial_inexistente_encaminha_no_quarto_turno(self):
        self.preparar_pedidos("entrega")
        for turno in range(1, 4):
            self.fila("123.04")
            self.ciclo()
            self.assertEqual(self.conversa()[:3], (6, turno, True))
        self.fila("123.04")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_sem_avanco"))
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
        self.assertEqual(self.conversa()[:3], (6, 0, True))
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
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_sem_avanco"))
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
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_sem_avanco"))
        self.assertIsNone(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda").fetchone()[0])
        self.assertEqual(self.cache.call_args.args[1]["bloqueio_dias"], 90)

    def test_produto_midia_usa_universal_e_dois_contatos(self):
        self.preparar_produto()
        self.fila(None, "video")
        self.ciclo()
        self.assertEqual(self.conversa()[:4], (11, 0, False, "encaminhamento_midia"))
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
            UPDATE chatbot.conversa SET id_etapa_atual=11,status_ativa=false,
                iniciou_em=now()-interval '92 days',finalizou_em=now()-interval '91 days',
                motivo_encerramento='encaminhamento';
        """)
        self.fila("Olá")
        self.ciclo()
        self.assertEqual(self.adm.execute("SELECT produto FROM chatbot.atendimento_pos_venda ORDER BY id_conversa").fetchall(),
                         [("moveis",), (None,)])
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
