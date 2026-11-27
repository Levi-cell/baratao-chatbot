def escolher_destinatario(wa_id_confirmado, bsuid_vigente, contato_pendente):
    if wa_id_confirmado and not contato_pendente:
        return "wa_id", wa_id_confirmado
    if bsuid_vigente:
        return "bsuid", bsuid_vigente
    raise ValueError("Sem destinatário comprovado para o turno")
