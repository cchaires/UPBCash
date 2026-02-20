from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
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
    public_starts_at = models.DateTimeField(null=True, blank=True)
    public_ends_at = models.DateTimeField(null=True, blank=True)
    max_map_spots = models.PositiveIntegerField(default=5)
    map_image = models.FileField(upload_to="events/maps/", null=True, blank=True)
    timezone = models.CharField(max_length=64, default="America/Mexico_City")
    status = models.CharField(max_length=16, choices=CampaignStatus.choices, default=CampaignStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-starts_at", "-id"]
        indexes = [
            models.Index(fields=["status", "starts_at"]),
            models.Index(fields=["starts_at", "ends_at"]),
            models.Index(fields=["status", "public_starts_at"]),
            models.Index(fields=["public_starts_at", "public_ends_at"]),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        public_starts = self.public_starts_at or self.starts_at
        public_ends = self.public_ends_at or self.ends_at
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "La ventana de campaña debe terminar despues de iniciar."})
        if public_starts and public_ends and public_starts >= public_ends:
            raise ValidationError({"public_ends_at": "La ventana publica debe terminar despues de iniciar."})
        if self.starts_at and public_starts and public_starts < self.starts_at:
            raise ValidationError({"public_starts_at": "La ventana publica debe iniciar dentro de la campaña."})
        if self.ends_at and public_ends and public_ends > self.ends_at:
            raise ValidationError({"public_ends_at": "La ventana publica debe terminar dentro de la campaña."})
        if self.max_map_spots <= 0:
            raise ValidationError({"max_map_spots": "El numero maximo de espacios debe ser mayor a cero."})

    @property
    def is_closed(self):
        return self.status == CampaignStatus.CLOSED

    @property
    def is_active_now(self):
        now = timezone.now()
        return self.status == CampaignStatus.ACTIVE and self.starts_at <= now <= self.ends_at

    @property
    def is_public_open_now(self):
        now = timezone.now()
        public_starts = self.public_starts_at or self.starts_at
        public_ends = self.public_ends_at or self.ends_at
        return self.status == CampaignStatus.ACTIVE and public_starts <= now <= public_ends


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
        permissions = [
            ("access_cliente_portal", "Puede acceder al portal cliente"),
            ("checkout_cart", "Puede ejecutar checkout de carrito"),
            ("access_vendedor_portal", "Puede acceder al portal vendedor"),
            ("manage_vendor_products", "Puede crear y editar productos de vendedor"),
            ("soft_delete_vendor_products", "Puede desactivar productos de vendedor"),
            ("manage_vendor_stall_image", "Puede administrar imagen de su tienda"),
            ("verify_order_qr", "Puede verificar QR de orden"),
            ("access_staff_panel", "Puede acceder al panel staff"),
            ("manage_event_profiles", "Puede gestionar perfiles por evento"),
            ("assign_vendor_stall", "Puede asignar vendedor a puesto y espacio"),
            ("grant_ucoins", "Puede otorgar ucoins a clientes"),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.user.username} - {self.group.name}"

# Create your models here.
