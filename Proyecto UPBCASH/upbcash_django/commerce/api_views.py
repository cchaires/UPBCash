from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import HasAnyEventPermission, HasEventPermission, PublicWindowOpen
from events.authz import (
    PERM_ACCESS_STAFF_PANEL,
    PERM_CHECKOUT_CART,
    PERM_VERIFY_ORDER_QR,
    build_authz_snapshot,
    has_any_permission,
)
from events.models import EventCampaign

from .models import SalesOrder
from .serializers import CheckoutSerializer, VerifyOrderQrSerializer


class CartCheckoutView(APIView):
    permission_classes = [
        IsAuthenticated,
        HasEventPermission.for_permission(PERM_CHECKOUT_CART, "No cuentas con permisos para ejecutar checkout."),
        PublicWindowOpen,
    ]

    def get_event(self):
        return get_object_or_404(EventCampaign, id=self.kwargs["event_id"])

    def post(self, request, event_id):
        serializer = CheckoutSerializer(data=request.data, context={"request": request, "event": self.get_event()})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        return Response(
            {
                "ok": True,
                "order": {
                    "id": result["order_id"],
                    "order_number": result["order_number"],
                    "status": result["status"],
                    "total_ucoin": str(result["total_ucoin"]),
                },
                "qr_token": result["qr_token"],
            }
        )


class VerifyOrderQrView(APIView):
    """Verificacion de entrega por QR (staff o vendedor con permiso especifico).

    Replica el doble chequeo del endpoint original: primero un permiso general sin
    evento especifico (para no revelar si la orden existe a alguien sin ningun
    permiso relevante), y solo si eso pasa se busca la orden y se re-valida el
    permiso y la ventana de campaña ya con el evento real de la orden.
    """

    permission_classes = [
        IsAuthenticated,
        HasAnyEventPermission.for_permissions(
            [PERM_VERIFY_ORDER_QR, PERM_ACCESS_STAFF_PANEL],
            "No cuentas con permisos para verificar entregas por QR.",
        ),
    ]

    def post(self, request, order_id):
        order = get_object_or_404(SalesOrder.objects.select_related("event"), id=order_id)

        snapshot = build_authz_snapshot(user=request.user, event=order.event)
        if not has_any_permission(
            user=request.user,
            permissions=[PERM_VERIFY_ORDER_QR, PERM_ACCESS_STAFF_PANEL],
            snapshot=snapshot,
        ):
            raise PermissionDenied("No cuentas con permisos para verificar entregas por QR.")
        if not (snapshot.is_campaign_open or snapshot.is_superuser):
            raise PermissionDenied("La ventana de campaña no esta activa para verificar QR.")

        serializer = VerifyOrderQrSerializer(data=request.data, context={"request": request, "order": order})
        serializer.is_valid(raise_exception=True)
        result = serializer.save()
        is_valid = result["is_valid"]
        return Response(
            {
                "ok": is_valid,
                "order_id": result["order_id"],
                "status": result["status"],
                "error": "" if is_valid else "Token invalido o expirado.",
            },
            status=200 if is_valid else 400,
        )
