import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from events.models import EventCampaign
from stalls.models import MapSpot, Stall

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


@login_required(login_url="index")
@require_POST
def assign_vendor_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    body = _json_body(request)
    user_model = get_user_model()
    vendor_id = body.get("vendor_user_id") or request.POST.get("vendor_user_id")
    stall_id = body.get("stall_id") or request.POST.get("stall_id")
    spot_id = body.get("spot_id") or request.POST.get("spot_id")

    vendor_user = user_model.objects.filter(id=vendor_id).first()
    stall = Stall.objects.filter(id=stall_id).first()
    spot = MapSpot.objects.filter(id=spot_id).first()
    if not vendor_user or not stall or not spot:
        return JsonResponse({"ok": False, "error": "Parametros invalidos."}, status=400)

    try:
        assignment = StaffOpsService.assign_vendor(
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
                "vendor_user_id": assignment.vendor_user_id,
                "stall_id": assignment.stall_id,
                "spot_id": assignment.spot_id,
            },
        }
    )


@login_required(login_url="index")
@require_POST
def assign_spot_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

    body = _json_body(request)
    stall_id = body.get("stall_id") or request.POST.get("stall_id")
    spot_id = body.get("spot_id") or request.POST.get("spot_id")
    stall = Stall.objects.filter(id=stall_id).first()
    spot = MapSpot.objects.filter(id=spot_id).first()
    if not stall or not spot:
        return JsonResponse({"ok": False, "error": "Parametros invalidos."}, status=400)

    try:
        assignment = StaffOpsService.assign_spot(
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
            "assignment": {"id": assignment.id, "stall_id": assignment.stall_id, "spot_id": assignment.spot_id},
        }
    )


@login_required(login_url="index")
@require_POST
def grant_ucoins_api(request, event_id):
    event = _load_event(event_id)
    if not event:
        return JsonResponse({"ok": False, "error": "Evento no encontrado."}, status=404)

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
