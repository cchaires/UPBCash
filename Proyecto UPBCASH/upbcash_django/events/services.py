from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import CampaignStatus, EventCampaign, EventMembership, EventUserGroup, ProfileType


class EventClosedError(ValidationError):
    pass


def get_active_event(*, for_update=False):
    queryset = EventCampaign.objects.filter(status=CampaignStatus.ACTIVE).order_by("-starts_at", "-id")
    if for_update:
        queryset = queryset.select_for_update()
    current_event = queryset.filter(starts_at__lte=timezone.now(), ends_at__gte=timezone.now()).first()
    if current_event:
        return current_event
    return queryset.first()


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
    target_event = event or get_active_event(for_update=True)
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


@transaction.atomic
def assign_group_to_user(*, event, user, group_name):
    group = ensure_group(group_name)
    return EventUserGroup.objects.get_or_create(event=event, user=user, group=group)


@transaction.atomic
def remove_group_from_user(*, event, user, group_name):
    deleted, _ = EventUserGroup.objects.filter(event=event, user=user, group__name=group_name).delete()
    return deleted > 0
