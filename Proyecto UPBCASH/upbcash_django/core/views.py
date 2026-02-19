import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from accounting.services import WalletService
from commerce.models import CartItem as CommerceCartItem
from commerce.models import OrderStatus, SalesOrder
from commerce.services import CheckoutService
from events.models import EventMembership, EventUserGroup, ProfileType
from events.services import ensure_user_client_membership, get_active_event, user_has_group
from operations.models import StaffAuditLog
from operations.services import StaffOpsService, StaffPermissionError
from stalls.models import (
    CatalogProduct,
    ItemNature,
    MapSpot,
    MapSpotStatus,
    ProductCategory,
    ProductSubcategory,
    Stall,
    StallAssignment,
    StallProduct,
    StallStatus,
    StockMode,
)

from .models import (
    Recharge,
    RechargeIssue,
    UserProfile,
    Wallet,
    WalletLedger,
)

logger = logging.getLogger(__name__)

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
    profile_type = ProfileType.COMUNIDAD if account_type == "comunidad" else ProfileType.INVITADO
    ensure_user_client_membership(
        user=user,
        profile_type=profile_type,
        matricula=matricula,
        phone=phone,
        invited_by_email=invited_by_email,
        invited_by_matricula=invited_by_matricula,
    )


def _sync_legacy_wallet_balance_to_v2(*, user, legacy_balance):
    event = get_active_event()
    if not event:
        return
    WalletService.set_balance(event=event, user=user, balance=legacy_balance)


def _sync_legacy_recharge_to_v2(*, user, recharge, amount):
    event = get_active_event()
    if not event:
        return
    WalletService.record_online_topup(
        event=event,
        user=user,
        amount_ucoin=amount,
        provider=recharge.payment_method or "PayPal",
        provider_ref=recharge.code,
        source_reference=f"legacy_recharge:{recharge.id}",
    )


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
            ensure_user_client_membership(user=user)
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


def _parse_ucoin(raw_value):
    value = (raw_value or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return None
    if amount < 0:
        return None
    return amount.quantize(Decimal("0.01"))


def _menu_filter_querystring(request):
    allowed_keys = ["category", "subcategory", "item_nature"]
    payload = {}
    for key in allowed_keys:
        value = (request.POST.get(key) or request.GET.get(key) or "").strip()
        if value:
            payload[key] = value
    return urlencode(payload)


def _menu_product_is_available(product):
    if not product.is_active or product.is_sold_out_manual:
        return False
    if product.item_nature == ItemNature.NO_INVENTORIABLE:
        return True
    if product.stock_mode == StockMode.UNLIMITED:
        return True
    return (product.stock_qty or 0) > 0


def _fallback_image_for_product(product):
    if product.subcategory and product.subcategory.default_image:
        return static(product.subcategory.default_image)
    if product.category and product.category.slug == "bebida":
        return static("core/img/products/default-bebida.svg")
    if product.category and product.category.slug == "servicio":
        return static("core/img/products/default-servicio.svg")
    return static("core/img/products/default-alimento.svg")


def _menu_photo_variant(product):
    if product.subcategory and product.subcategory.default_photo_variant:
        return _safe_photo_variant(product.subcategory.default_photo_variant)
    if product.catalog_product and product.catalog_product.photo_variant:
        return _safe_photo_variant(product.catalog_product.photo_variant)
    return "combo"


def _menu_catalog_queryset(event):
    if not event:
        return StallProduct.objects.none()
    return (
        StallProduct.objects.select_related("stall", "catalog_product", "category", "subcategory")
        .filter(event=event, is_active=True, stall__status=StallStatus.OPEN)
        .order_by("stall__name", "display_name", "id")
    )


@login_required(login_url="index")
def menu_alimentos(request):
    event = _active_event_with_membership(request.user)
    if not event:
        messages.error(request, "No hay un evento activo para mostrar el menu.")
        return render(
            request,
            "core/menu_alimentos.html",
            {
                "menu_stalls": [],
                "cart_count": 0,
                "category_options": [],
                "subcategory_options": [],
                "selected_category": "",
                "selected_subcategory": "",
                "selected_item_nature": "",
                "item_nature_options": ItemNature.choices,
            },
        )

    category_slug = (request.GET.get("category") or "").strip()
    subcategory_slug = (request.GET.get("subcategory") or "").strip()
    item_nature = (request.GET.get("item_nature") or "").strip()

    if request.method == "POST":
        action = request.POST.get("action", "add")
        stall_product_id = request.POST.get("stall_product_id")
        product_qs = _menu_catalog_queryset(event).filter(id=stall_product_id)
        stall_product = product_qs.first()
        if not stall_product or not _menu_product_is_available(stall_product):
            messages.error(request, "El producto no esta disponible.")
            return redirect("menu_alimentos")

        existing_stall_id = (
            CommerceCartItem.objects.filter(event=event, user=request.user)
            .values_list("stall_product__stall_id", flat=True)
            .first()
        )
        if existing_stall_id and existing_stall_id != stall_product.stall_id:
            messages.error(request, "Tu carrito ya tiene productos de otro puesto. Finaliza o limpia el carrito primero.")
            return redirect("carrito_cliente")

        cart_item, created = CommerceCartItem.objects.get_or_create(
            event=event,
            user=request.user,
            stall_product=stall_product,
            defaults={"quantity": 1},
        )
        if not created:
            cart_item.quantity += 1
            cart_item.save(update_fields=["quantity", "updated_at"])

        messages.success(request, f"{stall_product.display_name} agregado al carrito.")
        if action == "buy":
            return redirect(f"{reverse('carrito_cliente')}?pay=1")
        query_string = _menu_filter_querystring(request)
        redirect_url = reverse("menu_alimentos")
        if query_string:
            redirect_url = f"{redirect_url}?{query_string}"
        return redirect(redirect_url)

    menu_qs = _menu_catalog_queryset(event)
    if category_slug:
        menu_qs = menu_qs.filter(category__slug=category_slug)
    if subcategory_slug:
        menu_qs = menu_qs.filter(subcategory__slug=subcategory_slug)
    if item_nature in {ItemNature.INVENTORIABLE, ItemNature.NO_INVENTORIABLE}:
        menu_qs = menu_qs.filter(item_nature=item_nature)

    category_options = ProductCategory.objects.filter(is_active=True).order_by("sort_order", "name")
    subcategory_options = ProductSubcategory.objects.filter(is_active=True).order_by("category__sort_order", "sort_order")
    if category_slug:
        subcategory_options = subcategory_options.filter(category__slug=category_slug)

    menu_stalls = []
    current_stall = None
    for product in menu_qs:
        if not _menu_product_is_available(product):
            continue
        if current_stall is None or current_stall["stall_id"] != product.stall_id:
            current_stall = {"stall_id": product.stall_id, "stall_name": product.stall.name, "items": []}
            menu_stalls.append(current_stall)

        image_url = product.image.url if product.image else _fallback_image_for_product(product)
        current_stall["items"].append(
            {
                "id": product.id,
                "name": product.display_name,
                "description": product.catalog_product.description or "",
                "price": product.price_ucoin,
                "photo_variant": _menu_photo_variant(product),
                "image_url": image_url,
                "category_name": product.category.name if product.category else "",
                "subcategory_name": product.subcategory.name if product.subcategory else "",
                "item_nature_label": product.get_item_nature_display(),
                "is_low_stock": bool(product.is_low_stock),
            }
        )

    cart_count = (
        CommerceCartItem.objects.filter(event=event, user=request.user).aggregate(total_qty=Sum("quantity"))["total_qty"]
        or 0
    )
    return render(
        request,
        "core/menu_alimentos.html",
        {
            "menu_stalls": menu_stalls,
            "cart_count": cart_count,
            "category_options": category_options,
            "subcategory_options": subcategory_options,
            "selected_category": category_slug,
            "selected_subcategory": subcategory_slug,
            "selected_item_nature": item_nature,
            "item_nature_options": ItemNature.choices,
        },
    )


@login_required(login_url="index")
def carrito_cliente(request):
    event = _active_event_with_membership(request.user)
    if not event:
        messages.error(request, "No hay evento activo para operar el carrito.")
        return redirect("menu_alimentos")
    saldo_actual = WalletService.get_balance(event=event, user=request.user)

    if request.method == "POST":
        action = request.POST.get("action", "").strip().lower()

        if action == "remove":
            stall_product_id = request.POST.get("stall_product_id", "").strip()
            deleted, _ = CommerceCartItem.objects.filter(
                event=event,
                user=request.user,
                stall_product_id=stall_product_id,
            ).delete()
            if deleted:
                messages.success(request, "Producto eliminado del carrito.")
            else:
                messages.error(request, "No se encontro el producto en el carrito.")
            return redirect("carrito_cliente")

        if action == "clear":
            deleted, _ = CommerceCartItem.objects.filter(event=event, user=request.user).delete()
            if deleted:
                messages.success(request, "Carrito limpiado.")
            else:
                messages.error(request, "No hay productos en el carrito.")
            return redirect("carrito_cliente")

        if action == "pay":
            try:
                order, _raw_qr = CheckoutService.checkout_cart(event=event, user=request.user)
                messages.success(request, f"Compra realizada por ${order.total_ucoin:.2f}. Ticket #{order.order_number}.")
                return redirect("historial_compras")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
                return redirect("carrito_cliente")

        messages.error(request, "Accion no valida para el carrito.")
        return redirect("carrito_cliente")

    cart_items = list(
        CommerceCartItem.objects.select_related("stall_product", "stall_product__stall")
        .filter(event=event, user=request.user)
        .order_by("-updated_at", "-id")
    )
    cart_rows = []
    total = Decimal("0.00")
    for item in cart_items:
        line_total = (item.stall_product.price_ucoin * item.quantity).quantize(Decimal("0.01"))
        total += line_total
        cart_rows.append(
            {
                "stall_product_id": item.stall_product_id,
                "stall_name": item.stall_product.stall.name,
                "name": item.stall_product.display_name,
                "quantity": item.quantity,
                "unit_price": item.stall_product.price_ucoin,
                "line_total": line_total,
            }
        )

    return render(
        request,
        "core/carrito_cliente.html",
        {
            "saldo_actual": saldo_actual,
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
    event = _active_event_with_membership(request.user)
    order_items_qs = (
        SalesOrder.objects.filter(buyer_user=request.user)
        .prefetch_related("items")
        .select_related("stall")
        .order_by("-created_at", "-id")
    )
    if event:
        order_items_qs = order_items_qs.filter(event=event)

    purchase_rows = []
    for order in order_items_qs:
        for item in order.items.all():
            purchase_rows.append(
                {
                    "created_at": order.created_at,
                    "stall_name": order.stall.name,
                    "product_name": item.product_name_snapshot,
                    "quantity": item.quantity,
                    "unit_price": item.unit_price_snapshot,
                    "line_total": item.line_total_snapshot,
                    "status": order.get_status_display(),
                }
            )

    return render(
        request,
        "core/historial_compras.html",
        {
            "purchase_rows": purchase_rows,
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
            try:
                _sync_legacy_recharge_to_v2(
                    user=request.user,
                    recharge=recharge,
                    amount=amount,
                )
                _sync_legacy_wallet_balance_to_v2(user=request.user, legacy_balance=locked_wallet.balance)
            except Exception as exc:  # noqa: BLE001
                logger.exception("No se pudo sincronizar recarga legacy hacia esquema v2: %s", exc)
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


def _user_display_name(user):
    full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return full_name or user.username


def _active_event_with_membership(user):
    event = get_active_event()
    if event:
        ensure_user_client_membership(user=user, event=event)
    return event


def _has_event_group(*, event, user, group_name):
    if not event:
        return False
    return user_has_group(event=event, user=user, group_name=group_name)


def _redirect_if_no_vendor_role(request, *, event):
    if _has_event_group(event=event, user=request.user, group_name="vendedor"):
        return None
    if _has_event_group(event=event, user=request.user, group_name="staff"):
        messages.error(request, "No cuentas con rol vendedor para este evento. Te redirigimos al panel staff.")
        return redirect("staff_panel")
    messages.error(request, "Solo perfiles vendedor pueden acceder a este panel.")
    return redirect("cliente")


def _redirect_if_no_staff_role(request, *, event):
    if _has_event_group(event=event, user=request.user, group_name="staff"):
        return None
    messages.error(request, "Solo personal staff puede acceder a este panel.")
    return redirect("cliente")


def _vendor_assignment(event, user):
    if not event:
        return None
    return (
        StallAssignment.objects.select_related("stall", "spot", "spot__zone")
        .filter(event=event, vendor_user=user)
        .first()
    )


def _safe_photo_variant(raw_value):
    allowed = {"taco", "cafe", "agua", "postre", "ensalada", "combo"}
    return raw_value if raw_value in allowed else "combo"


def _status_card_for_product(product):
    if not product.is_active:
        return "Inactivo", "Off"
    if product.is_sold_out_manual:
        return "Agotado", "Manual"
    if product.item_nature == ItemNature.NO_INVENTORIABLE:
        return "Disponible", "Servicio"
    if product.stock_mode == StockMode.UNLIMITED:
        return "Disponible", "Ilimitado"
    qty = product.stock_qty or 0
    if qty <= 0:
        return "Agotado", "Sin stock"
    if product.is_low_stock:
        return "Proximo a agotarse", "15%"
    return "Disponible", "OK"


def _vendor_products_for_stall(event, stall):
    if not event or not stall:
        return []

    products = (
        StallProduct.objects.select_related("catalog_product", "category", "subcategory")
        .filter(event=event, stall=stall)
        .order_by("display_name", "id")
    )
    rows = []
    for product in products:
        availability_label, badge_label = _status_card_for_product(product)
        if product.item_nature == ItemNature.NO_INVENTORIABLE:
            stock_text = "No aplica"
        else:
            stock_text = "Ilimitado" if product.stock_mode == StockMode.UNLIMITED else str(product.stock_qty or 0)
        image_url = product.image.url if product.image else _fallback_image_for_product(product)
        rows.append(
            {
                "id": product.id,
                "name": product.display_name,
                "price": product.price_ucoin,
                "cost": product.cost_ucoin,
                "stock_text": stock_text,
                "availability_label": availability_label,
                "badge_label": badge_label,
                "photo_variant": _menu_photo_variant(product),
                "image_url": image_url,
                "category_name": product.category.name if product.category else "",
                "subcategory_name": product.subcategory.name if product.subcategory else "",
                "item_nature": product.get_item_nature_display(),
                "is_active": product.is_active,
                "is_low_stock": bool(product.is_low_stock),
            }
        )
    return rows


def _build_catalog_sku(event, stall, display_name):
    # CatalogProduct.sku allows 32 chars max; keep it deterministic and short.
    compact_slug = (slugify(display_name).replace("-", "")[:8] or "producto")
    suffix = timezone.now().strftime("%H%M%S%f")[:8]
    return f"e{event.id}s{stall.id}{suffix}{compact_slug}"[:32]


@login_required(login_url="index")
def vendedor(request):
    event = _active_event_with_membership(request.user)
    role_redirect = _redirect_if_no_vendor_role(request, event=event)
    if role_redirect:
        return role_redirect
    assignment = _vendor_assignment(event, request.user)
    stall = assignment.stall if assignment else None
    today = timezone.localdate()

    sales_qs = SalesOrder.objects.none()
    if event and stall:
        sales_qs = SalesOrder.objects.filter(event=event, stall=stall).prefetch_related("items")

    today_metrics = sales_qs.filter(created_at__date=today).aggregate(
        total=Sum("total_ucoin"),
        total_orders=Count("id"),
    )
    pending_orders = sales_qs.filter(
        status__in=[
            OrderStatus.PAID,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.PARTIALLY_DELIVERED,
        ]
    ).count()
    low_stock_count = StallProduct.objects.filter(
        event=event,
        stall=stall,
        is_active=True,
        is_sold_out_manual=False,
        item_nature=ItemNature.INVENTORIABLE,
        stock_mode=StockMode.FINITE,
        low_stock_threshold__isnull=False,
        stock_qty__gt=0,
        stock_qty__lte=F("low_stock_threshold"),
    ).count() if event and stall else 0

    latest_orders = list(sales_qs.order_by("-created_at", "-id")[:3])
    latest_sales = []
    for order in latest_orders:
        first_item = order.items.first()
        item_name = first_item.product_name_snapshot if first_item else "Orden sin detalle"
        extra_items = max(order.items.count() - 1, 0)
        suffix = f" +{extra_items} mas" if extra_items else ""
        latest_sales.append(
            {
                "title": f"{item_name}{suffix}",
                "description": f"{timezone.localtime(order.created_at):%d %b · Ticket #{order.order_number}}",
                "total": order.total_ucoin,
            }
        )

    context = {
        "user_display_name": _user_display_name(request.user),
        "event": event,
        "assignment": assignment,
        "today_sales_total": today_metrics["total"] or Decimal("0.00"),
        "today_sales_count": today_metrics["total_orders"] or 0,
        "pending_orders": pending_orders,
        "low_stock_count": low_stock_count,
        "latest_sales": latest_sales,
    }
    return render(request, "core/vendedor.html", context)


@login_required(login_url="index")
def vendedor_productos(request):
    event = _active_event_with_membership(request.user)
    role_redirect = _redirect_if_no_vendor_role(request, event=event)
    if role_redirect:
        return role_redirect
    assignment = _vendor_assignment(event, request.user)
    stall = assignment.stall if assignment else None
    category_options = ProductCategory.objects.filter(is_active=True).order_by("sort_order", "name")
    subcategory_options = ProductSubcategory.objects.filter(is_active=True).order_by("category__sort_order", "sort_order")
    edit_id = request.GET.get("edit", "").strip()
    edit_product = None

    if event and stall and edit_id.isdigit():
        edit_product = (
            StallProduct.objects.select_related("catalog_product", "category", "subcategory")
            .filter(event=event, stall=stall, id=int(edit_id))
            .first()
        )

    if request.method == "POST":
        if not event or not stall:
            messages.error(request, "Necesitas un evento activo y un puesto asignado para administrar productos.")
            return redirect("vendedor_productos")

        action = request.POST.get("action", "save_product")
        if action != "save_product":
            messages.error(request, "Accion no valida para productos.")
            return redirect("vendedor_productos")

        product_id = (request.POST.get("product_id") or "").strip()
        target_product = None
        if product_id.isdigit():
            target_product = (
                StallProduct.objects.select_related("catalog_product")
                .filter(event=event, stall=stall, id=int(product_id))
                .first()
            )
            if not target_product:
                messages.error(request, "El producto a editar no fue encontrado.")
                return redirect("vendedor_productos")

        display_name = (request.POST.get("display_name") or "").strip()
        description = (request.POST.get("description") or "").strip()
        item_nature = (request.POST.get("item_nature") or ItemNature.INVENTORIABLE).strip()
        category_id = (request.POST.get("category_id") or "").strip()
        subcategory_id = (request.POST.get("subcategory_id") or "").strip()
        price_ucoin = _parse_ucoin(request.POST.get("price_ucoin"))
        cost_ucoin = _parse_ucoin(request.POST.get("cost_ucoin"))
        stock_qty_raw = (request.POST.get("stock_qty") or "").strip()
        is_active = request.POST.get("is_active") == "on"
        remove_image = request.POST.get("remove_image") == "on"
        image_file = request.FILES.get("image")

        if not display_name:
            messages.error(request, "Ingresa el nombre del producto.")
            return redirect("vendedor_productos")
        if item_nature not in {ItemNature.INVENTORIABLE, ItemNature.NO_INVENTORIABLE}:
            messages.error(request, "Selecciona un tipo de item valido.")
            return redirect("vendedor_productos")
        if price_ucoin is None:
            messages.error(request, "Ingresa un precio valido.")
            return redirect("vendedor_productos")
        if cost_ucoin is None:
            messages.error(request, "Ingresa un costo valido.")
            return redirect("vendedor_productos")

        category = ProductCategory.objects.filter(id=category_id, is_active=True).first()
        subcategory = ProductSubcategory.objects.filter(id=subcategory_id, is_active=True).first()
        if not category or not subcategory:
            messages.error(request, "Selecciona categoria y subcategoria.")
            return redirect("vendedor_productos")
        if subcategory.category_id != category.id:
            messages.error(request, "La subcategoria no corresponde con la categoria seleccionada.")
            return redirect("vendedor_productos")

        stock_qty = None
        if item_nature == ItemNature.INVENTORIABLE:
            if stock_qty_raw:
                if not stock_qty_raw.isdigit():
                    messages.error(request, "El stock debe ser un numero entero.")
                    return redirect("vendedor_productos")
                stock_qty = int(stock_qty_raw)
            elif not target_product:
                messages.error(request, "El stock inicial es obligatorio para productos inventariables.")
                return redirect("vendedor_productos")

            if not target_product and (stock_qty is None or stock_qty <= 0):
                messages.error(request, "El stock inicial debe ser mayor a 0.")
                return redirect("vendedor_productos")

        if cost_ucoin > price_ucoin:
            messages.warning(request, "Advertencia: el costo unitario es mayor al precio de venta.")

        if target_product:
            catalog_product = target_product.catalog_product
        else:
            catalog_product = CatalogProduct.objects.create(
                sku=_build_catalog_sku(event, stall, display_name),
                name=display_name,
                description=description,
                photo_variant=_safe_photo_variant(subcategory.default_photo_variant),
                is_active=True,
            )
            target_product = StallProduct(
                event=event,
                stall=stall,
                catalog_product=catalog_product,
            )

        catalog_product.name = display_name
        catalog_product.description = description
        catalog_product.photo_variant = _safe_photo_variant(subcategory.default_photo_variant)
        catalog_product.is_active = is_active
        catalog_product.save(update_fields=["name", "description", "photo_variant", "is_active"])

        target_product.display_name = display_name
        target_product.item_nature = item_nature
        target_product.category = category
        target_product.subcategory = subcategory
        target_product.price_ucoin = price_ucoin
        target_product.cost_ucoin = cost_ucoin
        target_product.is_active = is_active
        if stock_qty is not None:
            target_product.stock_qty = stock_qty
        if image_file:
            target_product.image = image_file
        elif remove_image and target_product.image:
            target_product.image.delete(save=False)
            target_product.image = None
        target_product.save()

        messages.success(
            request,
            "Producto actualizado correctamente." if product_id.isdigit() else "Producto creado correctamente.",
        )
        return redirect("vendedor_productos")

    form_product = edit_product
    selected_category_id = str(form_product.category_id) if form_product and form_product.category_id else ""
    selected_subcategory_id = str(form_product.subcategory_id) if form_product and form_product.subcategory_id else ""
    selected_item_nature = form_product.item_nature if form_product else ItemNature.INVENTORIABLE

    context = {
        "user_display_name": _user_display_name(request.user),
        "event": event,
        "assignment": assignment,
        "stall_products": _vendor_products_for_stall(event, stall),
        "category_options": category_options,
        "subcategory_options": subcategory_options,
        "item_nature_options": ItemNature.choices,
        "form_product": form_product,
        "selected_category_id": selected_category_id,
        "selected_subcategory_id": selected_subcategory_id,
        "selected_item_nature": selected_item_nature,
    }
    return render(request, "core/vendedor_productos.html", context)


@login_required(login_url="index")
def vendedor_ventas(request):
    event = _active_event_with_membership(request.user)
    role_redirect = _redirect_if_no_vendor_role(request, event=event)
    if role_redirect:
        return role_redirect
    assignment = _vendor_assignment(event, request.user)
    stall = assignment.stall if assignment else None
    sales_qs = SalesOrder.objects.none()
    if event and stall:
        sales_qs = SalesOrder.objects.filter(event=event, stall=stall).prefetch_related("items")

    sales_rows = []
    for order in sales_qs.order_by("-created_at", "-id")[:24]:
        qty = sum(item.quantity for item in order.items.all())
        sales_rows.append(
            {
                "order_number": order.order_number,
                "status": order.get_status_display(),
                "created_at": timezone.localtime(order.created_at),
                "quantity": qty,
                "total": order.total_ucoin,
            }
        )

    context = {
        "user_display_name": _user_display_name(request.user),
        "event": event,
        "assignment": assignment,
        "sales_rows": sales_rows,
    }
    return render(request, "core/vendedor_ventas.html", context)


@login_required(login_url="index")
def vendedor_mapa(request):
    event = _active_event_with_membership(request.user)
    role_redirect = _redirect_if_no_vendor_role(request, event=event)
    if role_redirect:
        return role_redirect

    assignment = _vendor_assignment(event, request.user)
    return render(
        request,
        "core/vendedor_mapa.html",
        {
            "user_display_name": _user_display_name(request.user),
            "event": event,
            "assignment": assignment,
        },
    )


def _staff_panel_redirect(request):
    query_string = (request.POST.get("next_query") or "").strip()
    target = reverse("staff_panel")
    if query_string:
        target = f"{target}?{query_string}"
    return redirect(target)


@login_required(login_url="index")
def staff_panel(request):
    event = _active_event_with_membership(request.user)
    if not event:
        messages.error(request, "No hay un evento activo para administrar roles.")
        return redirect("cliente")

    role_redirect = _redirect_if_no_staff_role(request, event=event)
    if role_redirect:
        return role_redirect

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if action in {"grant_role", "revoke_role"}:
            target_user_id = (request.POST.get("target_user_id") or "").strip()
            group_name = (request.POST.get("group_name") or "").strip()
            if not target_user_id.isdigit():
                messages.error(request, "Selecciona un usuario valido.")
                return _staff_panel_redirect(request)

            target_membership = (
                EventMembership.objects.select_related("user")
                .filter(event=event, user_id=int(target_user_id))
                .first()
            )
            if not target_membership:
                messages.error(request, "El usuario no pertenece al evento activo.")
                return _staff_panel_redirect(request)

            try:
                if action == "grant_role":
                    _assignment, created = StaffOpsService.grant_role(
                        event=event,
                        staff_user=request.user,
                        target_user=target_membership.user,
                        group_name=group_name,
                    )
                    if created:
                        messages.success(request, f"Rol {group_name} asignado correctamente.")
                    else:
                        messages.info(request, f"El usuario ya cuenta con el rol {group_name}.")
                else:
                    removed = StaffOpsService.revoke_role(
                        event=event,
                        staff_user=request.user,
                        target_user=target_membership.user,
                        group_name=group_name,
                    )
                    if removed:
                        messages.success(request, f"Rol {group_name} revocado correctamente.")
                    else:
                        messages.info(request, f"El usuario no tenia el rol {group_name}.")
            except (StaffPermissionError, ValueError) as exc:
                messages.error(request, str(exc))
            return _staff_panel_redirect(request)

        if action == "assign_vendor":
            vendor_user_id = (request.POST.get("vendor_user_id") or "").strip()
            stall_id = (request.POST.get("stall_id") or "").strip()
            spot_id = (request.POST.get("spot_id") or "").strip()

            if not (vendor_user_id.isdigit() and stall_id.isdigit() and spot_id.isdigit()):
                messages.error(request, "Selecciona vendedor, puesto y espacio.")
                return _staff_panel_redirect(request)

            vendor_membership = (
                EventMembership.objects.select_related("user")
                .filter(event=event, user_id=int(vendor_user_id))
                .first()
            )
            stall = Stall.objects.filter(event=event, id=int(stall_id)).first()
            spot = MapSpot.objects.filter(event=event, id=int(spot_id)).first()
            if not vendor_membership or not stall or not spot:
                messages.error(request, "Los datos de asignacion no son validos para el evento activo.")
                return _staff_panel_redirect(request)
            if spot.status == MapSpotStatus.BLOCKED:
                messages.error(request, "El espacio seleccionado esta bloqueado.")
                return _staff_panel_redirect(request)
            spot_taken = (
                StallAssignment.objects.filter(event=event, spot=spot)
                .exclude(vendor_user=vendor_membership.user)
                .exists()
            )
            if spot_taken:
                messages.error(request, "El espacio seleccionado ya esta asignado a otro vendedor.")
                return _staff_panel_redirect(request)

            try:
                StaffOpsService.assign_vendor(
                    event=event,
                    staff_user=request.user,
                    vendor_user=vendor_membership.user,
                    stall=stall,
                    spot=spot,
                )
                messages.success(request, "Asignacion vendedor->puesto->espacio actualizada.")
            except Exception as exc:  # noqa: BLE001
                messages.error(request, str(exc))
            return _staff_panel_redirect(request)

        messages.error(request, "Accion no valida en panel staff.")
        return _staff_panel_redirect(request)

    search_query = (request.GET.get("q") or "").strip()
    memberships_qs = EventMembership.objects.select_related("user").filter(event=event).order_by("user__username", "id")
    if search_query:
        memberships_qs = memberships_qs.filter(
            Q(user__username__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(matricula__icontains=search_query)
        )
    memberships = list(memberships_qs[:100])
    user_ids = [membership.user_id for membership in memberships]

    groups_by_user = defaultdict(set)
    if user_ids:
        for row in EventUserGroup.objects.filter(
            event=event,
            user_id__in=user_ids,
            group__name__in=["vendedor", "staff"],
        ).select_related("group"):
            groups_by_user[row.user_id].add(row.group.name)

    assignments_by_user = {}
    if user_ids:
        for assignment in StallAssignment.objects.select_related("stall", "spot", "spot__zone").filter(
            event=event,
            vendor_user_id__in=user_ids,
        ):
            assignments_by_user[assignment.vendor_user_id] = assignment

    user_rows = []
    for membership in memberships:
        groups = groups_by_user.get(membership.user_id, set())
        assignment = assignments_by_user.get(membership.user_id)
        user_rows.append(
            {
                "membership": membership,
                "is_staff": "staff" in groups,
                "is_vendor": "vendedor" in groups,
                "assignment": assignment,
            }
        )

    stalls = list(Stall.objects.filter(event=event).order_by("name", "id"))
    spots = list(
        MapSpot.objects.select_related("zone")
        .filter(event=event)
        .exclude(status=MapSpotStatus.BLOCKED)
        .order_by("zone__sort_order", "label", "id")
    )
    assignments = list(
        StallAssignment.objects.select_related("stall", "spot", "spot__zone", "vendor_user")
        .filter(event=event)
        .order_by("stall__name", "id")
    )
    spot_taken_by = {assignment.spot_id: _user_display_name(assignment.vendor_user) for assignment in assignments}
    spot_rows = [
        {
            "spot": spot,
            "is_taken": spot.id in spot_taken_by,
            "taken_by": spot_taken_by.get(spot.id, ""),
        }
        for spot in spots
    ]

    audit_logs = list(
        StaffAuditLog.objects.select_related("staff_user")
        .filter(event=event)
        .order_by("-created_at", "-id")[:25]
    )

    context = {
        "user_display_name": _user_display_name(request.user),
        "event": event,
        "search_query": search_query,
        "current_query_string": request.GET.urlencode(),
        "user_rows": user_rows,
        "assignment_candidates": EventMembership.objects.select_related("user")
        .filter(event=event)
        .order_by("user__username", "id")[:200],
        "stalls": stalls,
        "spot_rows": spot_rows,
        "assignments": assignments,
        "audit_logs": audit_logs,
        "total_users": EventMembership.objects.filter(event=event).count(),
        "total_staff": (
            EventUserGroup.objects.filter(event=event, group__name="staff").values("user_id").distinct().count()
        ),
        "total_vendors": (
            EventUserGroup.objects.filter(event=event, group__name="vendedor").values("user_id").distinct().count()
        ),
        "total_assignments": StallAssignment.objects.filter(event=event).count(),
    }
    return render(request, "core/staff_panel.html", context)


@login_required(login_url="index")
def admin_inicio(request):
    event = _active_event_with_membership(request.user)
    orders_qs = SalesOrder.objects.none()
    stalls_qs = Stall.objects.none()
    if event:
        orders_qs = SalesOrder.objects.filter(event=event)
        stalls_qs = Stall.objects.filter(event=event)

    total_sales = (
        orders_qs.exclude(status=OrderStatus.CANCELLED).aggregate(total=Sum("total_ucoin")).get("total")
        or Decimal("0.00")
    )
    active_buyers = orders_qs.values("buyer_user_id").distinct().count()
    stalls_operating = stalls_qs.filter(status=StallStatus.OPEN).count()
    low_stock_alerts = StallProduct.objects.filter(
        event=event,
        is_active=True,
        is_sold_out_manual=False,
        item_nature=ItemNature.INVENTORIABLE,
        stock_mode=StockMode.FINITE,
        low_stock_threshold__isnull=False,
        stock_qty__gt=0,
        stock_qty__lte=F("low_stock_threshold"),
    ).count() if event else 0

    context = {
        "user_display_name": _user_display_name(request.user),
        "event": event,
        "total_sales": total_sales,
        "active_buyers": active_buyers,
        "stalls_operating": stalls_operating,
        "low_stock_alerts": low_stock_alerts,
    }
    return render(request, "core/admin_inicio.html", context)


@login_required(login_url="index")
def admin_mapa(request):
    event = _active_event_with_membership(request.user)
    assignment_rows = []
    if event:
        assignment_rows = list(
            StallAssignment.objects.select_related("stall", "vendor_user", "spot", "spot__zone")
            .filter(event=event)
            .order_by("stall__name")
        )

    spot_status_counts = {"available": 0, "assigned": 0, "blocked": 0}
    if event:
        for row in (
            MapSpot.objects.filter(event=event)
            .values("status")
            .annotate(total=Count("id"))
        ):
            spot_status_counts[row["status"]] = row["total"]

    context = {
        "user_display_name": _user_display_name(request.user),
        "event": event,
        "assignment_rows": assignment_rows,
        "available_spots": spot_status_counts.get(MapSpotStatus.AVAILABLE, 0),
        "assigned_spots": spot_status_counts.get(MapSpotStatus.ASSIGNED, 0),
        "blocked_spots": spot_status_counts.get(MapSpotStatus.BLOCKED, 0),
    }
    return render(request, "core/admin_mapa.html", context)


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
