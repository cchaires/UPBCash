from events.services import get_active_event, user_has_group


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

    event = get_active_event()
    if not event:
        flags["can_view_admin"] = bool(user.is_superuser)
        return flags

    flags["active_event_code"] = event.code
    flags["can_view_vendor"] = user_has_group(event=event, user=user, group_name="vendedor")
    flags["can_view_staff"] = user_has_group(event=event, user=user, group_name="staff")
    flags["can_view_admin"] = bool(user.is_superuser)
    return flags
