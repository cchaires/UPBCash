from django.conf import settings
from django.db import models


class MapSpotStatus(models.TextChoices):
    AVAILABLE = "available", "Disponible"
    ASSIGNED = "assigned", "Asignado"
    BLOCKED = "blocked", "Bloqueado"


class StallStatus(models.TextChoices):
    DRAFT = "draft", "Borrador"
    OPEN = "open", "Abierto"
    PAUSED = "paused", "Pausado"
    CLOSED = "closed", "Cerrado"


class StockMode(models.TextChoices):
    FINITE = "finite", "Finito"
    UNLIMITED = "unlimited", "Ilimitado"


class StockMovementType(models.TextChoices):
    SET = "set", "Ajuste inicial"
    INCREASE = "increase", "Incremento"
    DECREASE = "decrease", "Decremento"
    ADJUST = "adjust", "Ajuste manual"
    SALE = "sale", "Venta"


class MapZone(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="map_zones")
    name = models.CharField(max_length=120)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "name"], name="uniq_zone_name_by_event"),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.name}"


class MapSpot(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="map_spots")
    zone = models.ForeignKey(MapZone, on_delete=models.CASCADE, related_name="spots")
    label = models.CharField(max_length=64)
    x = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    y = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    status = models.CharField(max_length=16, choices=MapSpotStatus.choices, default=MapSpotStatus.AVAILABLE)

    class Meta:
        ordering = ["zone__sort_order", "label", "id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "label"], name="uniq_spot_label_by_event"),
        ]
        indexes = [
            models.Index(fields=["event", "status"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.label}"


class Stall(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="stalls")
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=StallStatus.choices, default=StallStatus.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "code"], name="uniq_stall_code_by_event"),
        ]
        indexes = [
            models.Index(fields=["event", "status"]),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.name}"


class StallAssignment(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="stall_assignments")
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, related_name="assignments")
    vendor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vendor_stall_assignments",
    )
    spot = models.OneToOneField(MapSpot, on_delete=models.PROTECT, related_name="stall_assignment")
    assigned_by_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="staff_stall_assignments",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-assigned_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["event", "vendor_user"], name="uniq_vendor_per_event"),
            models.UniqueConstraint(fields=["event", "spot"], name="uniq_spot_assignment_per_event"),
            models.UniqueConstraint(fields=["event", "stall"], name="uniq_stall_assignment_per_event"),
        ]

    def __str__(self):
        return f"{self.event.code} - {self.vendor_user.username} -> {self.stall.code}"


class CatalogProduct(models.Model):
    sku = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=240, blank=True)
    photo_variant = models.CharField(max_length=32, default="taco")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class StallProduct(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="stall_products")
    stall = models.ForeignKey(Stall, on_delete=models.CASCADE, related_name="products")
    catalog_product = models.ForeignKey(CatalogProduct, on_delete=models.PROTECT, related_name="stall_products")
    display_name = models.CharField(max_length=120)
    price_ucoin = models.DecimalField(max_digits=10, decimal_places=2)
    stock_mode = models.CharField(max_length=16, choices=StockMode.choices, default=StockMode.FINITE)
    stock_qty = models.PositiveIntegerField(null=True, blank=True)
    low_stock_threshold = models.PositiveIntegerField(null=True, blank=True)
    is_sold_out_manual = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stall__name", "display_name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "stall", "catalog_product"],
                name="uniq_stall_catalog_product_by_event",
            ),
            models.CheckConstraint(check=models.Q(price_ucoin__gte=0), name="check_stall_product_price_nonnegative"),
            models.CheckConstraint(
                check=(
                    models.Q(stock_mode=StockMode.UNLIMITED, stock_qty__isnull=True)
                    | models.Q(stock_mode=StockMode.FINITE, stock_qty__isnull=False, stock_qty__gte=0)
                ),
                name="check_stall_product_stock_consistency",
            ),
            models.CheckConstraint(
                check=models.Q(low_stock_threshold__isnull=True) | models.Q(low_stock_threshold__gte=0),
                name="check_low_stock_threshold_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["event", "stall", "is_active"]),
            models.Index(fields=["event", "is_active"]),
        ]

    def __str__(self):
        return f"{self.stall.name} - {self.display_name}"

    @property
    def is_low_stock(self):
        if self.stock_mode != StockMode.FINITE:
            return False
        if self.stock_qty is None or self.low_stock_threshold is None:
            return False
        return self.stock_qty <= self.low_stock_threshold


class StockMovement(models.Model):
    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="stock_movements")
    stall_product = models.ForeignKey(StallProduct, on_delete=models.CASCADE, related_name="stock_movements")
    movement_type = models.CharField(max_length=16, choices=StockMovementType.choices)
    quantity_delta = models.IntegerField()
    note = models.CharField(max_length=255, blank=True)
    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["event", "created_at"]),
            models.Index(fields=["stall_product", "created_at"]),
        ]

    def __str__(self):
        return f"{self.stall_product.display_name} ({self.quantity_delta})"

# Create your models here.
