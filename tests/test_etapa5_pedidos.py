"""Contrato da etapa de pedidos da Baratão, com transporte simulado."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.pedidos_pos_venda import extrair_pedidos
from tests.test_etapa1_pos_venda import contexto, ENV, PATCH_TEXTO, PATCH_CARTOES
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa


def contexto_pedidos(texto, assunto="entrega", **opcoes):
    ctx = contexto(etapa=5, texto=texto, **opcoes)
    ctx.update(produto="moveis", assunto=assunto, codigos_filiais={"01", "05", "09", "15", "29"})
    ctx["transicoes_permitidas"].update(
        pedidos_assistencia=6, nota_perdida_assistencia=6,
        pedidos_demais_assuntos=6, nota_perdida_demais_assuntos=6,
    )
    return ctx


class EtapaPedidosTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.qa")
        for p in (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                  patch(PATCH_CARTOES, return_value=self.wa)):
            p.start()
            self.addCleanup(p.stop)

    def test_identificador_inteiro_e_zeros(self):
        for invalido in ("123", "12.9", "12.099", "12,09", "12.0A", "A12.09", "12.09B",
                         "1.2.09", "12#3.09", "12.09-1", "1:234.09", "12(34.09)",
                         "-12.09", "+12.09", "١٢.٠٩", "12/34.09", "12. 09", "12 .09"):
            with self.subTest(invalido=invalido):
                self.assertEqual(extrair_pedidos(invalido), [])
        self.assertEqual(extrair_pedidos("Pedido:0001.09,35.15 e (7.01). Repetindo 0001.09!"),
                         ["0001.09", "35.15", "7.01"])

    def test_sufixo_desconhecido_repete_com_botao_sem_gravacao_parcial(self):
        singular = "Olha, não consegui identificar uma nota válida. Me fala novamente a nota, por favor."
        plural = "Olha, uma ou mais notas estão inválidas. Digite todas novamente, por favor."
        for mensagem_esperada, exemplos in (
            (singular, ("12.00", "12.04", "12.99", "345.1", "123,01", "AB12.09",
                        "476.213543.23", "245.42.3453.23", "23#4.01", "234.0A", "234.01X",
                        "234.01/345.09", "234.01-345.09", "ABC", "@@@", "não entendi")),
            (plural, ("1.04,2.09", "234.01 e 345.1", "345.1 234.01", "234.01,345.1,456.999",
                      "345.1 e 456.4", "234.01 e A345.09", "1.01 e 2.04 e 3.15", "123 456",
                      "nota:123 e a outra nota:234.01", "a nota é 123 e a outra é 234.01",
                      "234.01 e 345 por favor", "234.01 e 23#4.09", "234.01 e 476.213543.23",
                      "234.01 e 245.42.3453.23", "234.01 e AB345.09:", "234.01 e nota ABC",
                      "234.01 e a outra nota é @@@", "234.01 e a outra nota é abc", "ABC e 234.01",
                      "234.01 e ABC", "234.01,ABC", "ABC, 234.01", "234.01 e AB345 aqui")),
        ):
            for texto in exemplos:
                with self.subTest(texto=texto):
                    ctx = contexto_pedidos(texto)
                    envio = flow_sender(ctx)
                    self.assertTrue(envio["tratamento"])
                    self.assertEqual(envio["mensagem_bot"], mensagem_esperada)
                    self.assertEqual(envio["interativo"]["action"]["buttons"][0]["reply"]["title"], "Perdi a nota")
                    self.assertNotIn("numeros_pedido", envio)
                    cursor = MagicMock()
                    self.assertEqual(atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor), {})
                    cursor.execute.assert_not_called()
                    cursor.executemany.assert_not_called()

    def test_quantidades_na_frase_nao_sao_notas_e_lista_valida_avanca(self):
        for texto, esperado in (
            ("Comprei 2 cadeiras no pedido 234.01", ["234.01"]),
            ("O pedido 234.01 tem 2 cadeiras e 1 mesa.", ["234.01"]),
            ("Comprei 2 ou 3 cadeiras no pedido 234.01.", ["234.01"]),
            ("São 2: 234.01 e 345.09.", ["234.01", "345.09"]),
            ("A NOTA FISCAL do pedido é 234.01.", ["234.01"]),
            ("MINHAS NOTAS SÃO 234.01 E 345.09.", ["234.01", "345.09"]),
            ("Nota 234.01, OBRIGADO!", ["234.01"]),
            ("234.01 é a nota correta", ["234.01"]),
            ("Comprei 2 produtos, seguem as notas 234.01 e 345.09", ["234.01", "345.09"]),
            ("Pedidos: (234.01,345.09), repetindo 234.01.", ["234.01", "345.09"]),
            ("Pedidos: (234.01),(345.09).", ["234.01", "345.09"]),
        ):
            with self.subTest(texto=texto):
                envio = flow_sender(contexto_pedidos(texto))
                self.assertEqual(envio["numeros_pedido"], esperado)
                self.assertEqual(envio["id_etapa_resultante"], 6)

    def test_pedidos_e_nota_perdida_seguem_o_assunto_da_conversa(self):
        for assunto in ("entrega", "assistencia", "montador", "outros", "misto"):
            for texto, tipo, esperado in (
                ("Meus pedidos são 001.09 e 001.15.", "text", ["001.09", "001.15"]),
                ("Perdi a nota", "text", []), ("Perdi a nota", "interactive", []),
                ("pedidos:nota_perdida", "interactive", []),
            ):
                with self.subTest(assunto=assunto, texto=texto):
                    ctx = contexto_pedidos(texto, tipo=tipo, assunto=assunto)
                    envio = flow_sender(ctx)
                    self.assertEqual(envio["numeros_pedido"], esperado)
                    self.assertEqual(envio["id_etapa_resultante"], 6)
        for texto, tipo in (("Acho que perdi a nota", "text"), ("pedidos:nota_perdida", "text"),
                            ("001.09", "interactive"), ("assunto:entrega", "interactive")):
            self.assertTrue(flow_sender(contexto_pedidos(texto, tipo=tipo))["tratamento"])

    def test_painel_exibe_opcoes_do_atendimento_registrado(self):
        from callback.monitoramento.apresentacao import botoes_para_mensagem
        mensagem = {"quem_enviou": "bot", "tipo": "interactive", "id_etapa": 5}
        self.assertEqual(botoes_para_mensagem(mensagem), ["Perdi a nota"])
        self.assertEqual(botoes_para_mensagem({**mensagem, "id_etapa": 6}), [])
        self.assertEqual(botoes_para_mensagem({**mensagem, "id_etapa": 7}), [])
        contato = {"action": {"name": "request_contact_info"}}
        self.assertEqual(botoes_para_mensagem({**mensagem, "interativo": contato}), [])
        cta = {"action": {"parameters": {"display_text": "Pós-venda Móveis"}}}
        self.assertEqual(botoes_para_mensagem({**mensagem, "id_etapa": 7, "interativo": cta}), ["Pós-venda Móveis"])

    def test_universal_tem_prioridade_na_etapa5(self):
        for entrada, tipo, turnos, evento in (
            ("1.99", "text", 3, "limite_sem_avanco"), ("humano, pedido 12.09", "text", 0, "humano_solicitado"),
            (None, "document", 3, "limite_sem_avanco"),
        ):
            envio = flow_sender(contexto_pedidos(entrada, tipo=tipo, turnos=turnos))
            self.assertEqual((envio["evento_transicao"], envio["id_etapa_resultante"]), (evento, 7))
            self.assertNotIn("numeros_pedido", envio)

    def test_mapa_divergente_impede_envio(self):
        ctx = contexto_pedidos("1.09")
        ctx["transicoes_permitidas"]["pedidos_demais_assuntos"] = 7
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()
