from django.shortcuts import render


def index(request):
    return render(request, "core/index.html")


def recuperar(request):
    return render(request, "core/recuperar.html")


def cliente(request):
    return render(request, "core/cliente.html")


def recarga(request):
    return render(request, "core/recarga.html")


def vendedor(request):
    return render(request, "core/vendedor.html")


def mi_cuenta(request):
    return render(request, "core/mi_cuenta.html")


def mi_cuenta_tarjetas(request):
    return render(request, "core/mi_cuenta_tarjetas.html")


def mi_cuenta_tarjeta_editar(request):
    return render(request, "core/mi_cuenta_tarjeta_editar.html")


def mi_cuenta_resumen(request):
    return render(request, "core/mi_cuenta_resumen.html")


def cliente_web_app(request):
    return render(request, "core/cliente_web_app.html")
