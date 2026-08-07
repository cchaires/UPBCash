from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CampaignWindowOpen, HasEventPermission
from events.authz import PERM_ASSIGN_VENDOR_STALL, PERM_GRANT_UCOINS
from events.models import EventCampaign, EventMembership
from stalls.models import MapSpot, Stall, StallLocationAssignment

from .serializers import (
    AddVendorToStallSerializer,
    AssignStallSpotSerializer,
    AssignVendorSerializer,
    GrantUcoinsSerializer,
    MapSpotCreateSerializer,
    MapSpotUpdateSerializer,
)
from .services import StaffOpsService


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


class MapStateView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(
            PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para consultar el estado del mapa."
        ),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def get(self, request, event_id):
        return Response({"ok": True, **_map_state_payload(self.get_event())})


class MapSpotCreateView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para crear espacios."),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id):
        serializer = MapSpotCreateSerializer(
            data=request.data, context={"request": request, "event": self.get_event()}
        )
        serializer.is_valid(raise_exception=True)
        spot = serializer.save()
        return Response(
            {
                "ok": True,
                "spot": {"id": spot.id, "label": spot.label, "x": float(spot.x), "y": float(spot.y), "status": spot.status},
            }
        )


class MapSpotDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para mover espacios."),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def patch(self, request, event_id, spot_id):
        event = self.get_event()
        spot = get_object_or_404(MapSpot, event=event, id=spot_id)
        serializer = MapSpotUpdateSerializer(spot, data=request.data, context={"request": request, "event": event})
        serializer.is_valid(raise_exception=True)
        updated_spot = serializer.save()
        return Response(
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

    def delete(self, request, event_id, spot_id):
        event = self.get_event()
        spot = get_object_or_404(MapSpot, event=event, id=spot_id)
        StaffOpsService.delete_map_spot(event=event, staff_user=request.user, spot=spot)
        return Response({"ok": True, "deleted_spot_id": spot_id})


class AssignStallSpotView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para asignar espacios."),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id, stall_id):
        event = self.get_event()
        stall = get_object_or_404(Stall, event=event, id=stall_id)
        serializer = AssignStallSpotSerializer(
            data=request.data, context={"request": request, "event": event, "stall": stall}
        )
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(
            {
                "ok": True,
                "assignment": {"id": assignment.id, "stall_id": assignment.stall_id, "spot_id": assignment.spot_id},
            }
        )


class AddVendorToStallView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para agregar vendedores."),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id, stall_id):
        event = self.get_event()
        stall = get_object_or_404(Stall, event=event, id=stall_id)
        serializer = AddVendorToStallSerializer(
            data=request.data, context={"request": request, "event": event, "stall": stall}
        )
        serializer.is_valid(raise_exception=True)
        membership, created = serializer.save()
        return Response(
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


class AssignVendorView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(
            PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para asignar vendedor a puesto."
        ),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id):
        serializer = AssignVendorSerializer(data=request.data, context={"request": request, "event": self.get_event()})
        serializer.is_valid(raise_exception=True)
        assignment, membership = serializer.save()
        return Response(
            {
                "ok": True,
                "assignment": {"id": assignment.id, "stall_id": assignment.stall_id, "spot_id": assignment.spot_id},
                "membership": {
                    "id": membership.id,
                    "vendor_user_id": membership.vendor_user_id,
                    "stall_id": membership.stall_id,
                },
            }
        )


class AssignSpotView(APIView):
    """Alias delgado: toma `stall_id` del body (no de la URL) y reusa la misma
    logica que AssignStallSpotView, replicando `assign_spot_api` original."""

    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_ASSIGN_VENDOR_STALL, "No cuentas con permisos para asignar espacios."),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id):
        event = self.get_event()
        stall = get_object_or_404(Stall, event=event, id=request.data.get("stall_id"))
        serializer = AssignStallSpotSerializer(
            data=request.data, context={"request": request, "event": event, "stall": stall}
        )
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save()
        return Response(
            {
                "ok": True,
                "assignment": {"id": assignment.id, "stall_id": assignment.stall_id, "spot_id": assignment.spot_id},
            }
        )


class GrantUcoinsView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_GRANT_UCOINS, "No cuentas con permisos para otorgar ucoins."),
        CampaignWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id):
        serializer = GrantUcoinsSerializer(data=request.data, context={"request": request, "event": self.get_event()})
        serializer.is_valid(raise_exception=True)
        topup = serializer.save()
        return Response({"ok": True, "topup_id": topup.id, "amount_ucoin": str(topup.amount_ucoin)})
