"""Dados fictícios de consumo, sem credenciais ou identificadores reais."""

from datetime import date, datetime, timezone
from decimal import Decimal

from core.consumo_meta.periodos import fronteiras_mes

AGORA = datetime(2026, 11, 22, 15, tzinfo=timezone.utc)
CONTA = {"waba_id": "100", "timezone_id": "25", "fuso_horario": "America/Sao_Paulo"}


def resultado(mes="2026-11", *, agora=AGORA, janela=200, reserva=1000, cobradas=1300, phone="101"):
    inicio, fim = fronteiras_mes(date.fromisoformat(mes + "-01"), CONTA["fuso_horario"])
    return {
        **CONTA, "mes": mes, "data_hora_inicio": inicio.isoformat(), "data_hora_fim": fim.isoformat(),
        "fim_exclusivo": min(agora, fim).isoformat(),
        "numeros": [{"phone_number_id": phone, "volumes_por_tipo": {
            "FREE_ENTRY_POINT": janela, "FREE_CUSTOMER_SERVICE": reserva, "REGULAR": cobradas,
        }}],
    }


def registro(*, pendente=False):
    r = resultado()
    return {
        "id_central": 1, "mes_referencia": date(2026, 11, 1),
        "waba_id": "100", "phone_number_id": "101", "timezone_id": None if pendente else 25,
        "fuso_horario": CONTA["fuso_horario"],
        "data_hora_inicio": None if pendente else datetime.fromisoformat(r["data_hora_inicio"]),
        "data_hora_fim": None if pendente else datetime.fromisoformat(r["data_hora_fim"]),
        "consultado_ate": AGORA, "ultimo_sucesso_em": None if pendente else AGORA,
        "qtd_gratuitas": 1200, "qtd_janela_gratuita": None if pendente else 200,
        "qtd_franquia_consumida": None if pendente else 1000, "qtd_cobradas_meta": 1300,
        "status_apuracao": "pendente_detalhamento" if pendente else "em_andamento",
        "data_proxima_consolidacao": None if pendente else date(2026, 12, 25),
        "consolidado_em": None, "ultima_decisao_consolidacao_em": None,
        "franquia_meta_mensal": 1000, "beneficio_esl_mensal": 1000,
        "tarifa_referencia_brl": Decimal("0.035"), "tarifa_vigencia": date(2026, 10, 1),
        "ultimo_erro": None,
    }
