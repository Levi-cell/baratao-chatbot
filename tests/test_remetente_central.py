"""Contratos HTTP da conta empresarial, sem chamadas à Meta."""
import json
import os
import unittest
from unittest.mock import patch

import httpx

from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
from core.integrations.whatsapp.remetente import WhatsAppCentral, usar_remetente_central
from tests.test_etapa1_pos_venda import contexto, ENV
from tests.test_etapa3_pos_venda import contexto_produto
from workers.worker_flow.response_flow.flow_sender import flow_sender


class RemetenteCentralTests(unittest.TestCase):
    def setUp(self):
        self.requisicoes = []

    def sessao(self):
        def responder(request):
            corpo = json.loads(request.content)
            self.requisicoes.append((request.url.path, corpo))
            if corpo.get("status") == "read":
                return httpx.Response(200, json={"success": True})
            return httpx.Response(200, json={
                "messaging_product": "whatsapp",
                "contacts": [{"input": corpo["to"], "wa_id": corpo["to"]}],
                "messages": [{"id": "wamid.teste"}],
            })
        return self.enterContext(httpx.Client(transport=httpx.MockTransport(responder)))

    def test_turno_texto_botoes_lista_cta_e_carrossel(self):
        def criar_cliente(**opcoes):
            return WhatsAppCentral(**{**opcoes, "session": self.sessao(), "token": "teste"})
        self.enterContext(patch("core.integrations.whatsapp.pywa_functions.cliente.WhatsAppCentral",
                                side_effect=criar_cliente))
        self.enterContext(patch.dict(os.environ, ENV))
        encaminhar_moveis = contexto(tipo="audio", turnos=3)
        encaminhar_moveis["produto"] = "moveis"
        for ctx, tipo in (
            (contexto(apresentacao=True), "text"), (contexto_produto("talvez"), "button"),
            (contexto_produto("móveis"), "list"), (encaminhar_moveis, "cta_url"),
            (contexto(tipo="audio", turnos=3), "carousel"),
        ):
            for waac in (None, "771"):
                with self.subTest(tipo=tipo, waac=waac):
                    ctx["central"]["waac_id"] = waac
                    self.requisicoes.clear()
                    envio = flow_sender(ctx)
                    self.assertEqual(envio["id_hash_msg_bot"], "wamid.teste")
                    (path, corpo), = self.requisicoes
                    self.assertTrue(path.endswith(f"/{waac or '999'}/messages"))
                    self.assertEqual(corpo["messaging_account_id"], "100")
                    self.assertEqual(corpo["to"], ctx["mensagem_cliente_atual"]["cliente_telefone"])
                    self.assertEqual(corpo.get("interactive", {}).get("type", corpo["type"]), tipo)

    def test_digitacao_e_isolamento_entre_centrais_apos_erro(self):
        central = contexto()["central"] | {"waac_id": "771"}
        outra = {"phone_number_id": "222", "messaging_account_id": "300", "waac_id": None}
        with usar_remetente_central(central, "999"):
            with self.assertRaisesRegex(ValueError, "difere"):
                with usar_remetente_central(outra, "222"):
                    conta_wa("999", token="teste", session=self.sessao())
            cliente = conta_wa("999", token="teste", session=self.sessao())
            self.assertTrue(cliente.indicate_typing(message_id="wamid.entrada").success)
            with self.assertRaisesRegex(ValueError, "remetente"):
                cliente.send_message(to="5511000000000", text="teste", sender="222")
        with usar_remetente_central(outra, "222"):
            conta_wa("222", token="teste", session=self.sessao()).send_message(to="5511000000000", text="teste")
        self.assertEqual(len(self.requisicoes), 2)
        (path_digitacao, digitacao), (path_envio, envio) = self.requisicoes
        self.assertTrue(path_digitacao.endswith("/771/messages"))
        self.assertNotIn("messaging_account_id", digitacao)
        self.assertTrue(path_envio.endswith("/222/messages"))
        self.assertEqual(envio["messaging_account_id"], "300")
