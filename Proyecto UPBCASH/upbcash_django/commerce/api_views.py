import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from events.authz import (
    PERM_ACCESS_STAFF_PANEL,
    PERM_CHECKOUT_CART,
    PERM_VERIFY_ORDER_QR,
    build_authz_snapshot,
    enforce_campaign_window_api,
    enforce_permission_api,
    enforce_public_window_api,
    enforce_any_permission_api,
)
from events.models import EventCampaign
from events.services import ensure_user_client_membership

from .models import SalesOrder
from .services import CheckoutService, FulfillmentService


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


@login_required(login_url="index")
@require_POST
def checkout_cart_api(request, event_id):
    event = EventCampaign.objects.filter(id=event_id).first()
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    snapshot = build_authz_snapshot(user=request.user, event=event)
    auth_error = enforce_permission_api(
        request=request,
        permission=PERM_CHECKOUT_CART,
        snapshot=snapshot,
        denied_message="No cuentas con permisos para ejecutar checkout.",
    )
    if auth_error:
        return auth_error

    public_error = enforce_public_window_api(
        snapshot=snapshot,
        message="La ventana publica del evento no esta activa para checkout.",
    )
    if public_error:
        return public_error

    ensure_user_client_membership(user=request.user, event=event)
    try:
        order, qr_token = CheckoutService.checkout_cart(event=event, user=request.user)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "order": {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "total_ucoin": str(order.total_ucoin),
            },
            "qr_token": qr_token,
        }
    )


@login_required(login_url="index")
@require_POST
def verify_order_qr_api(request, order_id):
    precheck_snapshot = build_authz_snapshot(user=request.user)
    precheck_error = enforce_any_permission_api(
        request=request,
        permissions=[PERM_VERIFY_ORDER_QR, PERM_ACCESS_STAFF_PANEL],
        snapshot=precheck_snapshot,
        denied_message="No cuentas con permisos para verificar entregas por QR.",
    )
    if precheck_error:
        return precheck_error

    order = SalesOrder.objects.select_related("event").filter(id=order_id).first()
    if not order:
        return JsonResponse({"ok": False, "error": "Orden no encontrada."}, status=404)

    snapshot = build_authz_snapshot(user=request.user, event=order.event)
    auth_error = enforce_any_permission_api(
        request=request,
        permissions=[PERM_VERIFY_ORDER_QR, PERM_ACCESS_STAFF_PANEL],
        snapshot=snapshot,
        denied_message="No cuentas con permisos para verificar entregas por QR.",
    )
    if auth_error:
        return auth_error

    campaign_error = enforce_campaign_window_api(
        snapshot=snapshot,
        message="La ventana de campaña no esta activa para verificar QR.",
    )
    if campaign_error:
        return campaign_error

    body = _json_body(request)
    token = (body.get("token") or request.POST.get("token", "")).strip()
    try:
        is_valid = FulfillmentService.verify_qr_and_deliver(order=order, raw_token=token, actor_user=request.user)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": is_valid,
            "order_id": order.id,
            "status": order.status,
            "error": "" if is_valid else "Token invalido o expirado.",
        },
        status=200 if is_valid else 400,
    )
