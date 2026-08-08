from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.test import TestCase

from accounting.services import WalletService
from commerce.models import CartItem, OrderStatus, SalesOrder, SalesOrderItem
from commerce.services import CheckoutService, FulfillmentService
from events.models import CampaignStatus, EventCampaign, EventMembership, EventUserGroup
from events.services import assign_group_to_user
from operations import reports
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

        topup = StaffOpsService.grant_ucoins(
            event=self.event,
            staff_user=staff,
            client_user=client,
            amount_ucoin=Decimal("40.00"),
            reason="Pago en efectivo",
        )
        self.assertIsNotNone(topup.id)
        self.assertEqual(topup.reason, "Pago en efectivo")
        self.assertEqual(WalletService.get_balance(event=self.event, user=client), Decimal("40.00"))

    def test_purchase_idempotency_does_not_double_discount_balance(self):
        buyer = self.user_model.objects.create_user(username="buyer-idem", password="secret")
        WalletService.set_balance(event=self.event, user=buyer, balance=Decimal("100.00"))

        # reference_object solo necesita tener un pk estable entre ambas llamadas
        # para que la idempotency_key coincida; se usa self.event como stand-in.
        WalletService.record_purchase_mirror(
            event=self.event,
            user=buyer,
            amount_ucoin=Decimal("15.00"),
            reference_object=self.event,
            idempotency_ref_label="sales_order",
            created_by_user=buyer,
        )
        WalletService.record_purchase_mirror(
            event=self.event,
            user=buyer,
            amount_ucoin=Decimal("15.00"),
            reference_object=self.event,
            idempotency_ref_label="sales_order",
            created_by_user=buyer,
        )
        self.assertEqual(WalletService.get_balance(event=self.event, user=buyer), Decimal("85.00"))


class AdminReportsTests(TestCase):
    """Cubre la capa de consultas de `operations.reports` y las vistas de admin.

    El escenario sembrado es deliberadamente asimetrico para que los rankings
    tengan un orden verificable:

    - Puesto A vende 2 tacos (25 c/u) + 3 aguas (10 c/u) = 80 UC en una orden.
    - Puesto B vende 1 taco B (40 c/u) = 40 UC en una orden.
    - Puesto A tiene ademas una orden cancelada de 500 UC que no debe contar.
    """

    def setUp(self):
        self.event = EventCampaign.objects.create(
            code="rep-2026",
            name="Reportes 2026",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.user_model = get_user_model()
        self.admin = self.user_model.objects.create_superuser(username="root", password="secret")
        self.buyer = self.user_model.objects.create_user(username="compradora", password="secret")

        self.stall_a = Stall.objects.create(event=self.event, code="a", name="Puesto A", status="open")
        self.stall_b = Stall.objects.create(event=self.event, code="b", name="Puesto B", status="open")

        self.taco = self._make_product(self.stall_a, "taco-a", "Taco al pastor", price="25.00", cost="10.00", stock=50)
        self.agua = self._make_product(self.stall_a, "agua-a", "Agua de horchata", price="10.00", cost="4.00", stock=50)
        self.taco_b = self._make_product(self.stall_b, "taco-b", "Taco de suadero", price="40.00", cost="15.00", stock=50)

        WalletService.set_balance(event=self.event, user=self.buyer, balance=Decimal("1000.00"))
        self.order_a = self._checkout({self.taco: 2, self.agua: 3})
        self.order_b = self._checkout({self.taco_b: 1})
        self.cancelled_order = SalesOrder.objects.create(
            event=self.event,
            buyer_user=self.buyer,
            stall=self.stall_a,
            order_number=999,
            status=OrderStatus.CANCELLED,
            subtotal_ucoin=Decimal("500.00"),
            total_ucoin=Decimal("500.00"),
        )
        SalesOrderItem.objects.create(
            order=self.cancelled_order,
            stall_product=self.taco,
            product_name_snapshot=self.taco.display_name,
            unit_price_snapshot=Decimal("25.00"),
            quantity=20,
            line_total_snapshot=Decimal("500.00"),
        )

    def _make_product(self, stall, sku, name, *, price, cost, stock):
        catalog = CatalogProduct.objects.create(sku=sku, name=name)
        return StallProduct.objects.create(
            event=self.event,
            stall=stall,
            catalog_product=catalog,
            display_name=name,
            price_ucoin=Decimal(price),
            cost_ucoin=Decimal(cost),
            stock_mode=StockMode.FINITE,
            stock_qty=stock,
            is_active=True,
        )

    def _checkout(self, quantities_by_product):
        for product, quantity in quantities_by_product.items():
            CartItem.objects.create(
                event=self.event,
                user=self.buyer,
                stall_product=product,
                quantity=quantity,
            )
        order, _token = CheckoutService.checkout_cart(event=self.event, user=self.buyer)
        return order

    def test_sales_by_stall_ranks_by_revenue_without_join_inflation(self):
        # Regresion: anotar sumas de ordenes y de lineas en un mismo queryset
        # multiplicaria el ingreso del puesto A por sus 2 lineas de venta.
        rows = reports.sales_by_stall(event=self.event)
        by_name = {row["stall_name"]: row for row in rows}

        self.assertEqual([row["stall_name"] for row in rows], ["Puesto A", "Puesto B"])
        self.assertEqual(by_name["Puesto A"]["revenue"], Decimal("80.00"))
        self.assertEqual(by_name["Puesto A"]["orders"], 1)
        self.assertEqual(by_name["Puesto A"]["units"], 5)
        self.assertEqual(by_name["Puesto B"]["revenue"], Decimal("40.00"))
        self.assertEqual(by_name["Puesto B"]["units"], 1)

    def test_sales_by_stall_excludes_cancelled_orders(self):
        by_name = {row["stall_name"]: row for row in reports.sales_by_stall(event=self.event)}
        self.assertEqual(by_name["Puesto A"]["revenue"], Decimal("80.00"))
        self.assertEqual(by_name["Puesto A"]["cancelled_orders"], 1)

    def test_sales_kpis_totals(self):
        kpis = reports.sales_kpis(event=self.event)
        self.assertEqual(kpis["revenue"], Decimal("120.00"))
        self.assertEqual(kpis["orders"], 2)
        self.assertEqual(kpis["units"], 6)
        self.assertEqual(kpis["buyers"], 1)
        self.assertEqual(kpis["average_ticket"], Decimal("60.00"))
        self.assertEqual(kpis["cancelled_orders"], 1)
        self.assertEqual(kpis["cancelled_amount"], Decimal("500.00"))
        # (25-10)*2 + (10-4)*3 + (40-15)*1
        self.assertEqual(kpis["margin"], Decimal("73.00"))

    def test_top_products_orders_by_units(self):
        rows = reports.top_products(event=self.event)
        self.assertEqual(
            [(row["product_name"], row["units"], row["revenue"]) for row in rows],
            [
                ("Agua de horchata", 3, Decimal("30.00")),
                ("Taco al pastor", 2, Decimal("50.00")),
                ("Taco de suadero", 1, Decimal("40.00")),
            ],
        )

    def test_products_without_sales_lists_untouched_catalog(self):
        unsold = self._make_product(self.stall_b, "flan-b", "Flan", price="15.00", cost="5.00", stock=10)
        rows = reports.products_without_sales(event=self.event)
        self.assertEqual([row["product_name"] for row in rows], [unsold.display_name])

    def test_wallet_summary_balances_topups_against_spending(self):
        summary = reports.wallet_summary(event=self.event)
        self.assertEqual(summary["spent"], Decimal("120.00"))
        self.assertEqual(summary["outstanding"], Decimal("880.00"))
        # `set_balance` no registra un TopupRecord, asi que lo recargado es cero
        # y el descuadre expone justamente ese saldo inyectado en la prueba.
        self.assertEqual(summary["topped_up"], Decimal("0.00"))
        self.assertEqual(summary["unreconciled"], Decimal("1000.00"))

    def test_top_buyers_aggregates_spending(self):
        rows = reports.top_buyers(event=self.event)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["username"], "compradora")
        self.assertEqual(rows[0]["spent"], Decimal("120.00"))
        self.assertEqual(rows[0]["orders"], 2)
        self.assertEqual(rows[0]["units"], 6)

    def test_fulfillment_summary_counts_pending_orders(self):
        summary = reports.fulfillment_summary(event=self.event)
        self.assertEqual(summary["pending"], 2)
        self.assertEqual(summary["pending_amount"], Decimal("120.00"))
        self.assertEqual(summary["delivered"], 0)
        self.assertEqual(summary["cancelled"], 1)

    def test_report_functions_tolerate_missing_event(self):
        self.assertEqual(reports.sales_by_stall(event=None), [])
        self.assertEqual(reports.sales_kpis(event=None)["revenue"], Decimal("0.00"))
        self.assertEqual(reports.operations_snapshot(event=None)["spots_total"], 0)

    def test_admin_report_pages_render_for_superuser(self):
        self.client.force_login(self.admin)
        for url_name in (
            "admin_inicio",
            "admin_reportes_ventas",
            "admin_reportes_productos",
            "admin_reportes_clientes",
            "admin_reportes_operacion",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_admin_reports_reject_non_admin(self):
        self.client.force_login(self.buyer)
        response = self.client.get(reverse("admin_reportes_ventas"))
        self.assertEqual(response.status_code, 302)

    def test_admin_reports_accept_explicit_event(self):
        other_event = EventCampaign.objects.create(
            code="rep-2025",
            name="Reportes 2025",
            starts_at=timezone.now() - timezone.timedelta(days=40),
            ends_at=timezone.now() - timezone.timedelta(days=30),
            timezone="America/Mexico_City",
            status=CampaignStatus.CLOSED,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_reportes_ventas"), {"event": other_event.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"], other_event)
        self.assertEqual(response.context["stall_rows"], [])

    def test_csv_export_returns_report_rows(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_reportes_export", args=["ventas"]))
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment; filename=", response["Content-Disposition"])

        body = response.content.decode("utf-8-sig")
        lines = [line for line in body.splitlines() if line]
        self.assertTrue(lines[0].startswith("Posicion,Codigo quiosco,Quiosco"))
        self.assertIn("Puesto A", lines[1])
        self.assertIn("80.00", lines[1])

    def test_csv_export_rejects_unknown_report(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("admin_reportes_export", args=["inexistente"]))
        self.assertEqual(response.status_code, 404)

# Create your tests here.
