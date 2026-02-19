from django.conf import settings
from django.db import models


class SupportTicketStatus(models.TextChoices):
    OPEN = "open", "Abierto"
    IN_PROGRESS = "in_progress", "En proceso"
    RESOLVED = "resolved", "Resuelto"
    CLOSED = "closed", "Cerrado"


class SupportTicketType(models.TextChoices):
    RECHARGE_ISSUE = "recharge_issue", "Problema recarga"
    PAYMENT_ISSUE = "payment_issue", "Problema pago"
    ORDER_ISSUE = "order_issue", "Problema orden"
    OTHER = "other", "Otro"


class SupportTicket(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="support_tickets")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_tickets")
    ticket_type = models.CharField(max_length=32, choices=SupportTicketType.choices)
    order = models.ForeignKey(
        "commerce.SalesOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    topup = models.ForeignKey(
        "accounting.TopupRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="support_tickets",
    )
    summary = models.CharField(max_length=160)
    description = models.TextField()
    status = models.CharField(max_length=16, choices=SupportTicketStatus.choices, default=SupportTicketStatus.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["event", "status", "created_at"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.summary}"


class StaffAuditLog(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="staff_audit_logs")
    staff_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="staff_audit_logs")
    action_type = models.CharField(max_length=64)
    target_model = models.CharField(max_length=64)
    target_id = models.CharField(max_length=64)
    payload_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["event", "action_type", "created_at"]),
            models.Index(fields=["staff_user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.action_type}"

# Create your models here.
