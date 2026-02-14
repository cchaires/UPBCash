from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("logout/", views.logout_view, name="logout"),
    path("recuperar/", views.recuperar, name="recuperar"),
    path("registro/", views.registro, name="registro"),
    path("registro/invitado/", views.registro_invitado, name="registro_invitado"),
    path("cliente/", views.cliente, name="cliente"),
    path("cliente/menu/", views.menu_alimentos, name="menu_alimentos"),
    path("cliente/carrito/", views.carrito_cliente, name="carrito_cliente"),
    path("cliente/mapa/", views.cliente_mapa, name="cliente_mapa"),
    path("cliente/historial-compras/", views.historial_compras, name="historial_compras"),
    path("cliente/historial-recargas/", views.historial_recargas, name="historial_recargas"),
    path("cliente/historial-recargas/reporte/<str:recarga_id>/", views.reporte_recarga, name="reporte_recarga"),
    path("recarga/", views.recarga, name="recarga"),
    path("vendedor/", views.vendedor, name="vendedor"),
    path("vendedor/productos/", views.vendedor_productos, name="vendedor_productos"),
    path("vendedor/ventas/", views.vendedor_ventas, name="vendedor_ventas"),
    path("vendedor/mapa/", views.vendedor_mapa, name="vendedor_mapa"),
    path("administrador/", views.admin_inicio, name="admin_inicio"),
    path("administrador/mapa/", views.admin_mapa, name="admin_mapa"),
    path("cuenta/", views.mi_cuenta, name="mi_cuenta"),
    path("cuenta/tarjetas/", views.mi_cuenta_tarjetas, name="mi_cuenta_tarjetas"),
    path("cuenta/tarjetas/editar/", views.mi_cuenta_tarjeta_editar, name="mi_cuenta_tarjeta_editar"),
    path("cuenta/resumen/", views.mi_cuenta_resumen, name="mi_cuenta_resumen"),
    path("cliente-app/", views.cliente_web_app, name="cliente_web_app"),
]
