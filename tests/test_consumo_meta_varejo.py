"""Coberturas, consolidação e contratos da API; nunca acessa a Meta real."""

import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from core.consumo_meta.apuracao import calcular_resumo, decidir_apuracao, quantidades, validar_identidade
from core.integrations.whatsapp import consumo as integracao
from callback.monitoramento.consumo_services import apresentar_mes
from tests.consumo_fixtures import AGORA, CONTA, registro, resultado


class ResumoConsumoTests(unittest.TestCase):
    def test_cobertura_esl_nao_desconta_cobradas_meta_nem_total(self):
        r = registro()
        resumo = calcular_resumo(r)
        self.assertEqual(resumo, {"total_mensagens": 2500, "franquia_restante": 0,
                                 "assumidas_esl": 1000, "excedentes_central": 300,
                                 "valor_referencia_excedente": "10.50"})
        self.assertEqual(r["qtd_cobradas_meta"], 1300)

    def test_limites_cobertura_e_reserva_sem_saldo_negativo(self):
        for cobradas, cobertas, excesso in ((0, 0, 0), (999, 999, 0), (1000, 1000, 0), (1001, 1000, 1)):
            with self.subTest(cobradas=cobradas):
                r = registro(); r.update(qtd_cobradas_meta=cobradas, qtd_gratuitas=950,
                                         qtd_janela_gratuita=200, qtd_franquia_consumida=750)
                resumo = calcular_resumo(r)
                self.assertEqual((resumo["assumidas_esl"], resumo["excedentes_central"], resumo["franquia_restante"]),
                                 (cobertas, excesso, 250))

    def test_legado_nao_fabrica_divisao_ou_saldo(self):
        apresentado = apresentar_mes(registro(pendente=True), AGORA)
        self.assertTrue(apresentado["detalhamento_pendente"])
        self.assertIsNone(apresentado["qtd_janela_gratuita"])
        self.assertIsNone(apresentado["franquia_restante"])
        self.assertIsNone(apresentado["ultimo_sucesso_em"])
        self.assertEqual(apresentado["total_mensagens"], 2500)
        self.assertEqual(apresentado["assumidas_esl"], 1000)

    def test_identidade_legado_aceita_so_o_mesmo_numero_conta_e_fuso(self):
        validar_identidade(registro(pendente=True), resultado())
        for chave, novo in (("waba_id", "200"), ("fuso_horario", "America/Bahia")):
            with self.subTest(chave=chave), self.assertRaises(ValueError):
                validar_identidade(registro(pendente=True), dict(resultado(), **{chave: novo}))
        with self.assertRaises(ValueError):
            validar_identidade(registro(pendente=True), resultado(phone="202"))

    def test_volumes_invalidos_nao_viram_zero(self):
        for valor in (-1, True, 1.5, None, "100"):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                quantidades(resultado(cobradas=valor))
        with self.assertRaises(ValueError):
            quantidades(resultado(reserva=1001))

    def test_apresentacao_vira_mes_sem_mudar_total(self):
        r = apresentar_mes(registro(), datetime(2026, 12, 1, 3, tzinfo=timezone.utc))
        self.assertEqual(r["status_apuracao"], "em_conferencia")
        self.assertEqual(r["total_mensagens"], 2500)


class ConsolidacaoTests(unittest.TestCase):
    def setUp(self):
        self.agora = datetime(2026, 12, 25, 15, tzinfo=timezone.utc)
        self.anterior = registro()
        self.anterior.update(consultado_ate=self.anterior["data_hora_fim"],
                             ultimo_sucesso_em=self.agora - timedelta(days=1), status_apuracao="em_conferencia")

    def test_dia25_exige_leitura_igual_de_outro_dia_e_cobertura_completa(self):
        decisao = decidir_apuracao(self.anterior, resultado(agora=self.agora), self.agora)
        self.assertEqual(decisao["status_apuracao"], "consolidado")
        self.assertIsNone(decisao["data_proxima_consolidacao"])

    def test_alteracao_prolonga_ate_outro_dia25(self):
        d = decidir_apuracao(self.anterior, resultado(agora=self.agora, cobradas=1301), self.agora)
        self.assertEqual(d["status_apuracao"], "em_conferencia")
        self.assertEqual(d["data_proxima_consolidacao"], date(2027, 1, 25))

    def test_primeira_coleta_ou_leitura_mesmo_dia_nao_consolidam(self):
        self.anterior["ultimo_sucesso_em"] = self.agora - timedelta(hours=1)
        for anterior in (None, self.anterior):
            with self.subTest(anterior=anterior is None):
                d = decidir_apuracao(anterior, resultado(agora=self.agora), self.agora)
                self.assertEqual(d["status_apuracao"], "em_conferencia")

    def test_prazo_perdido_nao_consolida_no_dia26(self):
        agora = self.agora + timedelta(days=1)
        d = decidir_apuracao(self.anterior, resultado(agora=agora), agora)
        self.assertEqual(d["data_proxima_consolidacao"], date(2027, 1, 25))

    def test_mes_consolidado_nao_aceita_recoleta(self):
        self.anterior["status_apuracao"] = "consolidado"
        with self.assertRaises(ValueError):
            decidir_apuracao(self.anterior, resultado(agora=self.agora), self.agora)


class ContratoMetaTests(unittest.TestCase):
    def dados(self, **alteracoes):
        ponto = {"phone_number": "5511999990000", "pricing_category": "SERVICE", "pricing_type": "REGULAR", "volume": 1300}
        ponto.update(alteracoes)
        return {"pricing_analytics": {"data": [{"data_points": [ponto]}]}}

    def test_numero_errado_categoria_ou_paginacao_parcial_falham(self):
        for a in ({"phone_number": "5511999990001"}, {"pricing_category": "MARKETING"},
                  {"pricing_type": "DESCONHECIDO"}, {"volume": -1}):
            with self.subTest(a=a), self.assertRaises(RuntimeError):
                integracao._somar_metricas(self.dados(**a), "5511999990000")
        dados = self.dados(); dados["paging"] = {"next": "https://example.invalid"}
        with self.assertRaises(RuntimeError):
            integracao._somar_metricas(dados, "5511999990000")

    def test_api_consulta_so_service_volume_com_fronteira_local(self):
        numeros = {"data": [{"id": "101", "display_phone_number": "+55 11 99999-0000"}]}
        with patch.object(integracao, "_consultar_json", side_effect=[numeros, self.dados()]) as consulta:
            r = integracao.consultar_metricas_conta(CONTA, phone_number_id="101", mes="2026-11", agora=AGORA)
        fields = consulta.call_args.args[2]["fields"]
        self.assertIn(".metric_types(VOLUME).pricing_categories(SERVICE)", fields)
        self.assertIn(".dimensions(PHONE,PRICING_CATEGORY,PRICING_TYPE)", fields)
        self.assertEqual(datetime.fromisoformat(r["data_hora_inicio"]).hour, 0)
        self.assertEqual(datetime.fromisoformat(r["data_hora_inicio"]).utcoffset(), timedelta(hours=-3))
        self.assertEqual(quantidades(r)["qtd_cobradas_meta"], 1300)


if __name__ == "__main__":
    unittest.main()
