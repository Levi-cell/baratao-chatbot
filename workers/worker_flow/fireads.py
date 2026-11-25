"""Compatibilidade dos resolvers legados 7/9; abertura Supera removida.

Este módulo não pertence ao atendimento de varejo ativo.
"""

from core.integrations.fireads.extratores import extrair_email


def email_importado(contexto):
    """Confia na coleta FireAds desta conversa, sem revalidar como texto de chat."""
    # Nome histórico da API mantido para replay dos eventos 7/9 -> 11.
    if contexto.get('contexto_coleta'):
        from core.validacoes.coleta_abertura import email_coletado
        return email_coletado(contexto)
    estado = contexto.get("contexto_fireads") or {}
    return (
        estado.get("concluida") is True
        and estado.get("resultado") == "importado"
        and estado.get("id_conversa") == contexto.get("id_conversa")
        and estado.get("dados_titular", {}).get("resultado_email") == "email_valido"
        and bool(extrair_email(estado.get("dados_titular", {}).get("email")))
    )
