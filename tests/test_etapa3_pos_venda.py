"""Produto: texto, botões, tratamentos, contrato dos efeitos e transporte simulado."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.produto_pos_venda import extrair_produto
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa
from tests.test_etapa1_pos_venda import contexto, ENV, PATCH_TEXTO, PATCH_CARTOES


def contexto_produto(texto="Móveis", **kwargs):
    ctx = contexto(etapa=3, texto=texto, **kwargs)
    ctx["transicoes_permitidas"] = {
        "produto_escolhido": 4,
        "humano_solicitado": 7, "limite_sem_avanco": 7,
    }
    return ctx


class ProdutoExtratorTests(unittest.TestCase):
    def test_palavras_em_frases_sem_acento_e_com_limites(self):
        casos = {
            "Quero falar sobre meus MÓVEIS.": "moveis",
            "apenas moveis": "moveis", "Meu móvel": "moveis",
            "Sobre os estofados da compra": "estofados", "Meu sofá": "estofados",
            "Estofados e Móveis": "ambos", "móveis e estofados": "ambos",
            "quero falar dos dois": "ambos", "ambos": "ambos",
            "das duas opções": "ambos", "dos dois setores": "ambos",
            "nao recebi meus moveis": "moveis",
            "não entregaram o estofado": "estofados",
            "meus móveis não chegaram": "moveis",
            "não só móveis, mas também estofados": "ambos",
            "Os móveis e os estofados não chegaram": "ambos",
        }
        for texto, produto in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(extrair_produto(texto), produto)

    def test_negacao_de_setor_e_de_ambos(self):
        casos = {
            "não quero falar de móveis": "estofados",
            "não quero falar de estofados": "moveis",
            "não é sobre móveis": "estofados",
            "Não móveis, estofados": "estofados",
            "Estofados sim, móveis não": "estofados",
            "móveis não, estofados sim": "estofados",
            "não quero móveis, quero estofados": "estofados",
            "quero móveis e não estofados": "moveis",
            "não quero falar dos dois": None,
            "não quero ambos": None,
            "não quero móveis nem estofados": None,
            "não quero falar de móveis e estofados": None,
            "nem móveis nem estofados": None,
            "nenhum dos dois": None,
            "não quero móveis, mas quero móveis": None,
        }
        for texto, produto in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(extrair_produto(texto), produto)

    def test_ausencia_ou_ambiguidade_requer_correcao(self):
        for texto in (None, "", " ", "sim", "123", "entrega", "automoveis", "imóveis",
                      "sofamento", "não sei se são móveis", "talvez estofados"):
            with self.subTest(texto=texto):
                self.assertIsNone(extrair_produto(texto))


class Etapa3Tests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.texto")
        self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.cartoes")
        for p in (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                  patch(PATCH_CARTOES, return_value=self.wa)):
            p.start()
            self.addCleanup(p.stop)

    def test_apresentacao_e_correcao_com_tres_botoes_e_rodape(self):
        for apresentacao in (True, False):
            envio = flow_sender(contexto_produto("???", apresentacao=apresentacao))
            self.assertEqual(envio["id_etapa_resultante"], 3)
            texto = ("Sobre qual tipo de produto você quer falar?" if apresentacao
                     else "Não entendi, sobre qual tipo de produto você quer falar?")
            self.assertEqual(envio["mensagem_bot"], texto)
            self.assertEqual(bool(envio.get("tratamento")), not apresentacao)
            botoes = envio["interativo"]["action"]["buttons"]
            self.assertEqual([b["reply"]["title"] for b in botoes],
                             ["Apenas Estofados", "Apenas Móveis", "Estofados e Móveis"])
            self.assertEqual(envio["interativo"]["footer"]["text"], "Selecione apenas uma opção abaixo.")
            self.assertEqual(self.wa.send_message.call_args.kwargs["footer"],
                             "Selecione apenas uma opção abaixo.")

    def test_tres_opcoes_interativas_avancam_com_lista_de_assuntos(self):
        for tipo in ("interactive", "interactive_button", "button"):
            for texto, esperado in (("Apenas Estofados", "estofados"),
                                    ("Apenas Móveis", "moveis"),
                                    ("Estofados e Móveis", "ambos"),
                                    ("produto:ambos", "ambos")):
                with self.subTest(tipo=tipo, texto=texto):
                    envio = flow_sender(contexto_produto(texto, tipo=tipo))
                    self.assertEqual(envio["id_etapa_resultante"], 4)
                    self.assertEqual(envio["produto"], esperado)
                    self.assertEqual(envio["evento_transicao"], "produto_escolhido")
                    self.assertEqual(envio["interativo"]["type"], "list")
                    self.assertEqual(len(envio["interativo"]["action"]["sections"][0]["rows"]), 5)
        self.wa.send_carousel.assert_not_called()

    def test_botao_desconhecido_repete_sem_tratar_como_midia(self):
        for texto in ("assunto:entrega", "quero falar de móveis", "sim", None):
            envio = flow_sender(contexto_produto(texto, tipo="interactive"))
            self.assertTrue(envio["tratamento"])
            self.assertEqual(envio["id_etapa_resultante"], 3)
        self.wa.send_carousel.assert_not_called()

    def test_frase_valida_e_negacao_avancam(self):
        for texto, esperado in (("não quero falar de móveis", "estofados"),
                                ("gostaria de falar dos dois", "ambos")):
            envio = flow_sender(contexto_produto(texto))
            self.assertEqual(envio["produto"], esperado)
            self.assertEqual(envio["id_etapa_resultante"], 4)

    def test_universal_tem_prioridade_sobre_escolha_e_quarto_turno(self):
        for texto, tipo, turnos, evento in (
            (None, "audio", 3, "limite_sem_avanco"),
            (None, "image", 3, "limite_sem_avanco"),
            ("humano para móveis", "text", 0, "humano_solicitado"),
            ("id_desconhecido", "interactive", 3, "limite_sem_avanco"),
            ("talvez", "text", 3, "limite_sem_avanco"),
        ):
            envio = flow_sender(contexto_produto(texto, tipo=tipo, turnos=turnos))
            self.assertEqual(envio["id_etapa_resultante"], 7)
            self.assertEqual(envio["evento_transicao"], evento)
            self.assertNotIn("produto", envio)
            self.assertIn("encaminhado_sofas", envio)
            self.assertIn("encaminhado_moveis", envio)

    def test_mapa_invalido_impede_envio(self):
        ctx = contexto_produto()
        ctx["transicoes_permitidas"]["produto_escolhido"] = 5
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()

    def test_falha_meta_ou_falta_de_wamid_nao_devolve_produto(self):
        self.wa.send_message.side_effect = RuntimeError("Falha simulada")
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_produto())
        self.wa.send_message.side_effect = None
        self.wa.send_message.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_produto())

    def test_replay_na_etapa4_nao_envia_nem_reinterpreta(self):
        ctx = contexto_produto("Estofados")
        ctx["id_etapa_atual"] = 4
        ctx["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 4, "id_hash_msg": "wamid.confirmado",
            "interativo": {"_fluxo": {"evento": "produto_escolhido"}},
        }
        envio = flow_sender(ctx)
        self.assertTrue(envio["resposta_ja_existia"])
        self.assertNotIn("produto", envio)
        self.wa.send_message.assert_not_called()

    def test_efeito_produto_grava_somente_no_atendimento(self):
        cursor = MagicMock(rowcount=1)
        ctx = contexto_produto()
        envio = flow_sender(ctx)
        efeito = atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor)
        self.assertEqual(efeito, {"produto": "moveis"})
        cursor.execute.assert_called_once()
        self.assertIn("UPDATE chatbot.atendimento_pos_venda", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], ("moveis", 12))

    def test_dado_na_etapa_errada_e_produto_invalido_impedem_gravacao(self):
        cursor = MagicMock(rowcount=1)
        envio = {"id_etapa_resultante": 4, "evento_transicao": "produto_escolhido", "produto": "moveis"}
        for ctx, alteracao in ((contexto(etapa=1), {}), (contexto_produto(), {"produto": "outro"}),
                               (contexto_produto(), {"tratamento": True}),
                               (contexto_produto(), {"cpf_titular": "01234567890"})):
            with self.assertRaises(ValueError):
                atualizar_banco_conforme_transicao_de_etapa(ctx, dict(envio, **alteracao), cursor)
        cursor.execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
