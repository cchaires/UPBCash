from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import serializers

from stalls.models import MapSpot, Stall

from .services import StaffOpsService

User = get_user_model()


class MapSpotCreateSerializer(serializers.Serializer):
    """No hace CRUD de modelo: delega en `StaffOpsService.create_map_spot`, que ya
    valida el limite `event.max_map_spots` y las coordenadas normalizadas."""

    x = serializers.CharField()
    y = serializers.CharField()

    def create(self, validated_data):
        return StaffOpsService.create_map_spot(
            event=self.context["event"],
            staff_user=self.context["request"].user,
            x=validated_data["x"],
            y=validated_data["y"],
        )


class MapSpotUpdateSerializer(serializers.Serializer):
    x = serializers.CharField(required=False, allow_null=True, default=None)
    y = serializers.CharField(required=False, allow_null=True, default=None)

    def update(self, instance, validated_data):
        return StaffOpsService.update_map_spot(
            event=self.context["event"],
            staff_user=self.context["request"].user,
            spot=instance,
            x=validated_data.get("x"),
            y=validated_data.get("y"),
        )


class AssignStallSpotSerializer(serializers.Serializer):
    spot_id = serializers.IntegerField()

    def create(self, validated_data):
        event = self.context["event"]
        spot = get_object_or_404(MapSpot, event=event, id=validated_data["spot_id"])
        return StaffOpsService.assign_spot_to_stall(
            event=event,
            staff_user=self.context["request"].user,
            stall=self.context["stall"],
            spot=spot,
        )


class AddVendorToStallSerializer(serializers.Serializer):
    vendor_user_id = serializers.IntegerField()

    def create(self, validated_data):
        event = self.context["event"]
        vendor_user = get_object_or_404(User, id=validated_data["vendor_user_id"])
        return StaffOpsService.add_vendor_to_stall(
            event=event,
            staff_user=self.context["request"].user,
            stall=self.context["stall"],
            vendor_user=vendor_user,
        )


class AssignVendorSerializer(serializers.Serializer):
    vendor_user_id = serializers.IntegerField()
    stall_id = serializers.IntegerField()
    spot_id = serializers.IntegerField()

    def create(self, validated_data):
        event = self.context["event"]
        vendor_user = get_object_or_404(User, id=validated_data["vendor_user_id"])
        stall = get_object_or_404(Stall, event=event, id=validated_data["stall_id"])
        spot = get_object_or_404(MapSpot, event=event, id=validated_data["spot_id"])
        return StaffOpsService.assign_vendor(
            event=event,
            staff_user=self.context["request"].user,
            vendor_user=vendor_user,
            stall=stall,
            spot=spot,
        )


class GrantUcoinsSerializer(serializers.Serializer):
    client_user_id = serializers.IntegerField()
    amount_ucoin = serializers.CharField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_amount_ucoin(self, value):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise serializers.ValidationError("Monto invalido.") from exc

    def create(self, validated_data):
        event = self.context["event"]
        client_user = get_object_or_404(User, id=validated_data["client_user_id"])
        return StaffOpsService.grant_ucoins(
            event=event,
            staff_user=self.context["request"].user,
            client_user=client_user,
            amount_ucoin=validated_data["amount_ucoin"],
            reason=validated_data.get("reason", ""),
        )
