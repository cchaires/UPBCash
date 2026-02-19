import hashlib
import secrets
from decimal import Decimal
from datetime import timedelta

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from accounting.services import WalletService
from events.services import assert_event_writable
from stalls.models import CatalogProduct, Stall, StallProduct, StockMode, StockMovement, StockMovementType

from .models import (
    CartItem,
    DeliveryAction,
    OrderDeliveryLog,
    OrderQrToken,
    OrderStatus,
    SalesOrder,
    SalesOrderItem,
)


def _money(amount):
    return Decimal(amount).quantize(Decimal("0.01"))


def _hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


class CheckoutService:
    @classmethod
    def _next_order_number(cls, *, event):
        # Lock campaign row to serialize per-event numbering.
        event.__class__.objects.select_for_update().filter(pk=event.pk).exists()
        max_number = SalesOrder.objects.filter(event=event).aggregate(max_value=Max("order_number"))["max_value"] or 0
        return max_number + 1

    @classmethod
    def create_order_qr_token(cls, *, order, ttl_minutes=120):
        raw_token = secrets.token_urlsafe(24)
        hashed = _hash_token(raw_token)
        OrderQrToken.objects.filter(order=order, is_active=True).update(is_active=False)
        OrderQrToken.objects.create(
            order=order,
            token_hash=hashed,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
            is_active=True,
        )
        return raw_token

    @classmethod
    def _validate_stock_and_apply(cls, *, cart_items, actor_user):
        for cart_item in cart_items:
            stall_product = cart_item.stall_product
            if stall_product.stock_mode == StockMode.UNLIMITED:
                continue
            if stall_product.stock_qty is None or stall_product.stock_qty < cart_item.quantity:
                raise ValueError(
                    f"Stock insuficiente para {stall_product.display_name}. "
                    f"Disponible: {stall_product.stock_qty or 0}, solicitado: {cart_item.quantity}."
                )
            stall_product.stock_qty -= cart_item.quantity
            stall_product.save(update_fields=["stock_qty", "updated_at"])
            StockMovement.objects.create(
                event=cart_item.event,
                stall_product=stall_product,
                movement_type=StockMovementType.SALE,
                quantity_delta=-cart_item.quantity,
                note="Descuento por checkout",
                created_by_user=actor_user,
            )

    @classmethod
    @transaction.atomic
    def checkout_cart(cls, *, event, user):
        assert_event_writable(event)
        cart_items = list(
            CartItem.objects.select_for_update()
            .select_related("stall_product", "stall_product__stall")
            .filter(event=event, user=user)
            .order_by("id")
        )
        if not cart_items:
            raise ValueError("No hay productos en el carrito.")

        stall_ids = {item.stall_product.stall_id for item in cart_items}
        if len(stall_ids) != 1:
            raise ValueError("El carrito solo puede contener productos de un puesto por checkout.")

        subtotal = Decimal("0.00")
        for item in cart_items:
            subtotal += _money(item.stall_product.price_ucoin * item.quantity)
        total = _money(subtotal)

        if WalletService.get_balance(event=event, user=user) < total:
            raise ValueError("Saldo insuficiente.")

        order = SalesOrder.objects.create(
            event=event,
            buyer_user=user,
            stall_id=next(iter(stall_ids)),
            order_number=cls._next_order_number(event=event),
            status=OrderStatus.PAID,
            subtotal_ucoin=subtotal,
            total_ucoin=total,
            paid_at=timezone.now(),
        )
        SalesOrderItem.objects.bulk_create(
            [
                SalesOrderItem(
                    order=order,
                    stall_product=item.stall_product,
                    product_name_snapshot=item.stall_product.display_name,
                    unit_price_snapshot=item.stall_product.price_ucoin,
                    quantity=item.quantity,
                    line_total_snapshot=_money(item.stall_product.price_ucoin * item.quantity),
                )
                for item in cart_items
            ]
        )

        cls._validate_stock_and_apply(cart_items=cart_items, actor_user=user)
        WalletService.record_purchase(
            event=event,
            user=user,
            amount_ucoin=total,
            reference_model="sales_order",
            reference_id=order.id,
            created_by_user=user,
        )

        CartItem.objects.filter(id__in=[item.id for item in cart_items]).delete()
        qr_token = cls.create_order_qr_token(order=order)
        return order, qr_token

    @classmethod
    @transaction.atomic
    def mirror_legacy_purchase(
        cls,
        *,
        event,
        user,
        legacy_purchase_id,
        amount_ucoin,
        legacy_cart_rows,
    ):
        assert_event_writable(event)
        source_reference = f"legacy_purchase:{legacy_purchase_id}"
        existing = SalesOrder.objects.filter(event=event, source_reference=source_reference).first()
        if existing:
            return existing

        legacy_stall, _ = Stall.objects.get_or_create(
            event=event,
            code="legacy-stall",
            defaults={"name": "Puesto legado", "status": "open"},
        )
        order = SalesOrder.objects.create(
            event=event,
            buyer_user=user,
            stall=legacy_stall,
            order_number=cls._next_order_number(event=event),
            status=OrderStatus.PAID,
            subtotal_ucoin=_money(amount_ucoin),
            total_ucoin=_money(amount_ucoin),
            source_reference=source_reference,
            paid_at=timezone.now(),
        )

        items_to_create = []
        for row in legacy_cart_rows:
            code = row.get("code", "")
            name = row.get("name", "")
            price = _money(row.get("unit_price", "0"))
            quantity = int(row.get("quantity", 0))
            if quantity <= 0:
                continue
            catalog_product, _ = CatalogProduct.objects.get_or_create(
                sku=f"legacy-{code or name.lower().replace(' ', '-')}",
                defaults={"name": name or code, "description": "", "is_active": True},
            )
            stall_product, _ = StallProduct.objects.get_or_create(
                event=event,
                stall=legacy_stall,
                catalog_product=catalog_product,
                defaults={
                    "display_name": name or catalog_product.name,
                    "price_ucoin": price,
                    "stock_mode": StockMode.UNLIMITED,
                    "stock_qty": None,
                    "low_stock_threshold": None,
                },
            )
            items_to_create.append(
                SalesOrderItem(
                    order=order,
                    stall_product=stall_product,
                    product_name_snapshot=name or stall_product.display_name,
                    unit_price_snapshot=price,
                    quantity=quantity,
                    line_total_snapshot=_money(price * quantity),
                )
            )
        if items_to_create:
            SalesOrderItem.objects.bulk_create(items_to_create)

        cls.create_order_qr_token(order=order)
        return order


class FulfillmentService:
    @classmethod
    @transaction.atomic
    def verify_qr_and_deliver(cls, *, order, raw_token, actor_user):
        active_token = (
            OrderQrToken.objects.select_for_update()
            .filter(order=order, is_active=True, expires_at__gt=timezone.now())
            .order_by("-created_at")
            .first()
        )
        if not raw_token or not active_token or active_token.token_hash != _hash_token(raw_token):
            OrderDeliveryLog.objects.create(
                order=order,
                action=DeliveryAction.SCAN_FAIL,
                performed_by_user=actor_user,
                notes="Token invalido o expirado.",
            )
            return False

        active_token.is_active = False
        active_token.save(update_fields=["is_active"])
        OrderDeliveryLog.objects.create(
            order=order,
            action=DeliveryAction.SCAN_OK,
            performed_by_user=actor_user,
            notes="Token valido.",
        )

        order.status = OrderStatus.DELIVERED
        order.delivered_at = timezone.now()
        order.save(update_fields=["status", "delivered_at"])
        OrderDeliveryLog.objects.create(
            order=order,
            action=DeliveryAction.MARK_DELIVERED,
            performed_by_user=actor_user,
            notes="Entrega total confirmada via QR.",
        )
        return True
