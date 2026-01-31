from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("recuperar/", views.recuperar, name="recuperar"),
    path("cliente/", views.cliente, name="cliente"),
    path("recarga/", views.recarga, name="recarga"),
    path("vendedor/", views.vendedor, name="vendedor"),
    path("cuenta/", views.mi_cuenta, name="mi_cuenta"),
    path("cuenta/tarjetas/", views.mi_cuenta_tarjetas, name="mi_cuenta_tarjetas"),
    path("cuenta/tarjetas/editar/", views.mi_cuenta_tarjeta_editar, name="mi_cuenta_tarjeta_editar"),
    path("cuenta/resumen/", views.mi_cuenta_resumen, name="mi_cuenta_resumen"),
    path("cliente-app/", views.cliente_web_app, name="cliente_web_app"),
]
