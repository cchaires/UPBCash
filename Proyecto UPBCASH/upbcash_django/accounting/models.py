import uuid

from django.conf import settings
from django.db import models


class LedgerAccountType(models.TextChoices):
    ASSET = "asset", "Activo"
    LIABILITY = "liability", "Pasivo"
    REVENUE = "revenue", "Ingreso"
    EXPENSE = "expense", "Gasto"
    EQUITY = "equity", "Capital"


class LedgerTxType(models.TextChoices):
    TOPUP_ONLINE = "topup_online", "Recarga en linea"
    TOPUP_CASH = "topup_cash", "Recarga en efectivo"
    PURCHASE = "purchase", "Compra"
    REFUND = "refund", "Reembolso"
    ADJUSTMENT = "adjustment", "Ajuste"
    EXPIRY = "expiry", "Expiracion"


class LedgerTxStatus(models.TextChoices):
    POSTED = "posted", "Registrada"
    VOID = "void", "Anulada"


class TopupChannel(models.TextChoices):
    ONLINE = "online", "En linea"
    CASH_STAFF = "cash_staff", "Efectivo staff"


class TopupStatus(models.TextChoices):
    SUCCESS = "success", "Exitosa"
    PENDING = "pending", "Pendiente"
    FAILED = "failed", "Fallida"


class LedgerAccount(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="ledger_accounts")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    account_type = models.CharField(max_length=16, choices=LedgerAccountType.choices)
    owner_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_ledger_accounts",
    )
    owner_stall = models.ForeignKey(
        "stalls.Stall",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_ledger_accounts",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "code"], name="uniq_ledger_account_code_by_event"),
        ]
        indexes = [
            models.Index(fields=["event", "account_type"]),
            models.Index(fields=["event", "owner_user"]),
        ]

    def __str__(self):
        return f"{self.event.code}:{self.code}"


class LedgerTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="ledger_transactions")
    tx_type = models.CharField(max_length=24, choices=LedgerTxType.choices)
    status = models.CharField(max_length=16, choices=LedgerTxStatus.choices, default=LedgerTxStatus.POSTED)
    idempotency_key = models.CharField(max_length=120, unique=True)
    reference_model = models.CharField(max_length=64, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_transactions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "id"]
        indexes = [
            models.Index(fields=["event", "tx_type", "created_at"]),
            models.Index(fields=["event", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.tx_type} - {self.id}"


class LedgerEntry(models.Model):
    transaction = models.ForeignKey(LedgerTransaction, on_delete=models.CASCADE, related_name="entries")
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="entries")
    amount_mxn_signed = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(amount_mxn_signed=0),
                name="check_ledger_entry_nonzero_amount",
            ),
        ]
        indexes = [
            models.Index(fields=["account", "id"]),
            models.Index(fields=["transaction", "id"]),
        ]

    def __str__(self):
        return f"{self.transaction_id} - {self.amount_mxn_signed}"


class WalletBalanceCache(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="wallet_balances")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet_balances")
    balance_ucoin = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["event", "user"]
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], name="uniq_wallet_balance_cache_event_user"),
        ]
        indexes = [
            models.Index(fields=["event", "updated_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.user.username}: {self.balance_ucoin}"


class TopupRecord(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="topup_records")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="topup_records")
    channel = models.CharField(max_length=16, choices=TopupChannel.choices)
    amount_ucoin = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=16, choices=TopupStatus.choices, default=TopupStatus.SUCCESS)
    provider = models.CharField(max_length=64, blank=True)
    provider_ref = models.CharField(max_length=80, blank=True)
    source_reference = models.CharField(max_length=64, blank=True, default="")
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_topups_granted",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount_ucoin__gt=0), name="check_topup_amount_positive"),
            models.UniqueConstraint(
                fields=["event", "source_reference"],
                condition=~models.Q(source_reference=""),
                name="uniq_nonempty_topup_source_reference_by_event",
            ),
        ]
        indexes = [
            models.Index(fields=["event", "user", "created_at"]),
            models.Index(fields=["provider", "provider_ref"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.user.username} - {self.amount_ucoin}"


class StaffCreditGrant(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="staff_credit_grants")
    client_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_credit_grants_received",
    )
    staff_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_credit_grants_made",
    )
    amount_ucoin = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(check=models.Q(amount_ucoin__gt=0), name="check_staff_credit_amount_positive"),
        ]
        indexes = [
            models.Index(fields=["event", "created_at"]),
            models.Index(fields=["client_user", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.client_user.username} - {self.amount_ucoin}"

# Create your models here.
