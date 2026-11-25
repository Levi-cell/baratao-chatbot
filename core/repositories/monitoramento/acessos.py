"""Consulta autoritativa do vínculo usuário/central; sem escopo vindo do navegador."""

from dataclasses import dataclass


@dataclass(frozen=True)
class AcessoMonitoramento:
    id_usuario: int
    id_central: int
    nome_central: str

    # Compatibilidade temporária do restante do painel ainda em adaptação.
    @property
    def id_unidade(self):
        return self.id_central

    @property
    def nome_unidade(self):
        return self.nome_central


def buscar_acesso_monitoramento(
    id_usuario,
    cursor,
    *,
    id_conversa=None,
    id_mensagem=None,
):
    """Lê o vínculo ativo em monitoramento_acesso e autoriza os recursos.

    A identidade vem da sessao Django, nunca do corpo/URL da requisicao.
    Mensagens são autorizadas pela central da conversa, não pelo cliente global.
    Quando conversa e mensagem sao informadas, ambas devem pertencer ao mesmo
    atendimento. Nao ha bypass para contas administrativas nem cache do vinculo.
    """
    identificadores = (id_usuario, id_conversa, id_mensagem)
    if id_usuario is None or any(
        valor is not None and (type(valor) is not int or valor <= 0)
        for valor in identificadores
    ):
        return None

    consulta = """
        WITH vinculos AS (
            SELECT usuario.id, central.id_central, central.nome, count(*) OVER () AS quantidade
            FROM chatbot.monitoramento_acesso acesso
            JOIN chatbot.auth_user usuario ON usuario.id = acesso.id_usuario_django
            JOIN chatbot.central_pos_venda central ON central.id_central = acesso.id_central
            WHERE usuario.id = %s AND usuario.is_active IS TRUE
              AND usuario.is_staff IS FALSE AND usuario.is_superuser IS FALSE
              AND central.ativa IS TRUE
        )
        SELECT u.id, u.id_central, u.nome FROM vinculos u
        WHERE u.quantidade = 1
    """
    parametros = [id_usuario]

    if id_conversa is not None:
        consulta += """
          AND EXISTS (
              SELECT 1 FROM chatbot.conversa AS c
              WHERE c.id_conversa = %s AND c.id_central = u.id_central
          )
        """
        parametros.append(id_conversa)

    if id_mensagem is not None:
        consulta += """
          AND EXISTS (
              SELECT 1
              FROM chatbot.historico_mensagens AS h
              JOIN chatbot.conversa AS c ON c.id_conversa = h.id_conversa
              WHERE h.id_mensagem = %s AND c.id_central = u.id_central
        """
        parametros.append(id_mensagem)
        if id_conversa is not None:
            consulta += " AND h.id_conversa = %s"
            parametros.append(id_conversa)
        consulta += " )"

    cursor.execute(consulta, tuple(parametros))
    linha = cursor.fetchone()
    return AcessoMonitoramento(*linha) if linha else None
