"""Consultas paginadas de tabelas com chave composta, no contexto da central ou conversa."""
import logging
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html_join

from core.integrations.whatsapp.tools.usuarios import desbloquear_usuario_meta
from . import models

logger = logging.getLogger(__name__)


class VincularUsuarioForm(forms.Form):
    usuario = forms.ModelChoiceField(
        queryset=get_user_model().objects.filter(is_active=True, is_staff=False, is_superuser=False).order_by("username"),
        label="Usuário do painel",
        help_text="O painel de atendimento aceita contas comuns com uma única central ativa.",
    )


class ConsultasRelacionadasMixin:
    # Cada consulta tem modelo, campos de exibição e ordem estável de paginação.
    consultas = {}
    campo_vinculo = None

    def get_urls(self):
        return [path("<int:pk>/consultas/<slug:tipo>/", self.admin_site.admin_view(self.consultar),
                     name=self._nome_url())] + super().get_urls()

    def _nome_url(self):
        return f"{self.opts.app_label}_{self.opts.model_name}_consultar"

    def consultas_do_registro(self, obj):
        if obj is None or obj.pk is None:
            return "Disponíveis após o cadastro."
        return format_html_join(" · ", '<a href="{}">{}</a>', (
            (reverse(f"{self.admin_site.name}:{self._nome_url()}", args=(obj.pk, tipo)),
             registro._meta.verbose_name.capitalize())
            for tipo, (registro, _, _) in self.consultas.items()
        ))

    consultas_do_registro.short_description = "Consultas vinculadas"

    def consultar(self, request, pk, tipo):
        obj = get_object_or_404(self.get_queryset(request), pk=pk)
        if tipo not in self.consultas:
            raise Http404
        modelo, campos, ordem = self.consultas[tipo]
        if not self.has_view_permission(request, obj) or not request.user.has_perm(
            f"webhook.view_{modelo._meta.model_name}"
        ):
            raise PermissionDenied
        registros = modelo.objects.filter(**{self.campo_vinculo: obj})
        acessos = modelo is models.MonitoramentoAcesso
        bloqueios = modelo is models.ClienteBloqueadoMeta
        pode_vincular = acessos and request.user.has_perm("webhook.add_monitoramentoacesso")
        pode_remover = acessos and request.user.has_perm("webhook.delete_monitoramentoacesso")
        pode_desbloquear = bloqueios and request.user.has_perm("webhook.delete_clientebloqueadometa")
        form = VincularUsuarioForm() if pode_vincular else None

        if request.method == "POST":
            acao = request.POST.get("acao")
            if acao == "vincular" and pode_vincular:
                form = VincularUsuarioForm(request.POST)
                if form.is_valid():
                    with transaction.atomic():
                        usuario = get_user_model().objects.select_for_update().get(pk=form.cleaned_data["usuario"].pk)
                        outra_ativa = models.MonitoramentoAcesso.objects.filter(usuario=usuario, central__ativa=True).exclude(central=obj)
                        if obj.ativa and outra_ativa.exists():
                            form.add_error("usuario", "Remova o vínculo com a outra central ativa antes de transferir o acesso.")
                        else:
                            _, criado = registros.get_or_create(central=obj, usuario=usuario)
                            messages.success(request, "Vínculo salvo." if criado else "Esse usuário já está vinculado.")
                            return HttpResponseRedirect(request.path)
            elif acao == "remover" and pode_remover:
                chave = request.POST.get("chave", "")
                if not chave.isascii() or not chave.isdecimal():
                    raise Http404
                usuario = get_object_or_404(registros, usuario_id=chave)
                usuario.delete()
                messages.success(request, "Acesso removido.")
                return HttpResponseRedirect(request.path)
            elif acao == "desbloquear" and pode_desbloquear:
                with transaction.atomic():
                    bloqueio = get_object_or_404(registros.select_for_update(), wa_id_cliente=request.POST.get("chave"))
                    try:
                        desbloquear_usuario_meta(bloqueio.wa_id_cliente, obj.phone_number_id)
                    except Exception:
                        logger.exception("admin_desbloqueio_meta_sem_confirmacao | central=%s", obj.pk)
                        messages.error(request, "A Meta não confirmou o desbloqueio. O registro foi mantido.")
                    else:
                        models.Conversa.objects.filter(central=obj, status_ativa=True,
                            chat__cliente__waid_telefone=bloqueio.wa_id_cliente).update(turnos_sem_avanco=0)
                        bloqueio.delete()
                        messages.success(request, "Desbloqueio confirmado pela Meta.")
                return HttpResponseRedirect(request.path)
            else:
                raise PermissionDenied
        elif request.method != "GET":
            return HttpResponseNotAllowed(["GET", "POST"])

        pagina = Paginator(registros.order_by(*ordem).values_list(*campos), 50).get_page(request.GET.get("p"))
        return TemplateResponse(request, "admin/webhook/consultas.html", {
            **self.admin_site.each_context(request), "opts": self.opts, "original": obj,
            "voltar": reverse(f"{self.admin_site.name}:{self.opts.app_label}_{self.opts.model_name}_change", args=(pk,)),
            "title": modelo._meta.verbose_name.capitalize(), "pagina": pagina,
            "colunas": [campo.replace("__", " · ").replace("_", " ").capitalize() for campo in campos],
            "form": form, "pode_remover": pode_remover, "pode_desbloquear": pode_desbloquear,
        })
