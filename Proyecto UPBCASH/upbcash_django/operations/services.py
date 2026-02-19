from decimal import Decimal

from django.db import transaction

from accounting.services import WalletService
from events.services import assert_event_writable, assign_group_to_user, remove_group_from_user, user_has_group
from stalls.models import MapSpotStatus, StallAssignment

from .models import StaffAuditLog


class StaffPermissionError(PermissionError):
    pass


class StaffOpsService:
    @classmethod
    def _assert_staff(cls, *, event, user):
        if user.is_superuser:
            return
        if not user_has_group(event=event, user=user, group_name="staff"):
            raise StaffPermissionError("Solo staff puede ejecutar esta accion.")

    @classmethod
    def _log_action(cls, *, event, staff_user, action_type, target_model, target_id, payload):
        return StaffAuditLog.objects.create(
            event=event,
            staff_user=staff_user,
            action_type=action_type,
            target_model=target_model,
            target_id=str(target_id),
            payload_json=payload or {},
        )

    @classmethod
    def _assert_allowed_group(cls, *, group_name):
        if group_name not in {"vendedor", "staff"}:
            raise ValueError("Solo se permite administrar los roles vendedor y staff.")

    @classmethod
    @transaction.atomic
    def grant_role(cls, *, event, staff_user, target_user, group_name):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        cls._assert_allowed_group(group_name=group_name)
        assignment, created = assign_group_to_user(event=event, user=target_user, group_name=group_name)
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="grant_role",
            target_model="events.EventUserGroup",
            target_id=assignment.id,
            payload={
                "target_user_id": target_user.id,
                "group_name": group_name,
                "created": created,
            },
        )
        return assignment, created

    @classmethod
    @transaction.atomic
    def revoke_role(cls, *, event, staff_user, target_user, group_name):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        cls._assert_allowed_group(group_name=group_name)
        if group_name == "staff" and staff_user.id == target_user.id:
            raise StaffPermissionError("No puedes remover tu propio rol staff.")

        removed = remove_group_from_user(event=event, user=target_user, group_name=group_name)
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="revoke_role",
            target_model="events.EventUserGroup",
            target_id=target_user.id,
            payload={
                "target_user_id": target_user.id,
                "group_name": group_name,
                "removed": removed,
            },
        )
        return removed

    @classmethod
    @transaction.atomic
    def assign_vendor(cls, *, event, staff_user, vendor_user, stall, spot):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        if stall.event_id != event.id or spot.event_id != event.id:
            raise ValueError("Puesto y espacio deben pertenecer al evento.")

        assign_group_to_user(event=event, user=vendor_user, group_name="vendedor")
        assignment, created = StallAssignment.objects.get_or_create(
            event=event,
            vendor_user=vendor_user,
            defaults={
                "stall": stall,
                "spot": spot,
                "assigned_by_staff": staff_user,
            },
        )
        if not created:
            previous_spot = assignment.spot
            assignment.stall = stall
            assignment.spot = spot
            assignment.assigned_by_staff = staff_user
            assignment.save(update_fields=["stall", "spot", "assigned_by_staff"])
            if previous_spot_id := getattr(previous_spot, "id", None):
                if previous_spot_id != spot.id:
                    previous_spot.status = MapSpotStatus.AVAILABLE
                    previous_spot.save(update_fields=["status"])
        spot.status = MapSpotStatus.ASSIGNED
        spot.save(update_fields=["status"])
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="assign_vendor",
            target_model="stalls.StallAssignment",
            target_id=assignment.id,
            payload={
                "vendor_user_id": vendor_user.id,
                "stall_id": stall.id,
                "spot_id": spot.id,
            },
        )
        return assignment

    @classmethod
    @transaction.atomic
    def assign_spot(cls, *, event, staff_user, stall, spot):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        if stall.event_id != event.id or spot.event_id != event.id:
            raise ValueError("Puesto y espacio deben pertenecer al evento.")

        assignment = StallAssignment.objects.filter(event=event, stall=stall).select_for_update().first()
        if not assignment:
            raise ValueError("No existe asignacion de vendedor para el puesto.")
        previous_spot = assignment.spot
        assignment.spot = spot
        assignment.assigned_by_staff = staff_user
        assignment.save(update_fields=["spot", "assigned_by_staff"])
        if previous_spot.id != spot.id:
            previous_spot.status = MapSpotStatus.AVAILABLE
            previous_spot.save(update_fields=["status"])
        spot.status = MapSpotStatus.ASSIGNED
        spot.save(update_fields=["status"])
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="assign_spot",
            target_model="stalls.StallAssignment",
            target_id=assignment.id,
            payload={"stall_id": stall.id, "spot_id": spot.id},
        )
        return assignment

    @classmethod
    @transaction.atomic
    def grant_ucoins(cls, *, event, staff_user, client_user, amount_ucoin, reason=""):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)

        amount = Decimal(amount_ucoin)
        topup, grant = WalletService.grant_cash_topup(
            event=event,
            client_user=client_user,
            staff_user=staff_user,
            amount_ucoin=amount,
            reason=reason,
        )
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="grant_ucoins",
            target_model="accounting.StaffCreditGrant",
            target_id=grant.id,
            payload={"client_user_id": client_user.id, "amount_ucoin": str(amount), "reason": reason},
        )
        return topup, grant
