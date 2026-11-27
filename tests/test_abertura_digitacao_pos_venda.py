"""Abertura sem etapa artificial e indicador compartilhado, sem HTTP real."""

import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.integrations.whatsapp.pywa_functions.cliente import antes_do_primeiro_envio
from core.integrations.whatsapp.pywa_functions.digitacao import indicar_digitacao
from workers.worker_flow.response_flow.flow_sender import flow_sender
from tests.test_etapa1_pos_venda import contexto, ENV
from tests.test_etapa2_pos_venda import contexto_cpf


class AberturaDigitacaoTests(unittest.TestCase):
    def setUp(self):
        self.sdk = MagicMock()
        self.ordem = []
        def enviado(**kwargs):
            self.ordem.append("resposta")
            return SimpleNamespace(id="wamid.simulado")
        self.sdk.send_message.side_effect = enviado
        self.sdk.send_carousel.side_effect = enviado
        for p in (patch.dict(os.environ, ENV),
                  patch("core.integrations.whatsapp.pywa_functions.cliente.WhatsAppCentral",
                        return_value=self.sdk)):
            p.start()
            self.addCleanup(p.stop)

    def processar(self, ctx):
        with antes_do_primeiro_envio(lambda: self.ordem.append("digitando")):
            return flow_sender(ctx)

    def test_digitacao_precede_saudacao_repeticao_avanco_e_encaminhamento(self):
        casos = [
            contexto(apresentacao=True, tipo="audio", texto=None),
            contexto(texto="123"),
            contexto(texto="João da Silva"),
            contexto_cpf("123"),
            contexto_cpf("01234567890"),
            contexto(tipo="audio", texto=None),
            contexto_cpf("humano"),
            contexto(turnos=3),
        ]
        for ctx in casos:
            with self.subTest(etapa=ctx["id_etapa_atual"], texto=ctx["mensagem_cliente_atual"]["conteudo_texto"]):
                self.ordem.clear()
                self.processar(ctx)
                self.assertEqual(self.ordem, ["digitando", "resposta"])

    def test_nome_coletado_sempre_pede_cpf_mesmo_com_cadastro_antigo(self):
        ctx = contexto(texto="João da Silva")
        ctx["cadastro"] = {"cpf_titular": "01234567890"}
        envio = self.processar(ctx)
        self.assertEqual(envio["id_etapa_resultante"], 2)
        self.assertIn("CPF do titular", envio["mensagem_bot"])
        self.assertEqual(self.ordem, ["digitando", "resposta"])

    def test_replay_nao_digita_nem_envia(self):
        ctx = contexto()
        ctx["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 1, "id_hash_msg": "wamid.anterior", "interativo": {},
        }
        self.assertTrue(self.processar(ctx)["resposta_ja_existia"])
        self.assertEqual(self.ordem, [])

    def test_mapa_invalido_ou_configuracao_invalida_nao_disparam_digitacao(self):
        ctx = contexto(texto="João da Silva")
        ctx["transicoes_permitidas"] = {}
        with self.assertRaises(ValueError):
            self.processar(ctx)
        with patch.dict(os.environ, {"WHATSAPP_MIDIAS_BASE_URL": ""}):
            with self.assertRaises(ValueError):
                self.processar(contexto(tipo="audio", turnos=3))
        self.assertEqual(self.ordem, [])

    def test_falha_opcional_de_digitacao_nao_impede_a_resposta(self):
        self.sdk.indicate_typing.side_effect = RuntimeError("falha simulada")
        with patch("core.integrations.whatsapp.pywa_functions.digitacao.httpx.Client"):
            with antes_do_primeiro_envio(lambda: indicar_digitacao("999", "wamid.entrada")):
                envio = flow_sender(contexto(apresentacao=True))
        self.assertTrue(envio["enviou"])
        self.sdk.indicate_typing.assert_called_once()
        self.assertEqual(self.ordem, ["resposta"])

    def test_etapa11_nao_pode_voltar_a_saudacao(self):
        with self.assertRaises(NotImplementedError):
            self.processar(contexto(etapa=7, apresentacao=True))
        self.assertEqual(self.ordem, [])

    def test_escolha_de_produto_envia_assunto_com_digitacao(self):
        ctx = contexto(etapa=3, texto="Apenas móveis")
        ctx["transicoes_permitidas"]["produto_escolhido"] = 4
        envio = self.processar(ctx)
        self.assertEqual(envio["id_etapa_resultante"], 4)
        self.assertEqual(envio["produto"], "moveis")
        self.assertEqual(self.ordem, ["digitando", "resposta"])


if __name__ == "__main__":
    unittest.main()
