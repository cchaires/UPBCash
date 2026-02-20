from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CampaignStatus, EventCampaign, EventMembership, EventUserGroup, ProfileType

PROFILE_GROUP_NAMES = ("cliente", "vendedor", "staff")


class EventClosedError(ValidationError):
    pass


def get_active_campaign(*, for_update=False):
    queryset = EventCampaign.objects.filter(status=CampaignStatus.ACTIVE).order_by("-starts_at", "-id")
    if for_update:
        queryset = queryset.select_for_update()
    current_event = queryset.filter(starts_at__lte=timezone.now(), ends_at__gte=timezone.now()).first()
    if current_event:
        return current_event
    return queryset.first()


def get_active_event(*, for_update=False):
    return get_active_campaign(for_update=for_update)


def is_campaign_open(event):
    if not event:
        return False
    now = timezone.now()
    return event.status == CampaignStatus.ACTIVE and event.starts_at <= now <= event.ends_at


def is_public_event_open(event):
    if not event:
        return False
    now = timezone.now()
    public_starts = event.public_starts_at or event.starts_at
    public_ends = event.public_ends_at or event.ends_at
    return event.status == CampaignStatus.ACTIVE and public_starts <= now <= public_ends


def validate_campaign_windows(
    *,
    starts_at,
    ends_at,
    public_starts_at=None,
    public_ends_at=None,
):
    if starts_at >= ends_at:
        raise ValidationError("La ventana de campaña debe terminar despues de iniciar.")

    resolved_public_starts = public_starts_at or starts_at
    resolved_public_ends = public_ends_at or ends_at
    if resolved_public_starts >= resolved_public_ends:
        raise ValidationError("La ventana publica debe terminar despues de iniciar.")
    if resolved_public_starts < starts_at or resolved_public_ends > ends_at:
        raise ValidationError("La ventana publica debe quedar contenida dentro de la campaña.")
    return resolved_public_starts, resolved_public_ends


def assert_event_writable(event):
    if event.status == CampaignStatus.CLOSED:
        raise EventClosedError("El evento esta cerrado y en modo solo lectura.")


def ensure_group(name):
    group, _ = Group.objects.get_or_create(name=name)
    return group


@transaction.atomic
def ensure_user_client_membership(
    *,
    user,
    event=None,
    profile_type=ProfileType.COMUNIDAD,
    matricula="",
    phone="",
    invited_by_user=None,
    invited_by_email="",
    invited_by_matricula="",
):
    target_event = event or get_active_campaign(for_update=True)
    if not target_event:
        return None

    membership, created = EventMembership.objects.get_or_create(
        event=target_event,
        user=user,
        defaults={
            "profile_type": profile_type,
            "matricula": matricula,
            "phone": phone,
            "invited_by_user": invited_by_user,
            "invited_by_email": invited_by_email,
            "invited_by_matricula": invited_by_matricula,
        },
    )
    if not created:
        fields_to_update = []
        if profile_type and membership.profile_type != profile_type:
            membership.profile_type = profile_type
            fields_to_update.append("profile_type")
        if matricula and membership.matricula != matricula:
            membership.matricula = matricula
            fields_to_update.append("matricula")
        if phone and membership.phone != phone:
            membership.phone = phone
            fields_to_update.append("phone")
        if invited_by_user and membership.invited_by_user_id != invited_by_user.id:
            membership.invited_by_user = invited_by_user
            fields_to_update.append("invited_by_user")
        if invited_by_email and membership.invited_by_email != invited_by_email:
            membership.invited_by_email = invited_by_email
            fields_to_update.append("invited_by_email")
        if invited_by_matricula and membership.invited_by_matricula != invited_by_matricula:
            membership.invited_by_matricula = invited_by_matricula
            fields_to_update.append("invited_by_matricula")
        if fields_to_update:
            membership.save(update_fields=fields_to_update)

    client_group = ensure_group("cliente")
    EventUserGroup.objects.get_or_create(event=target_event, user=user, group=client_group)
    return membership


def user_has_group(*, event, user, group_name):
    return EventUserGroup.objects.filter(event=event, user=user, group__name=group_name).exists()


def get_event_profiles(*, user, event):
    if not event or not user or not user.is_authenticated:
        return set()
    return set(
        EventUserGroup.objects.filter(
            event=event,
            user=user,
            group__name__in=PROFILE_GROUP_NAMES,
        ).values_list("group__name", flat=True)
    )


def _fallback_profiles_without_active_event(*, user):
    if EventUserGroup.objects.filter(user=user, group__name="staff").exists():
        return {"staff"}
    return set()


def sync_auth_profile_groups_for_event(*, user, event):
    if not user or not user.is_authenticated:
        return set()

    for group_name in PROFILE_GROUP_NAMES:
        ensure_group(group_name)

    desired_group_names = get_event_profiles(user=user, event=event) if event else _fallback_profiles_without_active_event(user=user)
    current_group_names = set(user.groups.filter(name__in=PROFILE_GROUP_NAMES).values_list("name", flat=True))

    to_add = desired_group_names - current_group_names
    to_remove = current_group_names - desired_group_names

    if to_add:
        user.groups.add(*Group.objects.filter(name__in=to_add))
    if to_remove:
        user.groups.remove(*Group.objects.filter(name__in=to_remove))

    return desired_group_names


@transaction.atomic
def assign_group_to_user(*, event, user, group_name):
    group = ensure_group(group_name)
    return EventUserGroup.objects.get_or_create(event=event, user=user, group=group)


@transaction.atomic
def remove_group_from_user(*, event, user, group_name):
    deleted, _ = EventUserGroup.objects.filter(event=event, user=user, group__name=group_name).delete()
    return deleted > 0
