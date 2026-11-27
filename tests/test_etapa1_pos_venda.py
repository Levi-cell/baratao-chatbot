"""Testes sem banco, Redis, requisições reais ou envio para pessoas."""
import os
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.validacoes.nome_titular import normalizar_nome_titular
from core.integrations.whatsapp.messages.etapa1_messages import (
    MENSAGEM_PADRAO_ETAPA1, MENSAGEM_NOME_INVALIDO,
)
from core.integrations.whatsapp.messages.encaminhamento_pos_venda import (
    MENSAGEM_AMBOS_PRODUTOS, MENSAGEM_PRODUTO_NAO_INFORMADO,
)
from core.integrations.whatsapp.exceptions import ErroEnvioMeta
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import montar_cartoes
from core.integrations.whatsapp.pywa_functions.cliente import antes_do_primeiro_envio, conta_wa
from core.cache.runtime import cache_conversas_bloqueadas as bloqueio
from workers.worker_flow.response_flow.flow_sender import flow_sender

ENV = {"WHATSAPP_MIDIAS_BASE_URL": "https://example.test/static/monitoramento/img/pos_venda"}
PATCH_TEXTO = "core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda.conta_wa"
PATCH_CARTOES = "core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda.conta_wa"


def contexto(etapa=1, texto="123", tipo="text", turnos=0, apresentacao=False):
    return {
        "apresentacao_pendente": apresentacao, "id_conversa": 12, "id_cliente": 13, "id_etapa_atual": etapa,
        "id_etapa_origem_transicao": etapa, "turnos_sem_avanco": turnos,
        "resposta_bot_para_mensagem_atual": None,
        "transicoes_permitidas": {
            "nome_valido_falta_cpf": 2, "midia_recebida": 7,
            "humano_solicitado": 7, "limite_sem_avanco": 7,
        },
        "central": {"telefone_sofas": "557592087803", "telefone_moveis": "557582467000",
                    "phone_number_id": "999", "messaging_account_id": "100", "waac_id": None},
        "cadastro": {},
        "mensagem_cliente_atual": {"tipo_mensagem": tipo, "conteudo_texto": texto,
                                  "cliente_telefone": "5511999990000", "id_phone_unidade": "999"},
    }


class Etapa1Tests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.wa = MagicMock()
        self.wa.send_message.return_value = SimpleNamespace(id="wamid.texto")
        self.wa.send_carousel.return_value = SimpleNamespace(id="wamid.carrossel")
        for destino in (PATCH_TEXTO, PATCH_CARTOES):
            patcher = patch(destino, return_value=self.wa)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_nomes_aceitos(self):
        for entrada, esperado in (
            ("Olá, eu me chamo Ana Maria da Silva.", "Ana Maria da Silva"),
            ("O nome dele é João-Pedro de Souza", "João-Pedro de Souza"),
            ("Eu sou a Ana Costa", "Ana Costa"),
            ("Nome do titular da compra é José dos Santos", "José dos Santos"),
            ("Meu nome é Maria Silva e quero falar do pedido", "Maria Silva"),
            ("João da silva.", "João da silva"),
            ("João-Pedro da Silva", "João-Pedro da Silva"),
            ("João-Pedro da Silva.", "João-Pedro da Silva"),
            ("  María  José da Conceição  ", "María José da Conceição"),
            ("Joa\u0303o da Silva", "João da Silva"),
        ):
            with self.subTest(entrada=entrada):
                self.assertEqual(normalizar_nome_titular(entrada), esperado)

    def test_nomes_invalidos(self):
        for entrada in ("O nome dele é", "Eu me chamo Ana", "Eu sou de Salvador", "Ana de",
                        "Eu sou João2 Silva", "Quero falar do pedido", None, "", " ", "123", "João 123", "João @ Silva", "João da Silva!",
                        ".João Silva", "João. Silva", "João Silva..", "João - Pedro Silva",
                        "-João Silva", "João- Silva", "João -- Silva", "João Silva-",
                        "João 😊 Silva", "João O'Connor", "João Silva .", "João"):
            with self.subTest(entrada=entrada):
                self.assertIsNone(normalizar_nome_titular(entrada))

    def test_primeiro_contato_apresenta_regras_mesmo_com_midia_ou_humano(self):
        for tipo, texto in (("audio", None), ("image", None), ("text", "Quero um HUMANO"), ("text", "João da Silva")):
            envio = flow_sender(contexto(apresentacao=True, tipo=tipo, texto=texto, turnos=3))
            self.assertRegex(envio["mensagem_bot"], r"^(Bom dia|Boa tarde|Boa noite), eu sou o Theo")
            self.assertEqual(envio["mensagem_bot"].count("\n\n"), 2)
            self.assertIn("nome completo do titular",envio["mensagem_bot"])
            self.assertEqual(envio["id_etapa_resultante"], 1)
            self.assertNotIn("evento_transicao", envio)
        self.wa.send_carousel.assert_not_called()

    def test_tres_repeticoes_e_quarto_encaminhamento(self):
        for turnos in range(3):
            envio = flow_sender(contexto(turnos=turnos))
            self.assertEqual(envio["mensagem_bot"], MENSAGEM_NOME_INVALIDO)
            self.assertNotIn("evento_transicao", envio)
        envio = flow_sender(contexto(turnos=3))
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.assertEqual(envio["id_etapa_resultante"], 7)
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_PRODUTO_NAO_INFORMADO)
        self.wa.send_carousel.assert_called_once()

    def test_nome_valido_avanca_para_cpf(self):
        envio = flow_sender(contexto(texto="João-Pedro da Silva.", turnos=2))
        self.assertEqual(envio["nome_titular"], "João-Pedro da Silva")
        self.assertEqual(envio["id_etapa_resultante"], 2)
        self.assertEqual(envio["evento_transicao"], "nome_valido_falta_cpf")

    def test_todos_tipos_nao_textuais_encaminham_apos_saudacao(self):
        for tipo in ("audio", "image", "video", "document", "sticker", "location", "contacts", "interactive", "unknown"):
            with self.subTest(tipo=tipo):
                envio = flow_sender(contexto(tipo=tipo, texto=None))
                self.assertEqual(envio["evento_transicao"], "midia_recebida")
                self.assertEqual(envio["mensagem_bot"], MENSAGEM_PRODUTO_NAO_INFORMADO)

    def test_midia_apos_escolher_ambos_usa_mensagem_dos_dois_produtos(self):
        c = contexto(etapa=4, tipo="audio", texto=None)
        c["produto"] = "ambos"
        envio = flow_sender(c)
        self.assertEqual(envio["evento_transicao"], "midia_recebida")
        self.assertEqual(envio["mensagem_bot"], MENSAGEM_AMBOS_PRODUTOS)

    def test_humano_em_qualquer_frase_sem_diferenciar_caixa(self):
        for texto in ("Humano", "Quero falar com um HUMANO, por favor", "tem atendimento humano?"):
            self.assertEqual(flow_sender(contexto(texto=texto))["evento_transicao"], "humano_solicitado")

    def test_aviso_de_avarias_depende_do_assunto_da_conversa(self):
        from core.integrations.whatsapp.messages.encaminhamento_pos_venda import AVISO_ASSISTENCIA, mensagem_de_contato
        for assunto in ("assistencia", "misto", "entrega", "montador", "outros", None):
            with self.subTest(assunto=assunto):
                texto = mensagem_de_contato("Selecione o setor.", assunto)
                self.assertEqual(AVISO_ASSISTENCIA in texto, assunto in ("assistencia", "misto"))

    def test_cartoes_ordem_destinos_e_imagens(self):
        cards = [c.to_dict(i) for i, c in enumerate(montar_cartoes(contexto()))]
        self.assertEqual(len(cards), 2)
        for i, (rotulo, numero, imagem) in enumerate((
            ("Pós-venda Estofados", "557592087803", "estofados.png"),
            ("Pós-venda Móveis", "557582467000", "moveis.png"),
        )):
            card = cards[i]
            self.assertEqual(card["card_index"], i)
            self.assertNotIn("body", card)
            self.assertEqual(card["action"]["parameters"]["display_text"], rotulo)
            self.assertTrue(card["action"]["parameters"]["url"].startswith(f"https://wa.me/{numero}?text="))
            self.assertTrue(card["header"]["image"]["link"].endswith(imagem))
            self.assertNotIn("123", card["action"]["parameters"]["url"])

    def test_configuracao_incompleta_nao_envia_nem_inventa_destino(self):
        for base in ("", "http://example.test/img", "https://example.test/img?token=x"):
            with patch.dict(os.environ, {"WHATSAPP_MIDIAS_BASE_URL": base}):
                with self.assertRaises(ValueError):
                    flow_sender(contexto(tipo="audio"))
        c = contexto(tipo="audio")
        c["central"]["telefone_sofas"] = None
        with self.assertRaises(ValueError):
            flow_sender(c)
        self.wa.send_carousel.assert_not_called()

    def test_falha_meta_e_propagada_para_recuperacao_worker(self):
        self.wa.send_carousel.side_effect = RuntimeError("falha simulada")
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto(tipo="audio"))
        self.wa.send_message.assert_not_called()

    def test_resposta_sem_wamid_nao_e_considerada_enviada(self):
        self.wa.send_carousel.return_value = {}
        with self.assertRaises(ErroEnvioMeta):
            flow_sender(contexto(texto="humano"))

    def test_replay_nao_envia_nem_reclassifica(self):
        c = contexto(etapa=10)
        c["resposta_bot_para_mensagem_atual"] = {
            "id_etapa": 10, "id_hash_msg": "wamid.confirmado",
            "interativo": {"_fluxo": {"evento": "limite_sem_avanco"}},
        }
        with patch.dict(os.environ, {"WHATSAPP_MIDIAS_BASE_URL": ""}):
            envio = flow_sender(c)
        self.assertTrue(envio["resposta_ja_existia"])
        self.assertEqual(envio["evento_transicao"], "limite_sem_avanco")
        self.wa.send_message.assert_not_called()
        self.wa.send_carousel.assert_not_called()

    def test_mapa_invalido_impede_envio(self):
        c = contexto(tipo="audio")
        c["transicoes_permitidas"]["midia_recebida"] = 8
        with self.assertRaises(ValueError):
            flow_sender(c)
        self.wa.send_carousel.assert_not_called()

    def test_etapas_antigas_nao_sao_reutilizadas_por_engano(self):
        with self.assertRaises(NotImplementedError):
            flow_sender(contexto(etapa=8))
        self.wa.send_message.assert_not_called()


class CacheBloqueioTests(unittest.TestCase):
    def test_ttl_usa_data_confirmada_nao_renova_noventa_dias(self):
        fim = datetime.now(timezone.utc) - timedelta(days=10)
        ttl = bloqueio._calcular_ttl(fim, 90)
        self.assertTrue(80 * 86400 - 2 <= ttl <= 80 * 86400)
        self.assertLessEqual(bloqueio._calcular_ttl(fim - timedelta(days=81), 90), 0)
        self.assertEqual(bloqueio._calcular_ttl(None, 90), 0)

    def test_chave_separa_centrais(self):
        self.assertNotEqual(bloqueio._cache_key("5511999990000", "1"), bloqueio._cache_key("5511999990000", "2"))

    @patch.object(bloqueio, "_conversa_esta_bloqueada_banco_e_repara_cache", return_value=True)
    @patch.object(bloqueio, "get_redis_safe")
    def test_cache_vazio_consulta_banco(self, redis, fallback):
        redis.return_value.exists.return_value = False
        self.assertTrue(bloqueio.conversa_esta_bloqueada_cache("5511999990000", "1"))
        fallback.assert_called_once()

    @patch.object(bloqueio, "_conversa_esta_bloqueada_banco_e_repara_cache", return_value=True)
    @patch.object(bloqueio, "get_redis_safe", side_effect=ConnectionError("redis indisponível"))
    def test_cache_indisponivel_consulta_banco(self, redis, fallback):
        self.assertTrue(bloqueio.conversa_esta_bloqueada_cache("5511999990000", "1"))
        fallback.assert_called_once()

    @patch.object(bloqueio, "get_redis_safe")
    def test_hash_e_expiracao_atomicos(self, redis):
        self.assertTrue(bloqueio.registrar_bloqueio_conversa_cache(
            "5511999990000", "1", datetime.now(timezone.utc), 90))
        pipe = redis.return_value.pipeline
        pipe.assert_called_once_with(transaction=True)
        pipe.return_value.__enter__.return_value.expire.assert_called_once()
        pipe.return_value.__enter__.return_value.execute.assert_called_once()


class TransporteTests(unittest.TestCase):
    def test_carrossel_preserva_acao_antes_do_envio_uma_vez(self):
        with patch("core.integrations.whatsapp.pywa_functions.cliente.WhatsAppCentral") as sdk:
            acao = MagicMock()
            with antes_do_primeiro_envio(acao):
                wa = conta_wa("999", token="token-falso")
                wa.send_carousel(to="5511999990000", body="Contatos", cards=[])
                wa.send_message(to="5511999990000", text="Outro")
            acao.assert_called_once()
            sdk.return_value.send_carousel.assert_called_once()

    def test_serializacao_real_do_sdk_com_http_simulado(self):
        import httpx
        import json
        from pywa import WhatsApp
        capturados = []
        def responder(request):
            capturados.append(json.loads(request.content))
            return httpx.Response(200, json={"messaging_product": "whatsapp",
                "contacts": [{"input": "5511999990000", "wa_id": "5511999990000"}],
                "messages": [{"id": "wamid.simulado"}]})
        with patch.dict(os.environ, ENV), httpx.Client(transport=httpx.MockTransport(responder)) as session:
            wa = WhatsApp(phone_id="999", token="token-falso", session=session)
            resposta = wa.send_carousel(to="5511999990000", body=MENSAGEM_PRODUTO_NAO_INFORMADO, cards=montar_cartoes(contexto()))
        self.assertEqual(resposta.id, "wamid.simulado")
        self.assertEqual(len(capturados), 1)
        payload = capturados[0]
        self.assertEqual(payload["interactive"]["type"], "carousel")
        self.assertEqual(len(payload["interactive"]["action"]["cards"]), 2)


if __name__ == "__main__":
    unittest.main()
