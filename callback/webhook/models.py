"""Mapeamento de leitura e administração do schema chatbot, criado pelo DDL do projeto."""
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Right


class CentralPosVenda(models.Model):
    validar_telefone_setor = RegexValidator(
        r"\A[1-9][0-9]{7,14}\Z", "Informe de 8 a 15 dígitos, com DDI e sem zero inicial.",
    )

    id_central = models.AutoField(primary_key=True)
    nome = models.CharField("nome da central")
    nome_agente = models.CharField("nome do agente")
    genero_agente = models.CharField("gênero do agente", choices=[("masculino", "Masculino"), ("feminino", "Feminino")])
    ativa = models.BooleanField(default=True, help_text="Habilita o atendimento desta central.")
    waba_id = models.CharField("WABA ID", help_text="ID da conta empresarial (messaging_account_id).")
    phone_number_id = models.CharField("Phone Number ID", unique=True)
    waac_id = models.CharField(
        "WAAC ID", unique=True, blank=True, null=True,
        validators=[RegexValidator(r"\A[1-9][0-9]*\Z", "Informe um ID numérico positivo, sem zero inicial.")],
        help_text="Informe o ID de conta verificado para este número. Em branco, o envio usa o Phone Number ID.",
    )
    telefone = models.CharField("telefone da central", unique=True)
    telefone_baratao = models.CharField(
        "telefone do pós-venda do Baratão", blank=True, null=True, validators=[validar_telefone_setor],
    )
    telefone_atacadao = models.CharField(
        "telefone do pós-venda do Atacadão", blank=True, null=True, validators=[validar_telefone_setor],
    )
    id_fuso = models.IntegerField("ID do fuso", blank=True, null=True, editable=False)
    nome_fuso = models.TextField("nome do fuso", blank=True, null=True, editable=False)
    fuso_verificado_em = models.DateTimeField("fuso verificado em", blank=True, null=True, editable=False)

    def clean(self):
        super().clean()
        erros = {}
        if self.waac_id and self.waac_id == self.phone_number_id:
            erros["waac_id"] = "O WAAC ID deve ser diferente do Phone Number ID."
        if self.ativa:
            for campo in ("telefone_baratao", "telefone_atacadao"):
                if not getattr(self, campo):
                    erros[campo] = "Informe o telefone desta rede para ativar a central."
        if self.telefone_baratao and self.telefone_baratao == self.telefone_atacadao:
            erros["telefone_atacadao"] = "Informe números diferentes para o Baratão e o Atacadão."
        if erros:
            raise ValidationError(erros)

    def __str__(self):
        return self.nome

    class Meta:
        managed = False
        db_table = "central_pos_venda"
        verbose_name = "central de pós-venda"
        verbose_name_plural = "centrais de pós-venda"



class Cliente(models.Model):
    id_cliente = models.AutoField(primary_key=True)
    waid_telefone = models.CharField(unique=True, blank=True, null=True)
    username = models.TextField(blank=True, null=True)
    username_observado_em = models.DateTimeField(blank=True, null=True)
    nome_titular = models.TextField(blank=True, null=True)
    cpf_titular = models.CharField(max_length=11, blank=True, null=True)
    cidade_loja_compra = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nome_titular or f"Cliente {self.pk}"

    class Meta:
        managed = False
        db_table = "cliente"
        indexes = [models.Index(fields=["cpf_titular", "id_cliente"], name="cliente_cpf_conciliacao",
                                condition=models.Q(cpf_titular__isnull=False))]


class ContatoInterno(models.Model):
    waid_telefone = models.CharField("telefone", primary_key=True)

    class Meta:
        managed = False
        db_table = "contato_interno"
        verbose_name = "contato interno"


class Chat(models.Model):
    id_chat = models.BigAutoField(primary_key=True)
    cliente = models.ForeignKey(Cliente, models.PROTECT, db_column="id_cliente")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")

    class Meta:
        managed = False
        db_table = "chat"
        unique_together = (("cliente", "central"), ("id_chat", "central"))


class Etapa(models.Model):
    id_etapa = models.IntegerField(primary_key=True)
    nome_etapa = models.CharField(max_length=100, unique=True)
    encerra_automaticamente = models.BooleanField(default=False)
    bloqueio_dias = models.SmallIntegerField(default=0)

    def __str__(self):
        return f"{self.pk} · {self.nome_etapa}"

    class Meta:
        managed = False
        db_table = "etapa"


class EtapaTransicao(models.Model):
    id_transicao = models.AutoField(primary_key=True)
    origem = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_origem", related_name="saidas")
    evento = models.CharField(max_length=100)
    destino = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_destino", related_name="entradas")

    class Meta:
        managed = False
        db_table = "etapa_transicao"
        unique_together = (("origem", "evento"),)
        verbose_name = "transição de etapa"
        verbose_name_plural = "mapa de transições"


class Conversa(models.Model):
    id_conversa = models.AutoField(primary_key=True)
    # O SQL garante que a central seja a do chat por uma chave estrangeira composta.
    chat = models.ForeignKey(Chat, models.PROTECT, db_column="id_chat")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central", db_constraint=False)
    etapa_atual = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_atual")
    iniciou_em = models.DateTimeField()
    finalizou_em = models.DateTimeField(null=True)
    status_ativa = models.BooleanField(default=True)
    motivo_encerramento = models.TextField(null=True)
    last_interaction_at = models.DateTimeField(null=True)
    last_message_from = models.CharField(null=True)
    processing = models.BooleanField(default=False)
    processing_started_at = models.DateTimeField(null=True)
    lock_version = models.IntegerField(default=0)
    turnos_sem_avanco = models.IntegerField(default=0)

    def __str__(self):
        return f"Conversa {self.pk}"

    class Meta:
        managed = False
        db_table = "conversa"


class AtendimentoPosVenda(models.Model):
    conversa = models.OneToOneField(Conversa, models.PROTECT, primary_key=True, db_column="id_conversa")
    nome_titular = models.TextField(null=True)
    cpf_titular = models.CharField(max_length=11, null=True)
    cidade_loja_compra = models.TextField(null=True)
    produto = models.TextField(null=True)
    assunto = models.CharField(null=True)
    perdeu_nota = models.BooleanField(null=True)
    foi_a_loja = models.BooleanField(null=True)
    detalhes = models.TextField(null=True)
    encaminhado_baratao = models.CharField(null=True)
    encaminhado_atacadao = models.CharField(null=True)
    telefone_compartilhado = models.CharField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "atendimento_pos_venda"
        verbose_name = "atendimento de pós-venda"


class FilialCompra(models.Model):
    codigo = models.TextField(primary_key=True)
    nome = models.TextField()

    grupo = models.TextField(choices=[("Atacadão", "Atacadão"), ("Baratão", "Baratão")])

    def __str__(self):
        return f"{self.codigo} · {self.nome}"

    class Meta:
        managed = False
        db_table = "filial_compra"
        verbose_name = "filial de compra"
        verbose_name_plural = "filiais de compra"


class PedidoConversa(models.Model):
    pk = models.CompositePrimaryKey("conversa", "numero")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    numero = models.TextField()
    codigo_filial = models.GeneratedField(expression=Right("numero", 2), output_field=models.TextField(), db_persist=True)

    class Meta:
        managed = False
        db_table = "pedido_conversa"
        verbose_name = "pedido da conversa"


class EtiquetaConversa(models.Model):
    pk = models.CompositePrimaryKey("conversa", "etiqueta")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    etiqueta = models.CharField()

    class Meta:
        managed = False
        db_table = "etiqueta_conversa"
        verbose_name = "etiqueta da conversa"


class FilaMensagens(models.Model):
    id_mensagem = models.AutoField(primary_key=True)
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa", null=True)
    cliente = models.ForeignKey(Cliente, models.PROTECT, db_column="id_cliente", null=True)
    cliente_telefone = models.CharField(null=True)
    user_id_origem = models.TextField(null=True)
    username_origem = models.TextField(null=True)
    id_hash_msg = models.CharField(unique=True)
    received_data_hora = models.DateTimeField()
    tipo_mensagem = models.CharField()
    conteudo_texto = models.TextField(null=True)
    interativo = models.JSONField(null=True)
    status = models.CharField(default="pending")
    retry_count = models.IntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    processing_started_at = models.DateTimeField(null=True)
    last_error = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "fila_mensagens"
        verbose_name_plural = "fila de mensagens"


class HistoricoMensagens(models.Model):
    id_mensagem = models.BigAutoField(primary_key=True)
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    etapa = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa")
    received_data_hora = models.DateTimeField()
    quem_enviou = models.CharField()
    id_hash_msg = models.CharField(unique=True)
    mensagem_fila = models.ForeignKey(FilaMensagens, models.SET_NULL, db_column="id_mensagem_fila", null=True)
    id_hash_cliente_origem = models.CharField(null=True)
    parte_resposta = models.SmallIntegerField(default=1)
    tipo_mensagem = models.CharField()
    conteudo_texto = models.TextField(null=True)
    interativo = models.JSONField(null=True)
    tipo_destinatario = models.TextField(null=True)
    valor_destinatario = models.TextField(null=True)
    status_envio = models.CharField(null=True)

    class Meta:
        managed = False
        db_table = "historico_mensagens"
        verbose_name_plural = "histórico de mensagens"


class IdentidadeBsuid(models.Model):
    pk = models.CompositePrimaryKey("central", "user_id")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    user_id = models.TextField()
    cliente = models.ForeignKey(Cliente, models.PROTECT, db_column="id_cliente")
    wamid_origem = models.TextField()
    suspender_telefone = models.BooleanField(default=False)
    vigente = models.BooleanField(default=True)

    class Meta:
        managed = False
        db_table = "identidade_bsuid"
        verbose_name = "identidade por BSUID"


class SolicitacaoContato(models.Model):
    conversa = models.OneToOneField(Conversa, models.PROTECT, db_column="id_conversa", primary_key=True)
    motivo = models.TextField()
    etapa_retomada = models.ForeignKey(Etapa, models.PROTECT, db_column="id_etapa_retomada")
    bsuid_destino = models.TextField()
    wamid_solicitacao = models.TextField()
    wamids_aceitos = ArrayField(models.TextField())
    erros_cliente = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "solicitacao_contato"
        verbose_name = "solicitação de contato"
        verbose_name_plural = "solicitações de contato"


class FallbackContato(models.Model):
    pk = models.CompositePrimaryKey("conversa", "mensagem_fila")
    conversa = models.ForeignKey(Conversa, models.PROTECT, db_column="id_conversa")
    mensagem_fila = models.ForeignKey(FilaMensagens, models.PROTECT, db_column="id_mensagem_fila")
    wamid_original = models.TextField(null=True, unique=True)
    estado = models.TextField()
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "fallback_contato"
        verbose_name = "recuperação de contato"


class CacheControle(models.Model):
    nome = models.CharField(primary_key=True)
    versao = models.BigIntegerField(default=1)
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "cache_controle"
        verbose_name_plural = "versões do cache"


class ClienteBloqueadoMeta(models.Model):
    pk = models.CompositePrimaryKey("central", "wa_id_cliente")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    wa_id_cliente = models.CharField()
    bloqueado_em = models.DateTimeField(null=True)

    class Meta:
        managed = False
        db_table = "cliente_bloqueado_meta"
        verbose_name = "bloqueio na Meta"


class WebhookFloodEvento(models.Model):
    id_hash_msg = models.CharField(primary_key=True)
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    wa_id_cliente = models.CharField()
    received_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "webhook_flood_evento"
        verbose_name_plural = "eventos de proteção contra flood"


class MonitoramentoAcesso(models.Model):
    pk = models.CompositePrimaryKey("usuario", "central")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, models.CASCADE, db_column="id_usuario_django")
    central = models.ForeignKey(CentralPosVenda, models.CASCADE, db_column="id_central")

    class Meta:
        managed = False
        db_table = "monitoramento_acesso"
        verbose_name = "acesso ao monitoramento"


class ConsumoMensalMeta(models.Model):
    pk = models.CompositePrimaryKey("central", "mes_referencia")
    central = models.ForeignKey(CentralPosVenda, models.PROTECT, db_column="id_central")
    mes_referencia = models.DateField()
    waba_id = models.CharField()
    phone_number_id = models.CharField()
    fuso_horario = models.TextField()
    qtd_gratuitas = models.BigIntegerField()
    qtd_cobradas_meta = models.BigIntegerField()
    valor_meta = models.DecimalField(max_digits=14, decimal_places=6, null=True)
    moeda = models.CharField(max_length=3, null=True)
    consultado_ate = models.DateTimeField()
    consolidado_em = models.DateTimeField(null=True)
    timezone_id = models.IntegerField(null=True)
    data_hora_inicio = models.DateTimeField(null=True)
    data_hora_fim = models.DateTimeField(null=True)
    qtd_janela_gratuita = models.BigIntegerField(null=True)
    qtd_franquia_consumida = models.BigIntegerField(null=True)
    ultimo_sucesso_em = models.DateTimeField(null=True)
    status_apuracao = models.TextField(default="pendente_detalhamento")
    data_proxima_consolidacao = models.DateField(null=True)
    ultima_decisao_consolidacao_em = models.DateTimeField(null=True)
    franquia_meta_mensal = models.IntegerField(default=1000)
    beneficio_esl_mensal = models.IntegerField(default=1000)
    tarifa_referencia_brl = models.DecimalField(max_digits=12, decimal_places=6, default="0.035")
    tarifa_vigencia = models.DateField()
    atualizado_em = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "consumo_mensal_meta"
        verbose_name = "consumo mensal da Meta"


class ConsumoMetaColeta(models.Model):
    pk = models.CompositePrimaryKey("central", "periodo")
    central = models.ForeignKey(CentralPosVenda, models.CASCADE, db_column="id_central")
    periodo = models.CharField()
    proxima_consulta_em = models.DateTimeField()
    ultima_tentativa_em = models.DateTimeField(null=True)
    falhas_consecutivas = models.IntegerField(default=0)
    ultimo_erro = models.TextField(null=True)

    class Meta:
        managed = False
        db_table = "consumo_meta_coletas"
        verbose_name = "coleta de consumo"
