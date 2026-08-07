from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounting.services import WalletService
from events.models import CampaignStatus, EventCampaign
from events.services import assign_group_to_user
from operations.services import StaffOpsService
from stalls.models import CatalogProduct, MapSpot, MapZone, Stall, StallProduct, StockMode

from .models import CartItem, OrderStatus
from .services import CheckoutService, FulfillmentService


class MarkOrderDeliveredTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.event = EventCampaign.objects.create(
            code="camp-deliver-2026",
            name="Campana entrega 2026",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.staff = self.user_model.objects.create_user(username="staff-deliver", password="secret")
        assign_group_to_user(event=self.event, user=self.staff, group_name="staff")

        self.vendor = self.user_model.objects.create_user(username="vendor-deliver", password="secret")
        zone = MapZone.objects.create(event=self.event, name="Zona D", sort_order=1)
        spot = MapSpot.objects.create(event=self.event, zone=zone, label="D-01", x=0, y=0)
        self.stall = Stall.objects.create(event=self.event, code="stall-d", name="Puesto D", status="open")
        StaffOpsService.assign_vendor(
            event=self.event, staff_user=self.staff, vendor_user=self.vendor, stall=self.stall, spot=spot
        )

        self.buyer = self.user_model.objects.create_user(username="buyer-deliver", password="secret")
        product = CatalogProduct.objects.create(sku="taco-deliver-001", name="Taco entrega")
        self.stall_product = StallProduct.objects.create(
            event=self.event,
            stall=self.stall,
            catalog_product=product,
            display_name="Taco de prueba",
            price_ucoin=Decimal("20.00"),
            stock_mode=StockMode.FINITE,
            stock_qty=10,
            low_stock_threshold=2,
            is_active=True,
        )
        WalletService.set_balance(event=self.event, user=self.buyer, balance=Decimal("100.00"))

        self.client_user = self.user_model.objects.create_user(username="client-deliver", password="secret")

    def _create_paid_order(self):
        CartItem.objects.create(event=self.event, user=self.buyer, stall_product=self.stall_product, quantity=1)
        order, _qr_token = CheckoutService.checkout_cart(event=self.event, user=self.buyer)
        return order

    def test_vendor_can_mark_order_delivered_manually(self):
        order = self._create_paid_order()
        self.assertEqual(order.status, OrderStatus.PAID)

        self.client.login(username="vendor-deliver", password="secret")
        response = self.client.post(reverse("api_mark_order_delivered", args=[order.id]))

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DELIVERED)
        self.assertIsNotNone(order.delivered_at)
        self.assertTrue(order.delivery_logs.filter(action="mark_delivered").exists())

    def test_marking_delivered_twice_is_idempotent(self):
        order = self._create_paid_order()
        FulfillmentService.mark_delivered_manually(order=order, actor_user=self.vendor)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DELIVERED)

        # Segunda llamada no debe fallar ni duplicar el log.
        FulfillmentService.mark_delivered_manually(order=order, actor_user=self.vendor)
        self.assertEqual(order.delivery_logs.filter(action="mark_delivered").count(), 1)

    def test_cannot_deliver_cancelled_order(self):
        order = self._create_paid_order()
        order.status = OrderStatus.CANCELLED
        order.save(update_fields=["status"])

        with self.assertRaises(ValueError):
            FulfillmentService.mark_delivered_manually(order=order, actor_user=self.vendor)

    def test_client_without_permission_cannot_mark_delivered(self):
        order = self._create_paid_order()

        self.client.login(username="client-deliver", password="secret")
        response = self.client.post(reverse("api_mark_order_delivered", args=[order.id]))

        self.assertEqual(response.status_code, 403)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.PAID)
