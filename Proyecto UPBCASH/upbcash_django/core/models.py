import uuid

from django.contrib.auth.models import User
from django.db import models


def generate_recharge_code():
    return f"RCG-{uuid.uuid4().hex[:6].upper()}"


class UserProfile(models.Model):
    ACCOUNT_TYPE_CHOICES = [
        ("comunidad", "Comunidad"),
        ("invitado", "Invitado"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    matricula = models.CharField(max_length=64, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    invited_by_email = models.EmailField(blank=True)
    invited_by_matricula = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} ({self.account_type})"


class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="wallet")
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}: {self.balance}"


class WalletLedger(models.Model):
    MOVEMENT_CHOICES = [
        ("recharge", "Recarga"),
        ("purchase", "Compra"),
        ("refund", "Reembolso"),
        ("adjustment", "Ajuste"),
    ]

    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name="ledger_entries")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallet_ledger_entries")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference_type = models.CharField(max_length=32, blank=True)
    reference_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["movement_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} {self.movement_type} {self.amount}"


class Recharge(models.Model):
    STATUS_CHOICES = [
        ("success", "Success"),
        ("pending", "Pending"),
        ("failed", "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recharges")
    code = models.CharField(max_length=16, unique=True, default=generate_recharge_code)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=32, default="PayPal")
    card_label = models.CharField(max_length=64, default="Tarjeta")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="success")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.user.username}"


class RechargeIssue(models.Model):
    recharge = models.ForeignKey(Recharge, on_delete=models.CASCADE, related_name="issues")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="recharge_issues")
    email = models.EmailField()
    reason = models.CharField(max_length=120)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Issue {self.recharge.code} - {self.user.username}"


class FoodItem(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    photo_variant = models.CharField(max_length=32, default="taco")
    stall_label = models.CharField(max_length=120, default="Puesto general")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="cart_items")
    food_item = models.ForeignKey(FoodItem, on_delete=models.CASCADE, related_name="cart_items")
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "food_item"], name="unique_user_food_item")
        ]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} - {self.food_item.name} x{self.quantity}"

    @property
    def line_total(self):
        return self.food_item.price * self.quantity


class Purchase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchases")
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Compra {self.id} - {self.user.username}"


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    food_code = models.CharField(max_length=32)
    food_name = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    stall_label = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.food_name} x{self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity
