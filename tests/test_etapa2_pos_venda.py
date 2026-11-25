"""CPF e encaminhamento universal da etapa 2 sem serviços externos."""
import os
import unittest
from itertools import product
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.cpf_titular import extrair_cpf_titular
from core.integrations.whatsapp.messages.etapa2_messages import (
    MENSAGEM_PADRAO_ETAPA2, MENSAGEM_CPF_INVALIDO,
)
from core.integrations.whatsapp.messages.etapa3_messages import MENSAGEM_PRODUTO
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from workers.worker_flow.response_flow.flow_sender import flow_sender
from tests.test_etapa1_pos_venda import contexto, ENV, PATCH_TEXTO, PATCH_CARTOES


def contexto_cpf(texto="12345678901", *, tipo="text", turnos=0, cidade=None):
    ctx = contexto(etapa=2, texto=texto, tipo=tipo, turnos=turnos)
    ctx["transicoes_permitidas"] = {
        "cpf_valido": 3,
        "midia_recebida": 11, "humano_solicitado": 11, "limite_sem_avanco": 11,
    }
    ctx["cadastro"] = {"nome_titular": "João da Silva", "cidade_loja_compra": cidade}
    return ctx


class ExtratorCpfTests(unittest.TestCase):
    def test_pontuacao_completa_ou_faltando_em_todas_as_combinacoes(self):
        for ponto1, ponto2, traco in product(("", "."), ("", "."), ("", "-")):
            entrada = f"Meu CPF é 012{ponto1}345{ponto2}678{traco}90, obrigado."
            with self.subTest(entrada=entrada):
                self.assertEqual(extrair_cpf_titular(entrada), "01234567890")

    def test_extrai_documento_sem_juntar_numeros_da_frase(self):
        for entrada in (
            "01234567890", "CPF:012.345.678-90", "Tenho 30 anos, meu CPF é 01234567890.",
            "01234567890,obrigado", "(012.345.678-90)", "Meu CPF é *01234567890*",
            "RG 1234567, nasci em 01/02/1990. CPF 012.345.678-90.",
            "01234567890; confirmando: 012.345.678-90",
        ):
            with self.subTest(entrada=entrada):
                self.assertEqual(extrair_cpf_titular(entrada), "01234567890")

    def test_rejeita_ausente_maior_menor_letras_e_trechos(self):
        for entrada in (
            None, "", "não lembro", "1234567890", "123456789012", "123.456.789-0",
            "123.456.789-012", "123.456.78A-01", "1234567890A", "A12345678901",
            "12345678901A", "123456789O1", "12345678901/2", "12345678901+2",
            "12345678901,2", "0123456789-012", "123 456 789 01", "123_456_789_01",
            "１２３４５６７８９０１", "123.4567.8901X", "123.456.789-01/99",
            "RG 12345678 e pedido 901", "123..456.789-01",
        ):
            with self.subTest(entrada=entrada):
                self.assertIsNone(extrair_cpf_titular(entrada))

    def test_dois_cpfs_diferentes_exigem_correcao(self):
        self.assertIsNone(extrair_cpf_titular("O meu é 012.345.678-90 e o dele 12345678901"))

    def test_simbolos_proibidos_nao_sao_removidos_nem_separam_um_cpf_parcial(self):
        cpf = "01234567890"
        for simbolo in '/\\@#$_+*=,:;!?|&%~^<>()[]{}\"\'–—😊\u200b':
            entradas = [cpf[:i] + simbolo + cpf[i:] for i in range(1, len(cpf))]
            entradas += [cpf + simbolo + "1", "1" + simbolo + cpf]
            for entrada in entradas:
                with self.subTest(entrada=entrada):
                    self.assertIsNone(extrair_cpf_titular("Meu CPF é " + entrada))

    def test_criterio_e_formato_nao_digito_verificador_ou_receita(self):
        self.assertEqual(extrair_cpf_titular("11111111111"), "11111111111")
        self.assertEqual(extrair_cpf_titular("000.000.000-00"), "00000000000")


class Etapa2Tests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.cpf")
        self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.carrossel")
        patches = (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                   patch(PATCH_CARTOES, return_value=self.wa))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_nome_valido_agora_envia_novo_texto_do_cpf(self):
        envio = flow_sender(contexto(texto="João da Silva"))
        self.assertEqual(envio["id_etapa_resultante"], 2)
        self.assertEqual(envio["mensagem_bot"], "Certo agora em uma única mensagem me informe seu CPF.")

    def test_cpf_extraido_avanca_com_zero_inicial_preservado(self):
        envio = flow_sender(contexto_cpf("Meu CPF: 012.345678-90"))
        self.assertEqual(envio["cpf_titular"], "01234567890")
        self.assertEqual(envio["id_etapa_resultante"], 3)
        self.assertEqual(envio["evento_transicao"], "cpf_valido")
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_PRODUTO)

    def test_cidade_global_ja_presente_vai_ao_produto_com_tres_botoes(self):
        envio = flow_sender(contexto_cpf(cidade="Salvador"))
        self.assertEqual(envio["id_etapa_resultante"], 3)
        self.assertEqual(envio["evento_transicao"], "cpf_valido")
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_PRODUTO)
        self.assertEqual([b["reply"]["title"] for b in envio["interativo"]["action"]["buttons"]],
                         ["Apenas Estofados", "Apenas Móveis", "Estofados e Móveis"])

    def test_invalido_permanece_sem_tentar_salvar_cpf(self):
        for texto in ("12345678A01", "012/345/678-90", "01234567890@1", "012_345_678_90"):
            with self.subTest(texto=texto):
                envio = flow_sender(contexto_cpf(texto))
                self.assertEqual(envio["mensagem_bot"], MENSAGEM_CPF_INVALIDO)
                self.assertEqual(envio["id_etapa_resultante"], 2)
                self.assertTrue(envio["tratamento"])
                self.assertNotIn("cpf_titular", envio)
                self.assertNotIn("evento_transicao", envio)

    def test_tres_erros_repetem_e_quarto_encaminha(self):
        for turnos in range(3):
            self.assertEqual(flow_sender(contexto_cpf("123", turnos=turnos))["mensagem_bot"], MENSAGEM_CPF_INVALIDO)
        envio = flow_sender(contexto_cpf("123", turnos=3))
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.wa.send_carousel.assert_called_once()

    def test_midia_ou_pedido_humano_usam_o_universal_antes_do_cpf(self):
        for tipo, texto, evento in (("audio", None, "midia_recebida"),
                                    ("text", "Quero um HUMANO, CPF 01234567890", "humano_solicitado")):
            envio = flow_sender(contexto_cpf(texto, tipo=tipo))
            self.assertEqual(envio["id_etapa_resultante"], 11)
            self.assertEqual(envio["evento_transicao"], evento)
            self.assertNotIn("cpf_titular", envio)
        self.wa.send_message.assert_not_called()

    def test_transicao_ausente_impede_envio(self):
        ctx = contexto_cpf()
        ctx["transicoes_permitidas"].pop("cpf_valido")
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()

    def test_falha_meta_ou_ausencia_de_wamid_nao_devolve_cpf_para_persistir(self):
        self.wa.send_message.side_effect = RuntimeError("falha simulada")
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_cpf())
        self.wa.send_message.side_effect = None
        self.wa.send_message.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto_cpf())

    def test_replay_nao_reinterpreta_documento_nem_envia(self):
        ctx = contexto_cpf("conteúdo diferente")
        ctx["id_etapa_atual"] = 3
        ctx["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 3, "id_hash_msg": "wamid.confirmado",
            "interativo": {"_fluxo": {"evento": "cpf_valido"}},
        }
        envio = flow_sender(ctx)
        self.assertTrue(envio["resposta_ja_existia"])
        self.assertNotIn("cpf_titular", envio)
        self.wa.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
