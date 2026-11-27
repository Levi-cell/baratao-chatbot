"""Contrato da lista, texto livre, efeitos por conversa e encaminhamento humano."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from callback.webhook.services.populating_fila_mensagens import extrair_conteudo_texto_mensagem
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.validacoes.assunto_pos_venda import extrair_assunto
from workers.worker_flow.response_flow.flow_sender import flow_sender
from workers.worker_flow.transacoes.efeitos_transicao import atualizar_banco_conforme_transicao_de_etapa
from tests.test_etapa1_pos_venda import ENV, PATCH_CARTOES, PATCH_TEXTO, contexto


def contexto_assunto(texto, *, produto="moveis", **kwargs):
    ctx = contexto(etapa=4, texto=texto, **kwargs)
    ctx["produto"] = produto
    ctx["transicoes_permitidas"]["assunto_escolhido"] = 5
    return ctx


class AssuntoTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.send_message.return_value = self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.qa")
        for p in (patch.dict(os.environ, ENV), patch(PATCH_TEXTO, return_value=self.wa),
                  patch(PATCH_CARTOES, return_value=self.wa)):
            p.start()
            self.addCleanup(p.stop)

    def test_frases_reconhecem_categorias_distintas(self):
        for texto, esperado in (
            ("Qual é a previsão de entrega?", "entrega"),
            ("Meu sofá veio com avarias. Preciso de ASSISTENCIA.", "assistencia"),
            ("Preciso de um montador para a montagem", "montador"),
            ("Queria falar de outra coisa", "outros"), ("É outro assunto.", "outros"),
            ("Outros", "outros"), ("Quero a previsão e um montador", "misto"),
            ("Montagem, assistência e entrega", "misto"), ("Avarias e outro assunto", "misto"),
            ("Duas ou mais opções acima", "misto"), ("desmontagem", None),
            ("Entregador", None), ("Oi", None), ("123", None), (None, None),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(extrair_assunto(texto), esperado)

    def test_todas_as_linhas_da_lista_passam_pelo_webhook_e_gravam_no_atendimento(self):
        lista = flow_sender(contexto_assunto("", apresentacao=True))
        linhas = lista["interativo"]["action"]["sections"][0]["rows"]
        self.assertEqual([r["id"] for r in linhas], [
            "assunto:entrega", "assunto:assistencia", "assunto:montador", "assunto:misto", "assunto:outros",
        ])
        for linha in linhas:
            self.assertLessEqual(len(linha["title"]), 24)
            for opcao in (linha, {"id": linha["id"]}):
                payload = {"interactive": {"type": "list_reply", "list_reply": opcao}}
                texto = extrair_conteudo_texto_mensagem(payload, "interactive")
                ctx = contexto_assunto(texto, tipo="interactive")
                envio = flow_sender(ctx)
                assunto = linha["id"].split(":")[1]
                self.assertEqual((envio["id_etapa_resultante"], envio["evento_transicao"], envio["assunto"]),
                                 (5, "assunto_escolhido", assunto))
                self.assertEqual(envio["interativo"]["action"]["buttons"][0]["reply"]["title"], "Perdi a nota")
                cursor = MagicMock(rowcount=1)
                self.assertEqual(atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor), {"assunto": assunto})
                self.assertEqual(cursor.execute.call_args.args[1], (assunto, ctx["id_conversa"]))

    def test_entrada_invalida_repete_a_mesma_lista_sem_gravar(self):
        lista = flow_sender(contexto_assunto("", apresentacao=True))["interativo"]["action"]
        for texto, tipo in (("Oi", "text"), ("produto:ambos", "interactive"),
                            ("Mais de um ou outros", "interactive"), ("quero entrega", "interactive")):
            ctx = contexto_assunto(texto, tipo=tipo)
            envio = flow_sender(ctx)
            self.assertEqual(envio["interativo"]["action"], lista)
            self.assertEqual(envio["tipo_tratamento"], "assunto_invalido")
            self.assertTrue(envio["tratamento"])
            self.assertEqual(envio["id_etapa_resultante"], 4)
            cursor = MagicMock()
            self.assertEqual(atualizar_banco_conforme_transicao_de_etapa(ctx, envio, cursor), {})
            cursor.execute.assert_not_called()

    def test_universal_antecipa_assunto_e_respeita_produto_ja_escolhido(self):
        for produto, entrada, tipo, turnos, evento, setores in (
            ("moveis", "Quero um humano para a entrega", "text", 0, "humano_solicitado", {"moveis"}),
            ("estofados", None, "image", 0, "midia_recebida", {"sofas"}),
            ("ambos", "Outros", "interactive", 3, "limite_sem_avanco", {"moveis", "sofas"}),
        ):
            ctx = contexto_assunto(entrada, tipo=tipo, turnos=turnos, produto=produto)
            envio = flow_sender(ctx)
            self.assertEqual((envio["id_etapa_resultante"], envio["evento_transicao"]), (7, evento))
            self.assertNotIn("assunto", envio)
            self.assertEqual({k for k in envio if k.startswith("encaminhado_")},
                             {f"encaminhado_{s}" for s in setores})
            if len(setores) == 1:
                self.assertEqual(envio["interativo"]["type"], "cta_url")
                self.assertNotIn("header", self.wa.send_message.call_args.kwargs)
                self.assertNotIn("header", envio["interativo"])
                telefone = ctx["central"]["telefone_" + next(iter(setores))]
                self.assertIn(f"wa.me/{telefone}?", envio["interativo"]["action"]["parameters"]["url"])

    def test_mapa_e_confirmacao_da_meta_antes_de_qualquer_efeito(self):
        ctx = contexto_assunto("Montagem")
        ctx["transicoes_permitidas"]["assunto_escolhido"] = 6
        with self.assertRaises(ValueError):
            flow_sender(ctx)
        self.wa.send_message.assert_not_called()
        ctx["transicoes_permitidas"]["assunto_escolhido"] = 5
        self.wa.send_message.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(ctx)
