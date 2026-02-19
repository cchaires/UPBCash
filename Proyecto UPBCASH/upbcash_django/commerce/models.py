from django.conf import settings
from django.db import models


class OrderStatus(models.TextChoices):
    PAID = "paid", "Pagado"
    PREPARING = "preparing", "Preparando"
    READY = "ready", "Listo"
    PARTIALLY_DELIVERED = "partially_delivered", "Entrega parcial"
    DELIVERED = "delivered", "Entregado"
    CANCELLED = "cancelled", "Cancelado"


class DeliveryAction(models.TextChoices):
    SCAN_OK = "scan_ok", "QR valido"
    SCAN_FAIL = "scan_fail", "QR invalido"
    MARK_PARTIAL = "mark_partial", "Marcar parcial"
    MARK_DELIVERED = "mark_delivered", "Marcar entregado"
    REOPEN = "reopen", "Reabrir"


class CartItem(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="cart_items_v2")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items_v2")
    stall_product = models.ForeignKey("stalls.StallProduct", on_delete=models.CASCADE, related_name="cart_items_v2")
    quantity = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user", "stall_product"],
                name="uniq_cart_item_event_user_stall_product",
            ),
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="check_cart_item_qty_positive"),
        ]
        indexes = [
            models.Index(fields=["event", "user", "updated_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.user.username} - {self.stall_product.display_name}"


class SalesOrder(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="sales_orders")
    buyer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sales_orders_as_buyer",
    )
    stall = models.ForeignKey("stalls.Stall", on_delete=models.PROTECT, related_name="sales_orders")
    order_number = models.PositiveBigIntegerField()
    status = models.CharField(max_length=24, choices=OrderStatus.choices, default=OrderStatus.PAID)
    subtotal_ucoin = models.DecimalField(max_digits=12, decimal_places=2)
    total_ucoin = models.DecimalField(max_digits=12, decimal_places=2)
    source_reference = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "order_number"], name="uniq_order_number_by_event"),
            models.UniqueConstraint(
                fields=["event", "source_reference"],
                condition=~models.Q(source_reference=""),
                name="uniq_nonempty_source_reference_by_event",
            ),
            models.CheckConstraint(check=models.Q(subtotal_ucoin__gte=0), name="check_sales_order_subtotal_nonnegative"),
            models.CheckConstraint(check=models.Q(total_ucoin__gte=0), name="check_sales_order_total_nonnegative"),
        ]
        indexes = [
            models.Index(fields=["event", "buyer_user", "created_at"]),
            models.Index(fields=["event", "stall", "created_at"]),
            models.Index(fields=["event", "status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.event.code} #{self.order_number}"


class SalesOrderItem(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items")
    stall_product = models.ForeignKey(
        "stalls.StallProduct",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales_order_items",
    )
    product_name_snapshot = models.CharField(max_length=120)
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)
    line_total_snapshot = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="check_sales_order_item_qty_positive"),
            models.CheckConstraint(
                check=models.Q(unit_price_snapshot__gte=0),
                name="check_sales_order_item_unit_price_nonnegative",
            ),
            models.CheckConstraint(
                check=models.Q(line_total_snapshot__gte=0),
                name="check_sales_order_item_line_total_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.product_name_snapshot} x{self.quantity}"


class OrderQrToken(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="qr_tokens")
    token_hash = models.CharField(max_length=64, db_index=True)
    expires_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["order", "is_active", "expires_at"]),
        ]

    def __str__(self):
        return f"QR {self.order_id}"


class OrderDeliveryLog(models.Model):
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="delivery_logs")
    action = models.CharField(max_length=24, choices=DeliveryAction.choices)
    performed_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_delivery_logs",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["order", "created_at"]),
        ]

    def __str__(self):
        return f"{self.order_id} - {self.action}"

# Create your models here.
