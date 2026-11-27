"""Histórico vinculado à conversa, fila e WAMID de origem."""
from psycopg.types.json import Jsonb


def buscar_resposta_bot_por_mensagem_cliente(id_conversa, id_mensagem_fila, id_hash_cliente_origem, cursor):
    cursor.execute("""
        SELECT id_mensagem, id_etapa, received_data_hora, id_hash_msg, conteudo_texto, tipo_mensagem, interativo
        FROM chatbot.historico_mensagens
        WHERE id_conversa = %s AND id_mensagem_fila = %s AND id_hash_cliente_origem = %s
          AND quem_enviou = 'bot' AND status_envio = 'sent' AND parte_resposta = 1;
    """, (id_conversa, id_mensagem_fila, id_hash_cliente_origem))
    row = cursor.fetchone()
    return dict(zip(("id_mensagem", "id_etapa", "received_data_hora", "id_hash_msg",
                     "conteudo_texto", "tipo_mensagem", "interativo"), row)) if row else None


def inserir_historico_mensagem_cliente(mensagem, id_conversa, id_etapa, cursor):
    cursor.execute("""
        INSERT INTO chatbot.historico_mensagens
            (id_conversa, id_etapa, received_data_hora, quem_enviou, id_hash_msg,
             id_mensagem_fila, tipo_mensagem, conteudo_texto, interativo)
        SELECT %s, %s, %s, 'cliente', %s, f.id_mensagem, f.tipo_mensagem, f.conteudo_texto, CASE WHEN f.tipo_mensagem='contacts' THEN NULL ELSE f.interativo END
        FROM chatbot.fila_mensagens f WHERE f.id_mensagem = %s AND f.id_conversa = %s
        ON CONFLICT (id_hash_msg) DO NOTHING
        RETURNING id_mensagem, received_data_hora, id_etapa;
    """, (id_conversa, id_etapa, mensagem["data_recebimento"], mensagem["id_hash"],
          mensagem["id_mensagem"], id_conversa))
    row = cursor.fetchone()
    if row:
        return (*row, True)
    cursor.execute("""
        SELECT id_mensagem, received_data_hora, id_etapa FROM chatbot.historico_mensagens
        WHERE id_conversa = %s AND id_mensagem_fila = %s AND id_hash_msg = %s AND quem_enviou = 'cliente';
    """, (id_conversa, mensagem["id_mensagem"], mensagem["id_hash"]))
    row = cursor.fetchone()
    if not row:
        raise ValueError("Histórico da entrada ausente ou pertencente a outra conversa/fila.")
    return (*row, False)


def inserir_historico_mensagem_bot(contexto, envio, cursor):
    entrada = contexto["mensagem_cliente_atual"]
    existente = buscar_resposta_bot_por_mensagem_cliente(
        contexto["id_conversa"], entrada["id_mensagem_fila"], entrada["id_hash_msg"], cursor)
    if existente:
        return existente["id_mensagem"], existente["received_data_hora"], False
    if not envio.get("id_hash_msg_bot"):
        raise ValueError("Meta não retornou o WAMID da resposta.")
    primeira = _inserir_parte_resposta(contexto["id_conversa"], entrada, envio, 1, cursor)
    if envio.get("segunda_resposta"):
        segunda = {**envio, **envio["segunda_resposta"]}
        _inserir_parte_resposta(contexto["id_conversa"], entrada, segunda, 2, cursor)
    return (*primeira, True)


def _inserir_parte_resposta(id_conversa, entrada, envio, parte, cursor):
    interativo = dict(envio.get("interativo") or {})
    # Metadado interno de recuperação; não é enviado como parte do payload Meta.
    interativo["_fluxo"] = {"evento": envio.get("evento_transicao")}
    cursor.execute("""
        INSERT INTO chatbot.historico_mensagens
            (id_conversa, id_etapa, received_data_hora, quem_enviou, id_hash_msg,
             id_mensagem_fila, id_hash_cliente_origem, tipo_mensagem, conteudo_texto, interativo, status_envio, tipo_destinatario, valor_destinatario, parte_resposta)
        VALUES (%s, %s, clock_timestamp(), 'bot', %s, %s, %s, %s, %s, %s, 'sent', %s, %s, %s)
        RETURNING id_mensagem, received_data_hora;
    """, (id_conversa, envio["id_etapa_resultante"], envio["id_hash_msg_bot"],
          entrada["id_mensagem_fila"], entrada["id_hash_msg"], envio["tipo_mensagem"],
          envio["mensagem_bot"], Jsonb(interativo), envio.get("tipo_destinatario"), envio.get("valor_destinatario"), parte))
    return cursor.fetchone()
