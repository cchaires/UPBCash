import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from events.authz import (
    PERM_ASSIGN_VENDOR_STALL,
    PERM_GRANT_UCOINS,
    build_authz_snapshot,
    enforce_campaign_window_api,
    enforce_permission_api,
)
from events.models import EventCampaign, EventMembership
from stalls.models import MapSpot, Stall, StallLocationAssignment

from .services import StaffOpsService


def _json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _load_event(event_id):
    return EventCampaign.objects.filter(id=event_id).first()


def _ensure_staff_ops_auth(request, *, event, denied_message):
    snapshot = build_authz_snapshot(user=request.user, event=event)
    auth_error = enforce_permission_api(
        request=request,
        permission=PERM_ASSIGN_VENDOR_STALL,
        snapshot=snapshot,
        denied_message=denied_message,
    )
    if auth_error:
        return auth_error, snapshot
    campaign_error = enforce_campaign_window_api(
        snapshot=snapshot,
        message="La ventana de campaña no esta activa para esta operacion.",
    )
    if campaign_error:
        return campaign_error, snapshot
    return None, snapshot


def _map_state_payload(event):
    assignments = {
        row.spot_id: row
        for row in StallLocationAssignment.objects.select_related("stall").filter(event=event)
    }

    spots_payload = []
    for spot in MapSpot.objects.select_related("zone").filter(event=event).order_by("label", "id"):
        assignment = assignments.get(spot.id)
        spots_payload.append(
            {
                "id": spot.id,
                "label": spot.label,
                "x": float(spot.x),
                "y": float(spot.y),
                "status": spot.status,
                "zone": spot.zone.name,
                "stall_id": assignment.stall_id if assignment else None,
                "stall_name": assignment.stall.name if assignment else "",
            }
        )

    stalls_payload = []
    stalls_qs = Stall.objects.filter(event=event).order_by("name", "id")
    for stall in stalls_qs:
        members = StaffOpsService.get_stall_memberships(event=event, stall=stall)
        assignment = StaffOpsService.get_stall_location(event=event, stall=stall)
        stalls_payload.append(
            {
                "id": stall.id,
                "name": stall.name,
                "code": stall.code,
                "members": [
                    {
                        "user_id": member.vendor_user_id,
                        "username": member.vendor_user.username,
                        "role": member.role,
                    }
                    for member in members
                ],
                "assigned_spot_id": assignment.spot_id if assignment else None,
                "assigned_spot_label": assignment.spot.label if assignment else "",
            }
        )

    vendor_candidates = (
        EventMembership.objects.select_related("user")
        .filter(event=event)
        .order_by("user__username", "id")
    )
    return {
        "event": {
            "id": event.id,
            "code": event.code,
            "name": event.name,
            "max_map_spots": event.max_map_spots,
            "map_image_url": event.map_image.url if event.map_image else "",
        },
        "spots": spots_payload,
        "stalls": stalls_payload,
        "vendors": [
            {
                "user_id": membership.user_id,
                "username": membership.user.username,
                "matricula": membership.matricula,
            }
            for membership in vendor_candidates
        ],
    }


@login_required(login_url="index")
@require_http_methods(["GET"])
def map_state_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    auth_error, _snapshot = _ensure_staff_ops_auth(
        request,
        event=event,
        denied_message="No cuentas con permisos para consultar el estado del mapa.",
    )
    if auth_error:
        return auth_error

    return JsonResponse({"ok": True, **_map_state_payload(event)})


@login_required(login_url="index")
@require_http_methods(["POST"])
def create_map_spot_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    auth_error, _snapshot = _ensure_staff_ops_auth(
        request,
        event=event,
        denied_message="No cuentas con permisos para crear espacios.",
    )
    if auth_error:
        return auth_error

    body = _json_body(request)
    x = body.get("x") if "x" in body else request.POST.get("x")
    y = body.get("y") if "y" in body else request.POST.get("y")

    try:
        spot = StaffOpsService.create_map_spot(
            event=event,
            staff_user=request.user,
            x=x,
            y=y,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "spot": {
                "id": spot.id,
                "label": spot.label,
                "x": float(spot.x),
                "y": float(spot.y),
                "status": spot.status,
            },
        }
    )


@login_required(login_url="index")
@require_http_methods(["PATCH", "DELETE"])
def map_spot_detail_api(request, event_id, spot_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    auth_error, _snapshot = _ensure_staff_ops_auth(
        request,
        event=event,
        denied_message="No cuentas con permisos para mover espacios.",
    )
    if auth_error:
        return auth_error

    spot = MapSpot.objects.filter(event=event, id=spot_id).first()
    if not spot:
        return JsonResponse({"ok": False, "error": "Espacio no encontrado."}, status=404)

    if request.method == "DELETE":
        try:
            StaffOpsService.delete_map_spot(event=event, staff_user=request.user, spot=spot)
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse({"ok": True, "deleted_spot_id": spot_id})

    body = _json_body(request)
    x = body.get("x")
    y = body.get("y")

    try:
        updated_spot = StaffOpsService.update_map_spot(
            event=event,
            staff_user=request.user,
            spot=spot,
            x=x,
            y=y,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "spot": {
                "id": updated_spot.id,
                "label": updated_spot.label,
                "x": float(updated_spot.x),
                "y": float(updated_spot.y),
                "status": updated_spot.status,
            },
        }
    )


@login_required(login_url="index")
@require_http_methods(["POST"])
def assign_stall_spot_api(request, event_id, stall_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    auth_error, _snapshot = _ensure_staff_ops_auth(
        request,
        event=event,
        denied_message="No cuentas con permisos para asignar espacios.",
    )
    if auth_error:
        return auth_error

    stall = Stall.objects.filter(event=event, id=stall_id).first()
    if not stall:
        return JsonResponse({"ok": False, "error": "Tienda no encontrada."}, status=404)

    body = _json_body(request)
    spot_id = body.get("spot_id") or request.POST.get("spot_id")
    spot = MapSpot.objects.filter(event=event, id=spot_id).first()
    if not spot:
        return JsonResponse({"ok": False, "error": "Espacio no encontrado."}, status=404)

    try:
        assignment = StaffOpsService.assign_spot_to_stall(
            event=event,
            staff_user=request.user,
            stall=stall,
            spot=spot,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "assignment": {
                "id": assignment.id,
                "stall_id": assignment.stall_id,
                "spot_id": assignment.spot_id,
            },
        }
    )


@login_required(login_url="index")
@require_http_methods(["POST"])
def add_vendor_to_stall_api(request, event_id, stall_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    auth_error, _snapshot = _ensure_staff_ops_auth(
        request,
        event=event,
        denied_message="No cuentas con permisos para agregar vendedores.",
    )
    if auth_error:
        return auth_error

    stall = Stall.objects.filter(event=event, id=stall_id).first()
    if not stall:
        return JsonResponse({"ok": False, "error": "Tienda no encontrada."}, status=404)

    body = _json_body(request)
    vendor_id = body.get("vendor_user_id") or request.POST.get("vendor_user_id")
    user_model = get_user_model()
    vendor_user = user_model.objects.filter(id=vendor_id).first()
    if not vendor_user:
        return JsonResponse({"ok": False, "error": "Usuario vendedor no encontrado."}, status=404)

    try:
        membership, created = StaffOpsService.add_vendor_to_stall(
            event=event,
            staff_user=request.user,
            stall=stall,
            vendor_user=vendor_user,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "membership": {
                "id": membership.id,
                "stall_id": membership.stall_id,
                "vendor_user_id": membership.vendor_user_id,
                "role": membership.role,
            },
        }
    )


@login_required(login_url="index")
@require_http_methods(["POST"])
def grant_ucoins_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    snapshot = build_authz_snapshot(user=request.user, event=event)
    auth_error = enforce_permission_api(
        request=request,
        permission=PERM_GRANT_UCOINS,
        snapshot=snapshot,
        denied_message="No cuentas con permisos para otorgar ucoins.",
    )
    if auth_error:
        return auth_error

    campaign_error = enforce_campaign_window_api(
        snapshot=snapshot,
        message="La ventana de campaña no esta activa para otorgar ucoins.",
    )
    if campaign_error:
        return campaign_error

    body = _json_body(request)
    user_model = get_user_model()
    client_user_id = body.get("client_user_id") or request.POST.get("client_user_id")
    amount_raw = body.get("amount_ucoin") or request.POST.get("amount_ucoin")
    reason = (body.get("reason") or request.POST.get("reason", "")).strip()
    client_user = user_model.objects.filter(id=client_user_id).first()
    if not client_user:
        return JsonResponse({"ok": False, "error": "Cliente no encontrado."}, status=400)
    try:
        amount = Decimal(str(amount_raw))
    except Exception:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": "Monto invalido."}, status=400)

    try:
        topup, grant = StaffOpsService.grant_ucoins(
            event=event,
            staff_user=request.user,
            client_user=client_user,
            amount_ucoin=amount,
            reason=reason,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "topup_id": topup.id,
            "grant_id": grant.id,
            "amount_ucoin": str(grant.amount_ucoin),
        }
    )


@login_required(login_url="index")
@require_http_methods(["POST"])
def assign_vendor_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    auth_error, _snapshot = _ensure_staff_ops_auth(
        request,
        event=event,
        denied_message="No cuentas con permisos para asignar vendedor a puesto.",
    )
    if auth_error:
        return auth_error

    body = _json_body(request)
    user_model = get_user_model()
    vendor_id = body.get("vendor_user_id") or request.POST.get("vendor_user_id")
    stall_id = body.get("stall_id") or request.POST.get("stall_id")
    spot_id = body.get("spot_id") or request.POST.get("spot_id")

    vendor_user = user_model.objects.filter(id=vendor_id).first()
    stall = Stall.objects.filter(event=event, id=stall_id).first()
    spot = MapSpot.objects.filter(event=event, id=spot_id).first()
    if not vendor_user or not stall or not spot:
        return JsonResponse({"ok": False, "error": "Parametros invalidos."}, status=400)

    try:
        assignment, membership = StaffOpsService.assign_vendor(
            event=event,
            staff_user=request.user,
            vendor_user=vendor_user,
            stall=stall,
            spot=spot,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "assignment": {
                "id": assignment.id,
                "stall_id": assignment.stall_id,
                "spot_id": assignment.spot_id,
            },
            "membership": {
                "id": membership.id,
                "vendor_user_id": membership.vendor_user_id,
                "stall_id": membership.stall_id,
            },
        }
    )


@login_required(login_url="index")
@require_http_methods(["POST"])
def assign_spot_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    body = _json_body(request)
    stall_id = body.get("stall_id") or request.POST.get("stall_id")
    return assign_stall_spot_api(request, event_id=event_id, stall_id=stall_id)
