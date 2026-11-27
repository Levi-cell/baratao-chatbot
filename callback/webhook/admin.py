"""Painel operacional do pós-venda. A fila e o histórico são controlados pelo worker."""
import logging

from django.contrib import admin, messages
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponseRedirect
from django.urls import reverse

from core.cache.cache_unidade import CacheUnidadesIndisponivel, recarregar_cache_unidades_ou_erro
from . import models
from .admin_relacoes import ConsultasRelacionadasMixin
from .forms import CentralPosVendaForm
from .models import CentralPosVenda

logger = logging.getLogger(__name__)


@admin.register(CentralPosVenda)
class CentralPosVendaAdmin(ConsultasRelacionadasMixin, admin.ModelAdmin):
    campo_vinculo = "central"
    consultas = {
        "acessos": (models.MonitoramentoAcesso, ("usuario_id", "usuario__username"), ("usuario_id",)),
        "bloqueios": (models.ClienteBloqueadoMeta, ("wa_id_cliente", "bloqueado_em"), ("wa_id_cliente",)),
        "consumo": (models.ConsumoMensalMeta, ("mes_referencia", "qtd_janela_gratuita", "qtd_franquia_consumida",
                    "qtd_cobradas_meta", "valor_meta", "moeda", "status_apuracao"), ("-mes_referencia",)),
        "coletas": (models.ConsumoMetaColeta, ("periodo", "proxima_consulta_em", "ultima_tentativa_em",
                    "falhas_consecutivas", "ultimo_erro"), ("periodo",)),
        "identidades": (models.IdentidadeBsuid, ("cliente_id", "user_id", "vigente", "suspender_telefone"),
                        ("cliente_id", "user_id")),
    }
    fieldsets = (
        ("Atendimento", {"fields": ("nome", "ativa", "nome_agente", "genero_agente")}),
        ("Remetente no WhatsApp", {"fields": ("telefone", "waba_id", "phone_number_id", "waac_id")}),
        ("Redes de pós-venda", {"fields": ("telefone_baratao", "telefone_atacadao")}),
        ("Monitoramento", {"fields": ("consultas_do_registro", "id_fuso", "nome_fuso", "fuso_verificado_em")}),
    )
    form = CentralPosVendaForm
    list_display = ("nome", "ativa", "telefone", "phone_number_id", "waba_id", "waac_id")
    search_fields = ("nome", "telefone", "phone_number_id", "waba_id", "waac_id")
    list_filter = ("ativa",)
    ordering = ("nome", "id_central")
    readonly_fields = ("consultas_do_registro", "id_fuso", "nome_fuso", "fuso_verificado_em")

    def save_model(self, request, obj, form, change):
        if change:
            # Preserva o fuso sincronizado em paralelo. O trigger central_mudou
            # versiona o cache na própria transação, uma vez por UPDATE.
            obj.save(update_fields=form.changed_data)
        else:
            super().save_model(request, obj, form, change)
        self._sincronizar_apos_commit(request, obj._state.db)

    def delete_model(self, request, obj):
        using = obj._state.db
        super().delete_model(request, obj)
        self._sincronizar_apos_commit(request, using)

    def delete_queryset(self, request, queryset):
        using = queryset.db
        super().delete_queryset(request, queryset)
        self._sincronizar_apos_commit(request, using)

    def _sincronizar_apos_commit(self, request, using):
        # O trigger já versionou o catálogo. Recarregar apenas dados confirmados,
        # inclusive quando o Admin está dentro de uma transação externa.
        def publicar():
            try:
                with connections[using].cursor() as cursor:
                    recarregar_cache_unidades_ou_erro(cursor)
            except (CacheUnidadesIndisponivel, DatabaseError):
                logger.exception("central_confirmada_cache_pendente")
                self.message_user(
                    request, "Alteração salva no banco. A sincronização do cache está pendente.",
                    level=messages.WARNING,
                )

        transaction.on_commit(publicar, using=using)

    def delete_view(self, request, object_id, extra_context=None):
        try:
            return super().delete_view(request, object_id, extra_context)
        except IntegrityError as exc:
            # Um worker pode criar um vínculo após a tela de confirmação.
            if not isinstance(exc, ProtectedError) and getattr(exc.__cause__, "sqlstate", None) != "23503":
                raise
            self.message_user(request, "A central passou a ter registros vinculados. Para suspender o atendimento, desative a central.", messages.ERROR)
            return HttpResponseRedirect(reverse("admin:webhook_centralposvenda_changelist"))

    def changelist_view(self, request, extra_context=None):
        try:
            return super().changelist_view(request, extra_context)
        except IntegrityError as exc:
            vinculado = isinstance(exc, ProtectedError) or getattr(exc.__cause__, "sqlstate", None) == "23503"
            if request.POST.get("action") != "delete_selected" or not vinculado:
                raise
            self.message_user(request, "Uma das centrais passou a ter registros vinculados. Reabra a lista para conferir.", messages.ERROR)
            return HttpResponseRedirect(request.path)


class SomenteConsulta(admin.ModelAdmin):
    list_per_page = 50

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Conversa)
class ConversaAdmin(ConsultasRelacionadasMixin, SomenteConsulta):
    campo_vinculo = "conversa"
    consultas = {
        "pedidos": (models.PedidoConversa, ("numero", "codigo_filial"), ("numero",)),
        "etiquetas": (models.EtiquetaConversa, ("etiqueta",), ("etiqueta",)),
        "recuperacao": (models.FallbackContato, ("mensagem_fila_id", "estado", "atualizado_em", "wamid_original"),
                        ("-atualizado_em", "mensagem_fila_id")),
    }
    readonly_fields = ("consultas_do_registro",)
    list_display = ("id_conversa", "central", "chat_id", "etapa_atual", "status_ativa", "turnos_sem_avanco", "processing", "iniciou_em")
    list_filter = ("central", "status_ativa", "etapa_atual", "processing")
    ordering = ("-id_conversa",)
    search_fields = ("=chat__cliente__waid_telefone", "chat__cliente__nome_titular")


@admin.register(models.Cliente)
class ClienteAdmin(SomenteConsulta):
    list_display = ("id_cliente", "nome_titular", "waid_telefone", "username")
    search_fields = ("nome_titular", "waid_telefone", "username", "=cpf_titular")
    ordering = ("-id_cliente",)


@admin.register(models.Chat)
class ChatAdmin(SomenteConsulta):
    list_display = ("id_chat", "central", "cliente")
    list_filter = ("central",)
    ordering = ("-id_chat",)


@admin.register(models.Etapa)
class EtapaAdmin(SomenteConsulta):
    list_display = ("id_etapa", "nome_etapa", "encerra_automaticamente", "bloqueio_dias")
    ordering = ("id_etapa",)


@admin.register(models.EtapaTransicao)
class TransicaoAdmin(SomenteConsulta):
    list_display = ("origem", "evento", "destino")
    list_filter = ("origem", "destino")
    ordering = ("origem_id", "evento")


@admin.register(models.AtendimentoPosVenda)
class AtendimentoAdmin(SomenteConsulta):
    list_display = ("conversa", "nome_titular", "produto", "assunto", "perdeu_nota")
    list_filter = ("produto", "assunto", "perdeu_nota")
    ordering = ("-conversa_id",)


@admin.register(models.FilaMensagens)
class FilaAdmin(SomenteConsulta):
    list_display = ("id_mensagem", "central", "conversa_id", "tipo_mensagem", "status", "retry_count", "received_data_hora")
    list_filter = ("central", "status", "tipo_mensagem")
    search_fields = ("=id_hash_msg", "=cliente_telefone", "=user_id_origem")
    ordering = ("-id_mensagem",)


@admin.register(models.HistoricoMensagens)
class HistoricoAdmin(SomenteConsulta):
    list_display = ("id_mensagem", "conversa", "etapa", "quem_enviou", "tipo_mensagem", "status_envio", "received_data_hora")
    list_filter = ("quem_enviou", "status_envio", "etapa")
    search_fields = ("=id_hash_msg", "=id_hash_cliente_origem")
    ordering = ("-id_mensagem",)


@admin.register(models.FilialCompra)
class FilialAdmin(SomenteConsulta):
    list_display = ("codigo", "nome", "grupo")
    list_filter = ("grupo",)
    search_fields = ("codigo", "nome")
    ordering = ("codigo",)


@admin.register(models.SolicitacaoContato)
class SolicitacaoAdmin(SomenteConsulta):
    list_display = ("conversa", "motivo", "etapa_retomada", "erros_cliente")


@admin.register(models.WebhookFloodEvento)
class FloodAdmin(SomenteConsulta):
    list_display = ("id_hash_msg", "central", "wa_id_cliente", "received_at")
    list_filter = ("central",)
    ordering = ("-received_at",)


@admin.register(models.CacheControle)
class CacheAdmin(SomenteConsulta):
    list_display = ("nome", "versao", "atualizado_em")


@admin.register(models.ContatoInterno)
class ContatoInternoAdmin(admin.ModelAdmin):
    list_display = ("waid_telefone",)
    search_fields = ("=waid_telefone",)

    def get_readonly_fields(self, request, obj=None):
        # O telefone é a chave. Alterá-lo em uma edição criaria outro registro.
        return ("waid_telefone",) if obj is not None else ()
