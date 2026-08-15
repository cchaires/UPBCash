from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from accounting.services import WalletService
from events.models import CampaignStatus, EventUserGroup
from events.services import (
    PROFILE_GROUP_NAMES,
    activate_campaign,
    assert_event_writable,
    assign_group_to_user,
    remove_group_from_user,
    user_has_group,
)
from stalls.models import (
    MapSpot,
    MapSpotStatus,
    MapZone,
    Stall,
    StallLocationAssignment,
    StallVendorMembership,
    StallVendorRole,
)

from .models import StaffAuditLog


class StaffPermissionError(PermissionError):
    pass


class StaffOpsService:
    BLOCKED_GROUP_NAMES = {"admin", "administrador", "superuser"}
    DEFAULT_MANAGEABLE_GROUP_NAMES = PROFILE_GROUP_NAMES
    MAX_VENDORS_PER_STALL = 3

    @classmethod
    def _assert_staff(cls, *, event, user):
        if user.is_superuser:
            return
        if not user_has_group(event=event, user=user, group_name="staff"):
            raise StaffPermissionError("Solo staff puede ejecutar esta accion.")

    @classmethod
    def _log_action(cls, *, event, staff_user, action_type, target_object, payload):
        return StaffAuditLog.objects.create(
            event=event,
            staff_user=staff_user,
            action_type=action_type,
            target_object=target_object,
            payload_json=payload or {},
        )

    @classmethod
    def _log_action_for_deleted_object(cls, *, event, staff_user, action_type, target_model, target_id, payload):
        """Variante para loguear un objeto que ya fue borrado de la BD (ej. delete_map_spot):
        asigna content_type/object_id explicitos en vez de `target_object=instancia`, porque
        la instancia ya no existe en la base de datos cuando se llama a este metodo."""
        return StaffAuditLog.objects.create(
            event=event,
            staff_user=staff_user,
            action_type=action_type,
            target_content_type=ContentType.objects.get_for_model(target_model),
            target_object_id=target_id,
            payload_json=payload or {},
        )

    @classmethod
    def _assert_allowed_group(cls, *, group_name):
        if group_name not in {"vendedor", "staff"}:
            raise ValueError("Solo se permite administrar los roles vendedor y staff.")

    @classmethod
    def list_manageable_group_names(cls, *, event):
        del event
        for group_name in PROFILE_GROUP_NAMES:
            Group.objects.get_or_create(name=group_name)
        return list(PROFILE_GROUP_NAMES)

    @classmethod
    @transaction.atomic
    def sync_user_roles(cls, *, event, staff_user, target_user, desired_group_names):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)

        manageable_group_names = set(cls.list_manageable_group_names(event=event))
        desired = {group_name for group_name in desired_group_names if group_name}
        desired_manageable = desired & manageable_group_names

        ignored = sorted(desired - manageable_group_names)
        current_manageable = set(
            event.user_groups.filter(
                user=target_user,
                group__name__in=manageable_group_names,
            ).values_list("group__name", flat=True)
        )

        to_add = desired_manageable - current_manageable
        to_remove = current_manageable - desired_manageable

        if "cliente" in to_remove:
            to_remove.remove("cliente")
            ignored.append("cliente")

        if target_user.id == staff_user.id and "staff" in to_remove:
            to_remove.remove("staff")
            ignored.append("staff")

        added = []
        for group_name in sorted(to_add):
            _assignment, created = assign_group_to_user(event=event, user=target_user, group_name=group_name)
            if created:
                added.append(group_name)

        removed = []
        for group_name in sorted(to_remove):
            if remove_group_from_user(event=event, user=target_user, group_name=group_name):
                removed.append(group_name)

        ignored = sorted(set(ignored))
        payload = {
            "target_user_id": target_user.id,
            "desired": sorted(desired_manageable),
            "added": added,
            "removed": removed,
            "ignored": ignored,
        }
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="sync_roles",
            # Antes decia target_model="events.EventUserGroup" pero target_id era el id
            # de un User, no de un EventUserGroup (bug preexistente) - se corrige apuntando
            # al usuario real.
            target_object=target_user,
            payload=payload,
        )
        return payload

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
            target_object=assignment,
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
            # Mismo bug preexistente que en sync_user_roles: corregido apuntando al User real.
            target_object=target_user,
            payload={
                "target_user_id": target_user.id,
                "group_name": group_name,
                "removed": removed,
            },
        )
        return removed

    @classmethod
    def get_vendor_membership(cls, *, event, user):
        return (
            StallVendorMembership.objects.select_related("stall")
            .filter(event=event, vendor_user=user)
            .order_by("id")
            .first()
        )

    @classmethod
    def get_stall_location(cls, *, event, stall):
        return (
            StallLocationAssignment.objects.select_related("spot", "spot__zone")
            .filter(event=event, stall=stall)
            .order_by("-assigned_at", "-id")
            .first()
        )

    @classmethod
    def get_stall_memberships(cls, *, event, stall):
        return StallVendorMembership.objects.select_related("vendor_user").filter(event=event, stall=stall).order_by("id")

    @classmethod
    def _normalize_coordinate(cls, *, raw_value, coord_name):
        try:
            value = Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"La coordenada {coord_name} es invalida.")  # noqa: B904
        if value < 0 or value > 1:
            raise ValueError(f"La coordenada {coord_name} debe estar entre 0 y 1.")
        return value.quantize(Decimal("0.001"))

    @classmethod
    def _get_default_zone(cls, *, event):
        zone, _ = MapZone.objects.get_or_create(
            event=event,
            name="General",
            defaults={"sort_order": 0},
        )
        return zone

    @classmethod
    def _next_spot_label(cls, *, event):
        max_suffix = 0
        for label in MapSpot.objects.filter(event=event, label__startswith="S-").values_list("label", flat=True):
            suffix = label.split("-", 1)[-1]
            if suffix.isdigit():
                max_suffix = max(max_suffix, int(suffix))
        return f"S-{max_suffix + 1:02d}"

    @classmethod
    @transaction.atomic
    def create_map_spot(cls, *, event, staff_user, x, y):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)

        current_count = MapSpot.objects.filter(event=event).count()
        if event.max_map_spots and current_count >= event.max_map_spots:
            raise ValueError("No puedes crear mas espacios que el maximo configurado para el evento.")

        spot = MapSpot.objects.create(
            event=event,
            zone=cls._get_default_zone(event=event),
            label=cls._next_spot_label(event=event),
            x=cls._normalize_coordinate(raw_value=x, coord_name="x"),
            y=cls._normalize_coordinate(raw_value=y, coord_name="y"),
            status=MapSpotStatus.AVAILABLE,
        )
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="create_map_spot",
            target_object=spot,
            payload={"label": spot.label, "x": str(spot.x), "y": str(spot.y)},
        )
        return spot

    @classmethod
    @transaction.atomic
    def update_map_spot(cls, *, event, staff_user, spot, x=None, y=None):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        if spot.event_id != event.id:
            raise ValueError("El espacio debe pertenecer al evento.")

        fields_to_update = []
        if x is not None:
            spot.x = cls._normalize_coordinate(raw_value=x, coord_name="x")
            fields_to_update.append("x")
        if y is not None:
            spot.y = cls._normalize_coordinate(raw_value=y, coord_name="y")
            fields_to_update.append("y")
        if fields_to_update:
            spot.save(update_fields=fields_to_update)
            cls._log_action(
                event=event,
                staff_user=staff_user,
                action_type="update_map_spot",
                target_object=spot,
                payload={"x": str(spot.x), "y": str(spot.y)},
            )
        return spot

    @classmethod
    @transaction.atomic
    def delete_map_spot(cls, *, event, staff_user, spot):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        if spot.event_id != event.id:
            raise ValueError("El espacio debe pertenecer al evento.")
        if StallLocationAssignment.objects.filter(event=event, spot=spot).exists():
            raise ValueError("No puedes eliminar un espacio asignado a una tienda.")
        spot_id = spot.id
        label = spot.label
        spot.delete()
        # El spot ya fue borrado (spot.delete() arriba): no se puede usar
        # target_object=spot porque la instancia ya no existe en la BD.
        cls._log_action_for_deleted_object(
            event=event,
            staff_user=staff_user,
            action_type="delete_map_spot",
            target_model=MapSpot,
            target_id=spot_id,
            payload={"label": label},
        )

    @classmethod
    @transaction.atomic
    def create_vendor_stall(
        cls,
        *,
        event,
        vendor_user,
        name,
        code="",
        description="",
        image=None,
    ):
        assert_event_writable(event)
        existing_membership = cls.get_vendor_membership(event=event, user=vendor_user)
        if existing_membership:
            raise ValueError("El vendedor ya pertenece a una tienda en este evento.")
        if not name or not name.strip():
            raise ValueError("El nombre de la tienda es obligatorio.")

        suggested_code = (code or f"stall-u{vendor_user.id}").strip().lower().replace(" ", "-")[:32]
        base_code = suggested_code or f"stall-u{vendor_user.id}"
        candidate = base_code
        suffix = 1
        while Stall.objects.filter(event=event, code=candidate).exists():
            suffix += 1
            candidate = f"{base_code[:24]}-{suffix}"[:32]

        stall = Stall.objects.create(
            event=event,
            code=candidate,
            name=name.strip(),
            description=description.strip(),
            status="open",
            image=image,
        )
        membership = StallVendorMembership.objects.create(
            event=event,
            stall=stall,
            vendor_user=vendor_user,
            role=StallVendorRole.OWNER,
            assigned_by_staff=None,
        )
        assign_group_to_user(event=event, user=vendor_user, group_name="vendedor")
        return stall, membership

    @classmethod
    @transaction.atomic
    def add_vendor_to_stall(
        cls,
        *,
        event,
        staff_user,
        stall,
        vendor_user,
        role=StallVendorRole.MEMBER,
    ):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        if stall.event_id != event.id:
            raise ValueError("La tienda debe pertenecer al evento.")

        vendor_membership = cls.get_vendor_membership(event=event, user=vendor_user)
        if vendor_membership and vendor_membership.stall_id != stall.id:
            raise ValueError("El vendedor ya pertenece a otra tienda en este evento.")
        if vendor_membership and vendor_membership.stall_id == stall.id:
            return vendor_membership, False

        current_count = StallVendorMembership.objects.filter(event=event, stall=stall).count()
        if current_count >= cls.MAX_VENDORS_PER_STALL:
            raise ValueError("La tienda ya tiene el maximo de 3 vendedores.")

        membership = StallVendorMembership.objects.create(
            event=event,
            stall=stall,
            vendor_user=vendor_user,
            role=role,
            assigned_by_staff=staff_user,
        )
        assign_group_to_user(event=event, user=vendor_user, group_name="vendedor")
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="add_vendor_to_stall",
            target_object=membership,
            payload={
                "stall_id": stall.id,
                "vendor_user_id": vendor_user.id,
                "role": role,
            },
        )
        return membership, True

    @classmethod
    @transaction.atomic
    def assign_spot_to_stall(cls, *, event, staff_user, stall, spot):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)
        if stall.event_id != event.id or spot.event_id != event.id:
            raise ValueError("Tienda y espacio deben pertenecer al evento.")
        if spot.status == MapSpotStatus.BLOCKED:
            raise ValueError("No puedes asignar un espacio bloqueado.")
        taken_by_other = StallLocationAssignment.objects.filter(event=event, spot=spot).exclude(stall=stall).exists()
        if taken_by_other:
            raise ValueError("El espacio ya esta asignado a otra tienda.")

        previous_assignment = StallLocationAssignment.objects.filter(event=event, stall=stall).first()
        if previous_assignment and previous_assignment.spot_id == spot.id:
            return previous_assignment

        assignment, created = StallLocationAssignment.objects.get_or_create(
            event=event,
            stall=stall,
            defaults={
                "spot": spot,
                "assigned_by_staff": staff_user,
            },
        )
        if not created:
            previous_spot = previous_assignment.spot if previous_assignment else assignment.spot
            assignment.spot = spot
            assignment.assigned_by_staff = staff_user
            assignment.save(update_fields=["spot", "assigned_by_staff"])
            if previous_spot and previous_spot.id != spot.id:
                previous_spot.status = MapSpotStatus.AVAILABLE
                previous_spot.save(update_fields=["status"])

        if spot.status != MapSpotStatus.ASSIGNED:
            spot.status = MapSpotStatus.ASSIGNED
            spot.save(update_fields=["status"])
        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="assign_spot_to_stall",
            target_object=assignment,
            payload={
                "stall_id": stall.id,
                "spot_id": spot.id,
            },
        )
        return assignment

    @classmethod
    @transaction.atomic
    def assign_vendor(cls, *, event, staff_user, vendor_user, stall, spot):
        membership, _created = cls.add_vendor_to_stall(
            event=event,
            staff_user=staff_user,
            stall=stall,
            vendor_user=vendor_user,
            role=StallVendorRole.MEMBER,
        )
        assignment = cls.assign_spot_to_stall(
            event=event,
            staff_user=staff_user,
            stall=stall,
            spot=spot,
        )
        return assignment, membership

    @classmethod
    @transaction.atomic
    def assign_spot(cls, *, event, staff_user, stall, spot):
        return cls.assign_spot_to_stall(event=event, staff_user=staff_user, stall=stall, spot=spot)

    @classmethod
    @transaction.atomic
    def activate_event(cls, *, event, staff_user):
        """Activa `event` y arrastra al equipo staff para no dejarlo fuera.

        `EventUserGroup` es por evento y `sync_auth_profile_groups_for_event`
        remueve de `auth.Group` todo rol que el usuario no tenga en el evento
        activo. Una campana recien creada no tiene ninguna membresia, asi que
        activarla sin sembrar el rol `staff` dejaria a todo el personal sin
        acceso a `/staff/` y sin poder operar el mapa. Por eso se copia el
        conjunto de usuarios con rol `staff` de la campana que estaba activa,
        mas quien ejecuta la accion.

        `cliente` no se copia porque `ensure_user_client_membership` lo recrea
        en cada request, y `vendedor` tampoco porque los puestos y espacios son
        propios de cada evento y deben reasignarse.

        Nota de autorizacion: aqui NO se llama a `_assert_staff(event=event)`.
        Ese helper valida contra `EventUserGroup` del evento indicado y el
        evento destino todavia no tiene membresias, asi que se rechazaria
        siempre a si mismo. La compuerta es la vista, que exige
        `PERM_MANAGE_EVENT_PROFILES` evaluado contra el evento activo, que es
        el contexto donde el usuario si tiene rol.
        """
        # Se lee de todas las campanas activas distintas a la destino y no de
        # `get_active_campaign()`: cuando el evento se guarda ya con status
        # activo antes de llamar aqui, ese helper podria devolver el propio
        # evento destino y el equipo no se arrastraria.
        staff_user_ids = set(
            EventUserGroup.objects.filter(
                event__status=CampaignStatus.ACTIVE,
                group__name="staff",
            )
            .exclude(event_id=event.id)
            .values_list("user_id", flat=True)
        )
        if staff_user and staff_user.is_authenticated and not staff_user.is_superuser:
            staff_user_ids.add(staff_user.id)

        demoted = activate_campaign(event=event)

        user_model = get_user_model()
        for carried_user in user_model.objects.filter(id__in=staff_user_ids):
            assign_group_to_user(event=event, user=carried_user, group_name="staff")

        cls._log_action(
            event=event,
            staff_user=staff_user,
            action_type="activate_event",
            target_object=event,
            payload={
                "event_code": event.code,
                "demoted_event_codes": [campaign.code for campaign in demoted],
                "carried_staff_user_ids": sorted(staff_user_ids),
            },
        )
        return demoted

    @classmethod
    @transaction.atomic
    def grant_ucoins(cls, *, event, staff_user, client_user, amount_ucoin, reason=""):
        assert_event_writable(event)
        cls._assert_staff(event=event, user=staff_user)

        amount = Decimal(amount_ucoin)
        topup = WalletService.grant_cash_topup(
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
            target_object=topup,
            payload={"client_user_id": client_user.id, "amount_ucoin": str(amount), "reason": reason},
        )
        return topup
