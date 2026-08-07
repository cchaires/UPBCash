from rest_framework.permissions import BasePermission

from events.authz import build_authz_snapshot, has_any_permission, has_permission


class HasEventPermission(BasePermission):
    """Permission class de DRF que envuelve `events.authz.has_permission` sin
    reescribir su logica. La vista debe exponer `get_event()` (resuelve el evento
    desde la URL o desde el objeto relacionado que consulte la vista).

    Uso: `permission_classes = [HasEventPermission.for_permission(PERM_CHECKOUT_CART)]`
    """

    permission_code = None
    denied_message = "No cuentas con permisos para esta accion."

    @classmethod
    def for_permission(cls, permission_code, denied_message=None):
        return type(
            f"HasEventPermission_{permission_code.replace('.', '_')}",
            (cls,),
            {"permission_code": permission_code, "denied_message": denied_message or cls.denied_message},
        )

    def has_permission(self, request, view):
        event = view.get_event() if hasattr(view, "get_event") else None
        snapshot = build_authz_snapshot(user=request.user, event=event)
        view.authz_snapshot = snapshot  # cachea para no recalcular en CampaignWindowOpen/PublicWindowOpen
        if snapshot.is_event_locked:
            self.message = "No hay un evento activo para ejecutar esta operacion."
            return False
        if not has_permission(user=request.user, permission=self.permission_code, snapshot=snapshot):
            self.message = self.denied_message
            return False
        return True


class HasAnyEventPermission(BasePermission):
    """Igual que HasEventPermission pero satisface con cualquiera de varios permisos
    (equivalente a `events.authz.enforce_any_permission_api`)."""

    permission_codes = ()
    denied_message = "No autorizado."

    @classmethod
    def for_permissions(cls, permission_codes, denied_message=None):
        return type(
            "HasAnyEventPermission_" + "_".join(code.replace(".", "_") for code in permission_codes),
            (cls,),
            {"permission_codes": tuple(permission_codes), "denied_message": denied_message or cls.denied_message},
        )

    def has_permission(self, request, view):
        event = view.get_event() if hasattr(view, "get_event") else None
        snapshot = build_authz_snapshot(user=request.user, event=event)
        view.authz_snapshot = snapshot
        if snapshot.is_event_locked:
            self.message = "No hay un evento activo para ejecutar esta operacion."
            return False
        if not has_any_permission(user=request.user, permissions=self.permission_codes, snapshot=snapshot):
            self.message = self.denied_message
            return False
        return True


class CampaignWindowOpen(BasePermission):
    message = "La ventana de campaña no esta activa para esta operacion."

    def has_permission(self, request, view):
        snapshot = getattr(view, "authz_snapshot", None)
        if snapshot is None:
            event = view.get_event() if hasattr(view, "get_event") else None
            snapshot = build_authz_snapshot(user=request.user, event=event)
        return bool(snapshot.is_campaign_open or snapshot.is_superuser)


class PublicWindowOpen(BasePermission):
    message = "La ventana publica del evento no esta activa."

    def has_permission(self, request, view):
        snapshot = getattr(view, "authz_snapshot", None)
        if snapshot is None:
            event = view.get_event() if hasattr(view, "get_event") else None
            snapshot = build_authz_snapshot(user=request.user, event=event)
        return bool(snapshot.is_public_open or snapshot.is_superuser)
