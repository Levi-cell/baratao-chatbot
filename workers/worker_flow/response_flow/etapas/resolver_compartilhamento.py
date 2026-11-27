from core.validacoes.encaminhamento_pos_venda import LIMITE_TURNOS_SEM_AVANCO

def acao_contato(*, solicitacao_enviada, telefone_provado, tipo, texto, erros_cliente):
    if not solicitacao_enviada:
        return "solicitar"
    if telefone_provado:
        return "confirmar_e_retomar"
    if tipo not in {"text", "interactive", "button"}:
        return "midia_recebida"
    if tipo == "text" and "humano" in (texto or "").casefold():
        return "humano_solicitado"
    if erros_cliente >= LIMITE_TURNOS_SEM_AVANCO:
        return "limite_sem_avanco"
    return "repetir_botao"


from core.etapas_pos_venda import ETAPA_CPF, ETAPA_PRODUTO, ETAPA_ASSUNTO, ETAPA_PEDIDOS, ETAPA_DETALHES, ETAPA_NOME, ETAPA_ENCAMINHAMENTO
from core.integrations.whatsapp.messages.compartilhamento_contato import mensagem_contato, primeiro_nome
from core.integrations.whatsapp.messages.etapa2_messages import montar_mensagem_etapa2
from core.integrations.whatsapp.pywa_functions.pywa_senders.compartilhamento_contato import enviar_solicitacao
from core.integrations.whatsapp.pywa_functions.pywa_senders.texto_pos_venda import enviar_texto_pos_venda
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa1 import enviar_etapa1
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa3 import enviar_etapa3
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa4 import enviar_etapa4
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa5_pedidos import enviar_etapa5_pedidos
from core.integrations.whatsapp.pywa_functions.pywa_senders.etapa6_detalhes import enviar_etapa6_detalhes
from core.integrations.whatsapp.pywa_functions.pywa_senders.encaminhamento_pos_venda import enviar_encaminhamento
from workers.worker_flow.response_flow.transicoes.resolver_transicao import resolver_destino_transicao, anexar_transicao_ao_contexto_envio
from core.validacoes.compartilhamento_contato import telefone_compartilhado


def pedir(contexto, etapa, nome, *, repetir=False, reconfirmar=False):
    uid = contexto["bsuid_vigente"]
    phone = contexto["central"]["phone_number_id"]
    texto = mensagem_contato(nome, repeticao=repetir, reconfirmacao=reconfirmar,
                             abertura=contexto.get("apresentacao_pendente", False))
    envio = enviar_solicitacao(uid, phone, texto, etapa)
    return dict(envio, operacao_contato="repetir" if repetir else "abrir",
                motivo_contato="reconfirmacao" if reconfirmar else "cadastro",
                bsuid_contato=uid, tipo_destinatario="bsuid", valor_destinatario=uid)


def resolver_turno_contato(ctx):
    entrada = ctx["mensagem_cliente_atual"]
    etapa, pendente = ctx["id_etapa_atual"], ctx["solicitacao_contato"]
    nome = ctx["cadastro"].get("nome_titular")
    uid = ctx["bsuid_vigente"]
    prova = telefone_compartilhado(entrada.get("estrutura_compartilhamento") or {}, uid, pendente["wamids"])
    acao = acao_contato(solicitacao_enviada=True, telefone_provado=prova,
                        tipo=entrada["tipo_mensagem"], texto=entrada.get("conteudo_texto"),
                        erros_cliente=pendente["erros"])
    if acao == "confirmar_e_retomar":
        # A pergunta que contém dados cadastrais só é enviada depois da verificação no ingresso.
        if not ctx.get("telefone_compartilhado_apto") or ctx["telefone_compartilhado_apto"] != prova:
            raise ValueError("Prova conflitante ou sem autorização no ingresso")
        phone = ctx["central"]["phone_number_id"]
        if etapa == ETAPA_CPF:
            texto = montar_mensagem_etapa2(nome, contato_confirmado=True)
            envio = enviar_texto_pos_venda(prova, phone, texto, etapa)
        else:
            senders = {ETAPA_NOME: enviar_etapa1, ETAPA_PRODUTO: enviar_etapa3,
                       ETAPA_ASSUNTO: enviar_etapa4, ETAPA_PEDIDOS: enviar_etapa5_pedidos,
                        ETAPA_DETALHES: enviar_etapa6_detalhes}
            from core.integrations.whatsapp.pywa_functions.cliente import usar_prefixo_mensagem_bot
            with usar_prefixo_mensagem_bot("Obrigado por compartilhar seu contato!"):
                envio = senders[etapa](prova, phone)
        return dict(envio, operacao_contato="confirmar", bsuid_contato=uid, telefone_provado=prova,
                    tipo_destinatario="wa_id", valor_destinatario=prova)
    if acao == "repetir_botao":
        return pedir(ctx, etapa, nome, repetir=True)
    destino = resolver_destino_transicao(ctx, acao, destinos_esperados={ETAPA_ENCAMINHAMENTO})
    envio = enviar_encaminhamento(ctx, acao)
    envio["operacao_contato"] = "encerrar"
    return anexar_transicao_ao_contexto_envio(ctx, envio, acao, destino)
