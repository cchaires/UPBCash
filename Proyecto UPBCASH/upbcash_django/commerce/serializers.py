from rest_framework import serializers

from events.services import ensure_user_client_membership

from .services import CheckoutService, FulfillmentService


class CheckoutSerializer(serializers.Serializer):
    """No hace CRUD de modelo: delega toda la logica de negocio en
    `CheckoutService.checkout_cart`, que ya implementa idempotencia, locking
    (select_for_update) y la transaccion atomica completa."""

    order_id = serializers.IntegerField(read_only=True)
    order_number = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    total_ucoin = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    qr_token = serializers.CharField(read_only=True)

    def create(self, validated_data):
        event = self.context["event"]
        user = self.context["request"].user
        ensure_user_client_membership(user=user, event=event)
        order, qr_token = CheckoutService.checkout_cart(event=event, user=user)
        return {
            "order_id": order.id,
            "order_number": order.order_number,
            "status": order.status,
            "total_ucoin": order.total_ucoin,
            "qr_token": qr_token,
        }


class VerifyOrderQrSerializer(serializers.Serializer):
    """Delega en `FulfillmentService.verify_qr_and_deliver`, que ya maneja el
    locking del token QR y el registro de OrderDeliveryLog."""

    token = serializers.CharField(allow_blank=True, required=False, default="")
    order_id = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    def create(self, validated_data):
        order = self.context["order"]
        actor_user = self.context["request"].user
        token = (validated_data.get("token") or "").strip()
        is_valid = FulfillmentService.verify_qr_and_deliver(order=order, raw_token=token, actor_user=actor_user)
        order.refresh_from_db(fields=["status"])
        return {"order_id": order.id, "status": order.status, "is_valid": is_valid}
