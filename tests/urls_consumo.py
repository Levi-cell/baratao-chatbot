"""URLs de testes locais, sem inicializar o webhook de produção."""
from django.urls import include, path

urlpatterns = [path("", include("monitoramento.urls"))]
