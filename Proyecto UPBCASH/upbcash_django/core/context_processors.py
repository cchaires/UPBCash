from events.authz import PERM_ACCESS_STAFF_PANEL, PERM_ACCESS_VENDEDOR_PORTAL, build_authz_snapshot, has_permission


def role_flags(request):
    user = getattr(request, "user", None)
    flags = {
        "can_view_vendor": False,
        "can_view_staff": False,
        "can_view_admin": False,
        "active_event_code": "",
    }
    if not user or not user.is_authenticated:
        return flags

    snapshot = build_authz_snapshot(user=user)
    event = snapshot.event
    if not event:
        flags["can_view_vendor"] = has_permission(
            user=user,
            permission=PERM_ACCESS_VENDEDOR_PORTAL,
            snapshot=snapshot,
        )
        flags["can_view_staff"] = has_permission(
            user=user,
            permission=PERM_ACCESS_STAFF_PANEL,
            snapshot=snapshot,
        )
        flags["can_view_admin"] = bool(user.is_superuser)
        return flags

    flags["active_event_code"] = event.code
    flags["can_view_vendor"] = has_permission(
        user=user,
        permission=PERM_ACCESS_VENDEDOR_PORTAL,
        snapshot=snapshot,
    )
    flags["can_view_staff"] = has_permission(
        user=user,
        permission=PERM_ACCESS_STAFF_PANEL,
        snapshot=snapshot,
    )
    flags["can_view_admin"] = bool(user.is_superuser)
    return flags
