from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import TestCase

from accounting.services import WalletService
from commerce.models import CartItem, OrderStatus
from commerce.services import CheckoutService, FulfillmentService
from events.models import CampaignStatus, EventCampaign, EventMembership, EventUserGroup
from events.services import assign_group_to_user
from operations.services import StaffOpsService
from stalls.models import CatalogProduct, MapSpot, MapZone, Stall, StallProduct, StockMode


class RedesignFlowTests(TestCase):
    def setUp(self):
        self.event = EventCampaign.objects.create(
            code="camp-2026",
            name="Campana 2026",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.user_model = get_user_model()

    def test_new_user_gets_client_membership_by_default(self):
        user = self.user_model.objects.create_user(username="cliente1", password="secret")
        membership = EventMembership.objects.filter(event=self.event, user=user).first()
        self.assertIsNotNone(membership)
        client_group_assignment = EventUserGroup.objects.filter(
            event=self.event,
            user=user,
            group__name="cliente",
        ).exists()
        self.assertTrue(client_group_assignment)

    def test_checkout_and_qr_delivery(self):
        buyer = self.user_model.objects.create_user(username="buyer", password="secret")
        zone = MapZone.objects.create(event=self.event, name="Zona A", sort_order=1)
        spot = MapSpot.objects.create(event=self.event, zone=zone, label="A-01", x=1, y=1)
        stall = Stall.objects.create(event=self.event, code="stall-a", name="Puesto A", status="open")
        staff = self.user_model.objects.create_user(username="staff1", password="secret")
        assign_group_to_user(event=self.event, user=staff, group_name="staff")
        StaffOpsService.assign_vendor(
            event=self.event,
            staff_user=staff,
            vendor_user=staff,
            stall=stall,
            spot=spot,
        )
        product = CatalogProduct.objects.create(sku="taco-001", name="Taco")
        stall_product = StallProduct.objects.create(
            event=self.event,
            stall=stall,
            catalog_product=product,
            display_name="Taco al pastor",
            price_ucoin=Decimal("25.00"),
            stock_mode=StockMode.FINITE,
            stock_qty=20,
            low_stock_threshold=10,
            is_active=True,
        )
        WalletService.set_balance(event=self.event, user=buyer, balance=Decimal("100.00"))
        CartItem.objects.create(event=self.event, user=buyer, stall_product=stall_product, quantity=2)

        order, raw_token = CheckoutService.checkout_cart(event=self.event, user=buyer)
        self.assertEqual(order.status, OrderStatus.PAID)
        stall_product.refresh_from_db()
        self.assertEqual(stall_product.stock_qty, 18)
        self.assertEqual(WalletService.get_balance(event=self.event, user=buyer), Decimal("50.00"))

        is_valid = FulfillmentService.verify_qr_and_deliver(order=order, raw_token=raw_token, actor_user=staff)
        self.assertTrue(is_valid)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.DELIVERED)

    def test_staff_can_grant_ucoins(self):
        staff = self.user_model.objects.create_user(username="staff2", password="secret")
        client = self.user_model.objects.create_user(username="client2", password="secret")
        assign_group_to_user(event=self.event, user=staff, group_name="staff")

        topup, grant = StaffOpsService.grant_ucoins(
            event=self.event,
            staff_user=staff,
            client_user=client,
            amount_ucoin=Decimal("40.00"),
            reason="Pago en efectivo",
        )
        self.assertIsNotNone(topup.id)
        self.assertIsNotNone(grant.id)
        self.assertEqual(WalletService.get_balance(event=self.event, user=client), Decimal("40.00"))

    def test_purchase_idempotency_does_not_double_discount_balance(self):
        buyer = self.user_model.objects.create_user(username="buyer-idem", password="secret")
        WalletService.set_balance(event=self.event, user=buyer, balance=Decimal("100.00"))

        WalletService.record_purchase_mirror(
            event=self.event,
            user=buyer,
            amount_ucoin=Decimal("15.00"),
            reference_model="sales_order",
            reference_id=999,
            created_by_user=buyer,
        )
        WalletService.record_purchase_mirror(
            event=self.event,
            user=buyer,
            amount_ucoin=Decimal("15.00"),
            reference_model="sales_order",
            reference_id=999,
            created_by_user=buyer,
        )
        self.assertEqual(WalletService.get_balance(event=self.event, user=buyer), Decimal("85.00"))

# Create your tests here.
