"""Envia a lista de assuntos; não interpreta nem persiste a escolha."""

from pywa.types import Section, SectionList, SectionRow
from core.integrations.whatsapp.messages.tratamentos.midia import avisar_sobre_midia
from core.etapas_pos_venda import ETAPA_ASSUNTO
from core.integrations.whatsapp.messages.etapa4_messages import (
    MENSAGEM_ASSUNTO, MENSAGEM_ASSUNTO_INVALIDO, OPCOES_ASSUNTO,
)
from .texto_pos_venda import enviar_texto_pos_venda


def enviar_etapa4(cliente_telefone, phone_id_unidade, *, invalido=False, midia=False):
    lista = SectionList(button_title="Escolher assunto", sections=[Section(
        title="Assunto do atendimento",
        rows=[SectionRow(title=titulo, callback_data=f"assunto:{valor}", description=descricao)
              for titulo, valor, descricao in OPCOES_ASSUNTO],
    )])
    mensagem = MENSAGEM_ASSUNTO_INVALIDO if invalido else MENSAGEM_ASSUNTO
    envio = enviar_texto_pos_venda(
        cliente_telefone, phone_id_unidade,
        avisar_sobre_midia(mensagem) if midia else mensagem,
        ETAPA_ASSUNTO, botoes=lista,
    )
    if invalido:
        envio.update(tratamento=True, tipo_tratamento="assunto_invalido")
    return envio
