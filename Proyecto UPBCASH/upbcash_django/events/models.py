from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone


class CampaignStatus(models.TextChoices):
    DRAFT = "draft", "Borrador"
    ACTIVE = "active", "Activo"
    CLOSED = "closed", "Cerrado"


class ProfileType(models.TextChoices):
    COMUNIDAD = "comunidad", "Comunidad"
    INVITADO = "invitado", "Invitado"


class EventCampaign(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    timezone = models.CharField(max_length=64, default="America/Mexico_City")
    status = models.CharField(max_length=16, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at", "-id"]
        indexes = [
            models.Index(fields=["status", "starts_at"]),
            models.Index(fields=["starts_at", "ends_at"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    @property
    def is_closed(self):
        return self.status == CampaignStatus.CLOSED

    @property
    def is_active_now(self):
        now = timezone.now()
        return self.status == CampaignStatus.ACTIVE and self.starts_at <= now <= self.ends_at


class EventMembership(models.Model):
    event = models.ForeignKey(EventCampaign, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_memberships")
    profile_type = models.CharField(max_length=20, choices=ProfileType.choices, default=ProfileType.COMUNIDAD)
    matricula = models.CharField(max_length=64, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    invited_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invited_memberships",
    )
    invited_by_email = models.EmailField(blank=True)
    invited_by_matricula = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="uniq_event_membership_user"),
        ]
        indexes = [
            models.Index(fields=["event", "profile_type"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.user.username}"


class EventUserGroup(models.Model):
    event = models.ForeignKey(EventCampaign, on_delete=models.CASCADE, related_name="user_groups")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="event_user_groups")
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="event_assignments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user", "group"], name="uniq_event_user_group"),
        ]
        indexes = [
            models.Index(fields=["event", "group", "user"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.user.username} - {self.group.name}"

# Create your models here.
