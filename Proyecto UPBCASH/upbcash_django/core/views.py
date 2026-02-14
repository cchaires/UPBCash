import re
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import (
    CartItem,
    FoodItem,
    Purchase,
    PurchaseItem,
    Recharge,
    RechargeIssue,
    UserProfile,
    Wallet,
    WalletLedger,
)

DEFAULT_FOOD_ITEMS = [
    {
        "code": "tacos",
        "name": "Tacos al pastor",
        "description": "Orden con pina, cilantro y cebolla.",
        "price": Decimal("45.00"),
        "photo_variant": "taco",
        "stall_label": "Puesto A-10",
    },
    {
        "code": "cafe",
        "name": "Cafe de olla",
        "description": "Canela y piloncillo, 12 oz.",
        "price": Decimal("28.00"),
        "photo_variant": "cafe",
        "stall_label": "Kiosko central",
    },
    {
        "code": "agua",
        "name": "Agua de jamaica",
        "description": "Recien preparada, 16 oz.",
        "price": Decimal("22.00"),
        "photo_variant": "agua",
        "stall_label": "Puesto B-12",
    },
    {
        "code": "postre",
        "name": "Cheesecake fresa",
        "description": "Rebanada individual, cremosa.",
        "price": Decimal("38.00"),
        "photo_variant": "postre",
        "stall_label": "Puesto C-05",
    },
]


def _wallet_for(user):
    wallet, _ = Wallet.objects.get_or_create(user=user)
    return wallet


def _parse_amount(raw_value):
    digits = re.sub(r"\D", "", raw_value or "")
    if not digits:
        return Decimal("0")
    try:
        return Decimal(digits)
    except InvalidOperation:
        return Decimal("0")


def _authenticate_by_identifier(request, identifier, password):
    if not identifier or not password:
        return None

    user_by_email = User.objects.filter(email__iexact=identifier).first()
    user_by_username = User.objects.filter(username__iexact=identifier).first()
    user_obj = user_by_email or user_by_username

    username_for_auth = user_obj.username if user_obj else identifier
    return authenticate(request, username=username_for_auth, password=password)


def _build_identifier(*candidates):
    for value in candidates:
        cleaned = (value or "").strip()
        if cleaned:
            return cleaned
    return ""


def _create_profile_and_wallet(
    user,
    account_type,
    matricula="",
    phone="",
    invited_by_email="",
    invited_by_matricula="",
):
    UserProfile.objects.create(
        user=user,
        account_type=account_type,
        matricula=matricula,
        phone=phone,
        invited_by_email=invited_by_email,
        invited_by_matricula=invited_by_matricula,
    )
    _wallet_for(user)


def _append_wallet_ledger(
    *,
    wallet,
    user,
    movement_type,
    amount,
    balance_before,
    balance_after,
    reference_type="",
    reference_id="",
    description="",
):
    WalletLedger.objects.create(
        wallet=wallet,
        user=user,
        movement_type=movement_type,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_type=reference_type,
        reference_id=reference_id,
        description=description,
    )


def _ensure_food_catalog():
    for item in DEFAULT_FOOD_ITEMS:
        FoodItem.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "price": item["price"],
                "photo_variant": item["photo_variant"],
                "stall_label": item["stall_label"],
                "is_active": True,
            },
        )


def _cart_queryset(user):
    return CartItem.objects.filter(user=user).select_related("food_item")


def _cart_total(cart_items):
    total = Decimal("0")
    for cart_item in cart_items:
        total += cart_item.food_item.price * cart_item.quantity
    return total


def _cart_rows(cart_items):
    rows = []
    for cart_item in cart_items:
        line_total = cart_item.food_item.price * cart_item.quantity
        rows.append(
            {
                "code": cart_item.food_item.code,
                "name": cart_item.food_item.name,
                "quantity": cart_item.quantity,
                "unit_price": cart_item.food_item.price,
                "line_total": line_total,
            }
        )
    return rows


def index(request):
    if request.user.is_authenticated:
        return redirect("cliente")

    error_message = ""

    if request.method == "POST":
        identifier = request.POST.get("identifier", "").strip()
        password = request.POST.get("password", "")

        user = _authenticate_by_identifier(request, identifier, password)
        if user:
            login(request, user)
            _wallet_for(user)
            return redirect("cliente")
        error_message = "Credenciales invalidas."

    return render(request, "core/index.html", {"error_message": error_message})


def logout_view(request):
    logout(request)
    return redirect("index")


def recuperar(request):
    return render(request, "core/recuperar.html")


def registro(request):
    if request.user.is_authenticated:
        return redirect("cliente")

    error_message = ""

    if request.method == "POST":
        tipo = request.POST.get("tipo", "comunidad")
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")

        if not password or password != password_confirm:
            error_message = "Las contrasenas no coinciden."
        else:
            if tipo == "comunidad":
                matricula = request.POST.get("upbc_matricula", "").strip()
                correo = request.POST.get("upbc_correo", "").strip().lower()
                telefono = request.POST.get("upbc_telefono", "").strip()

                identifier = _build_identifier(matricula, correo)
                if not identifier:
                    error_message = "Debes ingresar matricula o correo institucional."
                else:
                    username = identifier
                    email = correo
                    invited_by_email = ""
                    invited_by_matricula = ""
                    account_type = "comunidad"
            else:
                correo = request.POST.get("inv_correo", "").strip().lower()
                telefono = request.POST.get("inv_telefono", "").strip()
                invitador_correo = request.POST.get("inv_anfitrion_correo", "").strip().lower()
                invitador_matricula = request.POST.get("inv_anfitrion_matricula", "").strip()

                if not correo:
                    error_message = "Debes ingresar correo personal."
                elif not invitador_correo and not invitador_matricula:
                    error_message = "Debes registrar correo o matricula del invitador."
                else:
                    username = correo
                    email = correo
                    matricula = ""
                    invited_by_email = invitador_correo
                    invited_by_matricula = invitador_matricula
                    account_type = "invitado"

            if not error_message:
                if User.objects.filter(username__iexact=username).exists():
                    error_message = "Ese usuario ya existe."
                elif email and User.objects.filter(email__iexact=email).exists():
                    error_message = "Ese correo ya esta registrado."
                else:
                    try:
                        user = User.objects.create_user(
                            username=username,
                            email=email,
                            password=password,
                        )
                    except IntegrityError:
                        error_message = "No se pudo crear la cuenta."
                    else:
                        _create_profile_and_wallet(
                            user=user,
                            account_type=account_type,
                            matricula=matricula,
                            phone=telefono,
                            invited_by_email=invited_by_email,
                            invited_by_matricula=invited_by_matricula,
                        )
                        login(request, user)
                        return redirect("cliente")

    return render(request, "core/registro.html", {"error_message": error_message})


def registro_invitado(request):
    if request.user.is_authenticated:
        return redirect("cliente")

    error_message = ""

    if request.method == "POST":
        correo = request.POST.get("inv_correo", "").strip().lower()
        nombres = request.POST.get("inv_nombres", "").strip()
        apellidos = request.POST.get("inv_apellidos", "").strip()
        telefono = request.POST.get("inv_telefono", "").strip()
        invitador_correo = request.POST.get("inv_anfitrion_correo", "").strip().lower()
        invitador_matricula = request.POST.get("inv_anfitrion_matricula", "").strip()

        if not correo or not nombres or not apellidos:
            error_message = "Completa correo, nombres y apellidos."
        elif not invitador_correo and not invitador_matricula:
            error_message = "Debes ingresar correo o matricula del invitador."
        elif User.objects.filter(username__iexact=correo).exists() or User.objects.filter(email__iexact=correo).exists():
            error_message = "Ese correo ya esta registrado."
        else:
            random_password = User.objects.make_random_password()
            user = User.objects.create_user(
                username=correo,
                email=correo,
                password=random_password,
                first_name=nombres,
                last_name=apellidos,
            )
            _create_profile_and_wallet(
                user=user,
                account_type="invitado",
                matricula="",
                phone=telefono,
                invited_by_email=invitador_correo,
                invited_by_matricula=invitador_matricula,
            )
            login(request, user)
            return redirect("cliente")

    return render(request, "core/registro_invitado.html", {"error_message": error_message})


@login_required(login_url="index")
def cliente(request):
    saldo_actual = _wallet_for(request.user).balance
    return render(request, "core/cliente.html", {"saldo_actual": saldo_actual})


@login_required(login_url="index")
def menu_alimentos(request):
    _ensure_food_catalog()

    if request.method == "POST":
        item_code = request.POST.get("item_code", "").strip().lower()
        action = request.POST.get("action", "add")
        food_item = FoodItem.objects.filter(code=item_code, is_active=True).first()

        if not food_item:
            messages.error(request, "El producto no esta disponible.")
            return redirect("menu_alimentos")

        cart_item, created = CartItem.objects.get_or_create(
            user=request.user,
            food_item=food_item,
            defaults={"quantity": 1},
        )
        if not created:
            cart_item.quantity += 1
            cart_item.save(update_fields=["quantity", "updated_at"])

        messages.success(request, f"{food_item.name} agregado al carrito.")
        if action == "buy":
            return redirect(f"{reverse('carrito_cliente')}?pay=1")
        return redirect("menu_alimentos")

    menu_items = FoodItem.objects.filter(is_active=True).order_by("id")
    cart_count = (
        CartItem.objects.filter(user=request.user).aggregate(total_qty=Sum("quantity"))["total_qty"] or 0
    )
    return render(
        request,
        "core/menu_alimentos.html",
        {
            "menu_items": menu_items,
            "cart_count": cart_count,
        },
    )


@login_required(login_url="index")
def carrito_cliente(request):
    wallet = _wallet_for(request.user)

    if request.method == "POST":
        action = request.POST.get("action", "").strip().lower()

        if action == "remove":
            item_code = request.POST.get("item_code", "").strip().lower()
            deleted, _ = CartItem.objects.filter(user=request.user, food_item__code=item_code).delete()
            if deleted:
                messages.success(request, "Producto eliminado del carrito.")
            else:
                messages.error(request, "No se encontro el producto en el carrito.")
            return redirect("carrito_cliente")

        if action == "clear":
            deleted, _ = CartItem.objects.filter(user=request.user).delete()
            if deleted:
                messages.success(request, "Carrito limpiado.")
            else:
                messages.error(request, "No hay productos en el carrito.")
            return redirect("carrito_cliente")

        if action == "pay":
            cart_items = list(_cart_queryset(request.user))
            total = _cart_total(cart_items)

            if not cart_items:
                messages.error(request, "No hay productos en el carrito.")
                return redirect("carrito_cliente")

            with transaction.atomic():
                locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                if locked_wallet.balance < total:
                    faltante = total - locked_wallet.balance
                    messages.error(request, f"Saldo insuficiente. Te faltan ${faltante:.2f}.")
                    return redirect("carrito_cliente")

                purchase = Purchase.objects.create(user=request.user, total=total)
                purchase_items = [
                    PurchaseItem(
                        purchase=purchase,
                        food_code=cart_item.food_item.code,
                        food_name=cart_item.food_item.name,
                        unit_price=cart_item.food_item.price,
                        quantity=cart_item.quantity,
                        stall_label=cart_item.food_item.stall_label,
                    )
                    for cart_item in cart_items
                ]
                PurchaseItem.objects.bulk_create(purchase_items)

                balance_before = locked_wallet.balance
                locked_wallet.balance = balance_before - total
                locked_wallet.save(update_fields=["balance", "updated_at"])
                _append_wallet_ledger(
                    wallet=locked_wallet,
                    user=request.user,
                    movement_type="purchase",
                    amount=-total,
                    balance_before=balance_before,
                    balance_after=locked_wallet.balance,
                    reference_type="purchase",
                    reference_id=str(purchase.id),
                    description="Pago de carrito de compras",
                )

                CartItem.objects.filter(user=request.user).delete()

            messages.success(request, f"Compra realizada por ${total:.2f}.")
            return redirect("historial_compras")

        messages.error(request, "Accion no valida para el carrito.")
        return redirect("carrito_cliente")

    cart_items = list(_cart_queryset(request.user))
    total = _cart_total(cart_items)
    cart_rows = _cart_rows(cart_items)

    return render(
        request,
        "core/carrito_cliente.html",
        {
            "saldo_actual": wallet.balance,
            "cart_rows": cart_rows,
            "cart_total": total,
            "auto_pay_hint": request.GET.get("pay") == "1",
        },
    )


@login_required(login_url="index")
def cliente_mapa(request):
    return render(request, "core/cliente_mapa.html")


@login_required(login_url="index")
def historial_compras(request):
    purchase_items = (
        PurchaseItem.objects.filter(purchase__user=request.user)
        .select_related("purchase")
        .order_by("-purchase__created_at", "id")
    )
    return render(
        request,
        "core/historial_compras.html",
        {
            "purchase_items": purchase_items,
        },
    )


@login_required(login_url="index")
def historial_recargas(request):
    recargas = Recharge.objects.filter(user=request.user).order_by("-created_at")
    return render(
        request,
        "core/historial_recargas.html",
        {
            "recargas": recargas,
        },
    )


@login_required(login_url="index")
def reporte_recarga(request, recarga_id):
    recarga = get_object_or_404(Recharge, code=recarga_id.upper(), user=request.user)
    error_message = ""

    if request.method == "POST":
        email = request.POST.get("recarga_correo", "").strip().lower()
        motivo = request.POST.get("recarga_motivo", "").strip()
        detalle = request.POST.get("recarga_detalle", "").strip()

        if not email or not motivo or not detalle:
            error_message = "Completa correo, motivo y descripcion del problema."
        else:
            RechargeIssue.objects.create(
                recharge=recarga,
                user=request.user,
                email=email,
                reason=motivo,
                description=detalle,
            )
            messages.success(request, f"Reporte enviado para la recarga {recarga.code}.")
            return redirect("historial_recargas")

    return render(
        request,
        "core/reporte_recarga.html",
        {
            "recarga": recarga,
            "error_message": error_message,
        },
    )


@login_required(login_url="index")
def recarga(request):
    wallet = _wallet_for(request.user)
    error_message = ""

    if request.method == "POST":
        amount = _parse_amount(request.POST.get("amount", ""))
        card_raw = request.POST.get("card", "")
        card_digits = re.sub(r"\D", "", card_raw)
        last4 = card_digits[-4:] if card_digits else ""
        card_label = f"Tarjeta **** {last4}" if last4 else "Tarjeta"

        if amount <= 0:
            error_message = "Ingresa un monto valido para recargar."
        else:
            with transaction.atomic():
                locked_wallet = Wallet.objects.select_for_update().get(pk=wallet.pk)
                recharge = Recharge.objects.create(
                    user=request.user,
                    amount=amount,
                    payment_method="PayPal",
                    card_label=card_label,
                    status="success",
                )
                balance_before = locked_wallet.balance
                locked_wallet.balance = balance_before + amount
                locked_wallet.save(update_fields=["balance", "updated_at"])
                _append_wallet_ledger(
                    wallet=locked_wallet,
                    user=request.user,
                    movement_type="recharge",
                    amount=amount,
                    balance_before=balance_before,
                    balance_after=locked_wallet.balance,
                    reference_type="recharge",
                    reference_id=recharge.code,
                    description="Recarga de saldo",
                )
            messages.success(request, f"Recarga aplicada correctamente ({recharge.code}).")
            return redirect("recarga")

    return render(
        request,
        "core/recarga.html",
        {
            "saldo_actual": wallet.balance,
            "error_message": error_message,
        },
    )


@login_required(login_url="index")
def vendedor(request):
    return render(request, "core/vendedor.html")


@login_required(login_url="index")
def vendedor_productos(request):
    return render(request, "core/vendedor_productos.html")


@login_required(login_url="index")
def vendedor_ventas(request):
    return render(request, "core/vendedor_ventas.html")


@login_required(login_url="index")
def vendedor_mapa(request):
    return render(request, "core/vendedor_mapa.html")


@login_required(login_url="index")
def admin_inicio(request):
    return render(request, "core/admin_inicio.html")


@login_required(login_url="index")
def admin_mapa(request):
    return render(request, "core/admin_mapa.html")


@login_required(login_url="index")
def mi_cuenta(request):
    return render(request, "core/mi_cuenta.html")


@login_required(login_url="index")
def mi_cuenta_tarjetas(request):
    return render(request, "core/mi_cuenta_tarjetas.html")


@login_required(login_url="index")
def mi_cuenta_tarjeta_editar(request):
    return render(request, "core/mi_cuenta_tarjeta_editar.html")


@login_required(login_url="index")
def mi_cuenta_resumen(request):
    return render(request, "core/mi_cuenta_resumen.html")


@login_required(login_url="index")
def cliente_web_app(request):
    saldo_actual = _wallet_for(request.user).balance
    return render(request, "core/cliente_web_app.html", {"saldo_actual": saldo_actual})
