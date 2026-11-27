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
        "transicoes_permitidas": dict(mapas.get(etapa, {}), midia_recebida=7,
                                     humano_solicitado=7, limite_sem_avanco=7),
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
            for evento in ("midia_recebida", "humano_solicitado", "limite_sem_avanco"):
                with self.subTest(etapa=etapa, evento=evento):
                    self.cursor.reset_mock()
                    self.assertEqual(self.persistir(
                        etapa, evento_transicao=evento, id_etapa_resultante=7,
                        encaminhado_moveis="557582467000", encaminhado_sofas="557592087803",
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
            self.persistir(1, evento_transicao="midia_recebida", id_etapa_resultante=7,
                           encaminhado_moveis="557582467000")
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
