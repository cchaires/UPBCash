from dataclasses import dataclass, field

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect

from .services import (
    get_active_campaign,
    is_campaign_open,
    is_public_event_open,
    sync_auth_profile_groups_for_event,
)

PERM_ACCESS_CLIENTE_PORTAL = "events.access_cliente_portal"
PERM_CHECKOUT_CART = "events.checkout_cart"
PERM_ACCESS_VENDEDOR_PORTAL = "events.access_vendedor_portal"
PERM_MANAGE_VENDOR_PRODUCTS = "events.manage_vendor_products"
PERM_SOFT_DELETE_VENDOR_PRODUCTS = "events.soft_delete_vendor_products"
PERM_MANAGE_VENDOR_STALL_IMAGE = "events.manage_vendor_stall_image"
PERM_VERIFY_ORDER_QR = "events.verify_order_qr"
PERM_ACCESS_STAFF_PANEL = "events.access_staff_panel"
PERM_MANAGE_EVENT_PROFILES = "events.manage_event_profiles"
PERM_ASSIGN_VENDOR_STALL = "events.assign_vendor_stall"
PERM_GRANT_UCOINS = "events.grant_ucoins"


@dataclass
class AuthzSnapshot:
    event: object | None
    profile_names: set[str] = field(default_factory=set)
    is_superuser: bool = False
    can_bypass_event_lock: bool = False
    is_campaign_open: bool = False
    is_public_open: bool = False
    is_event_locked: bool = False


def build_authz_snapshot(*, user, event=None, sync_groups=True):
    resolved_event = event or get_active_campaign()
    if not user or not user.is_authenticated:
        return AuthzSnapshot(event=resolved_event)

    profile_names = set()
    if sync_groups:
        profile_names = sync_auth_profile_groups_for_event(user=user, event=resolved_event)

    is_superuser = bool(user.is_superuser)
    can_bypass_event_lock = is_superuser or ("staff" in profile_names)
    campaign_open = is_campaign_open(resolved_event)
    public_open = is_public_event_open(resolved_event)
    is_event_locked = (not campaign_open) and not can_bypass_event_lock
    return AuthzSnapshot(
        event=resolved_event,
        profile_names=profile_names,
        is_superuser=is_superuser,
        can_bypass_event_lock=can_bypass_event_lock,
        is_campaign_open=campaign_open,
        is_public_open=public_open,
        is_event_locked=is_event_locked,
    )


def has_permission(*, user, permission, snapshot=None):
    current_snapshot = snapshot or build_authz_snapshot(user=user)
    if not user or not user.is_authenticated:
        return False
    if current_snapshot.is_superuser:
        return True
    return bool(user.has_perm(permission))


def has_any_permission(*, user, permissions, snapshot=None):
    return any(has_permission(user=user, permission=permission, snapshot=snapshot) for permission in permissions)


def enforce_event_lock_web(
    *,
    request,
    snapshot,
    redirect_name="index",
    message="No hay un evento activo. El acceso estara disponible al iniciar un nuevo evento.",
):
    if not snapshot.is_event_locked:
        return None
    messages.error(request, message)
    return redirect(redirect_name)


def enforce_campaign_window_web(
    *,
    request,
    snapshot,
    redirect_name="index",
    message="La ventana de campaña no esta activa para esta operacion.",
):
    if snapshot.is_campaign_open or snapshot.is_superuser:
        return None
    messages.error(request, message)
    return redirect(redirect_name)


def enforce_public_window_web(
    *,
    request,
    snapshot,
    redirect_name="index",
    message="La ventana publica del evento no esta activa.",
):
    if snapshot.is_public_open or snapshot.is_superuser:
        return None
    messages.error(request, message)
    return redirect(redirect_name)


def enforce_permission_web(
    *,
    request,
    permission,
    snapshot,
    denied_redirect_name="cliente",
    denied_message="No cuentas con permisos para esta accion.",
):
    lock_redirect = enforce_event_lock_web(request=request, snapshot=snapshot)
    if lock_redirect:
        return lock_redirect
    if has_permission(user=request.user, permission=permission, snapshot=snapshot):
        return None
    messages.error(request, denied_message)
    return redirect(denied_redirect_name)


def enforce_any_permission_web(
    *,
    request,
    permissions,
    snapshot,
    denied_redirect_name="cliente",
    denied_message="No cuentas con permisos para esta accion.",
):
    lock_redirect = enforce_event_lock_web(request=request, snapshot=snapshot)
    if lock_redirect:
        return lock_redirect
    if has_any_permission(user=request.user, permissions=permissions, snapshot=snapshot):
        return None
    messages.error(request, denied_message)
    return redirect(denied_redirect_name)


def enforce_event_lock_api(
    *,
    snapshot,
    message="No hay un evento activo para ejecutar esta operacion.",
):
    if not snapshot.is_event_locked:
        return None
    return JsonResponse({"ok": False, "error": message}, status=403)


def enforce_campaign_window_api(
    *,
    snapshot,
    message="La ventana de campaña no esta activa para esta operacion.",
):
    if snapshot.is_campaign_open or snapshot.is_superuser:
        return None
    return JsonResponse({"ok": False, "error": message}, status=403)


def enforce_public_window_api(
    *,
    snapshot,
    message="La ventana publica del evento no esta activa.",
):
    if snapshot.is_public_open or snapshot.is_superuser:
        return None
    return JsonResponse({"ok": False, "error": message}, status=403)


def enforce_permission_api(
    *,
    request,
    permission,
    snapshot,
    denied_message="No autorizado.",
):
    lock_error = enforce_event_lock_api(snapshot=snapshot)
    if lock_error:
        return lock_error
    if has_permission(user=request.user, permission=permission, snapshot=snapshot):
        return None
    return JsonResponse({"ok": False, "error": denied_message}, status=403)


def enforce_any_permission_api(
    *,
    request,
    permissions,
    snapshot,
    denied_message="No autorizado.",
):
    lock_error = enforce_event_lock_api(snapshot=snapshot)
    if lock_error:
        return lock_error
    if has_any_permission(user=request.user, permissions=permissions, snapshot=snapshot):
        return None
    return JsonResponse({"ok": False, "error": denied_message}, status=403)
