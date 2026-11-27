import json
from pathlib import Path
from unittest import TestCase

from core.integrations.whatsapp.identidade_cliente import extrair_identidade
from core.validacoes.compartilhamento_contato import telefone_compartilhado
from core.validacoes.destinatario_whatsapp import escolher_destinatario

def entrada(nome):
    pasta = Path(__file__).resolve().parents[1] / "payloads"
    evento = json.loads((pasta / (nome + ".json")).read_text(encoding="utf-8-sig"))
    valor = evento["entry"][0]["changes"][0]["value"]
    return valor, valor["messages"][0]

class IdentidadeClienteTests(TestCase):
    def test_prioridade_das_rotas(self):
        for nome, rota in (("WAID", "wa_id"), ("WAID_BSUID_USERNAME", "wa_id"),
                           ("BSUID_USERNAME", "bsuid")):
            with self.subTest(nome=nome):
                identidade = extrair_identidade(*entrada(nome))
                self.assertEqual(escolher_destinatario(identidade.wa_id,
                                 identidade.user_id, False)[0], rota)

    def test_apenas_contato_oficial_do_remetente(self):
        _, msg = entrada("CONTACT_INFO")
        bsuid = msg["from_user_id"]
        self.assertTrue(telefone_compartilhado(msg, bsuid, ()))
        self.assertIsNone(telefone_compartilhado(msg, "outro", ()))
        msg["contacts"][0]["origin"] = "other"
        self.assertIsNone(telefone_compartilhado(msg, bsuid, ()))


class ContratoHTTP(TestCase):
    def test_telefone_e_bsuid_com_as_duas_rotas_de_central(self):
        import httpx
        from core.integrations.whatsapp.remetente import usar_remetente_central
        from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
        from core.integrations.whatsapp.tools.config import get_meta_graph_api_version
        for waac in (None,"901"):
            for chave, valor in (("to","5511999999999"),("recipient","BR.123456789")):
                with self.subTest(waac=waac,chave=chave):
                    def resposta(req):
                        corpo=json.loads(req.content)
                        self.assertEqual(req.url.path,f"/v{get_meta_graph_api_version()}/{waac or '900'}/messages")
                        self.assertEqual(corpo["messaging_account_id"],"800")
                        self.assertEqual(corpo[chave],valor)
                        self.assertNotIn("to" if chave=="recipient" else "recipient",corpo)
                        self.assertEqual(corpo["interactive"]["action"]["name"],"request_contact_info")
                        return httpx.Response(200,json={"messaging_product":"whatsapp",
                            "contacts":[{"input":valor, "user_id" if chave=="recipient" else "wa_id":valor}],
                            "messages":[{"id":"wamid.simulado"}]})
                    central={"phone_number_id":"900","waac_id":waac,"messaging_account_id":"800"}
                    with httpx.Client(transport=httpx.MockTransport(resposta)) as sessao:
                        with usar_remetente_central(central,"900"):
                            msg=conta_wa("900",token="teste",session=sessao).request_contact_info(to=valor,text="Teste")
                    self.assertEqual(msg.id,"wamid.simulado")

    def test_bloqueio_e_desbloqueio_pelo_sdk_com_waac_e_phone_id(self):
        import httpx
        from unittest.mock import patch
        from core.integrations.whatsapp.pywa_functions.cliente import conta_wa
        from core.integrations.whatsapp.tools import usuarios
        from core.integrations.whatsapp.remetente import usar_remetente_central

        for waac in (None, "771"):
            for chave, valor in (("user", "5511991234567"), ("user_id", "BR.12345")):
                with self.subTest(waac=waac, chave=chave):
                    metodos = []
                    def responder(req):
                        metodos.append(req.method)
                        self.assertTrue(req.url.path.endswith(f"/{waac or '999'}/block_users"))
                        self.assertEqual(json.loads(req.content)["block_users"], [{chave: valor}])
                        campo = "added_users" if req.method == "POST" else "removed_users"
                        resultado = {"input": valor, "wa_id" if chave == "user" else "user_id": valor}
                        return httpx.Response(200, json={"block_users": {campo: [resultado]}})
                    central = {"phone_number_id": "999", "messaging_account_id": "100", "waac_id": waac}
                    with httpx.Client(transport=httpx.MockTransport(responder)) as sessao:
                        with usar_remetente_central(central, "999"):
                            cliente = conta_wa("999", token="teste", session=sessao)
                        with patch.object(usuarios, "cliente_de_bloqueio", return_value=cliente):
                            self.assertTrue(usuarios.bloquear_usuario_meta(valor,"999").added_users)
                            self.assertTrue(usuarios.desbloquear_usuario_meta(valor,"999").removed_users)
                    self.assertEqual(metodos, ["POST", "DELETE"])
