from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from commerce.models import CartItem as CommerceCartItem
from events.models import CampaignStatus, EventCampaign, EventMembership, EventUserGroup
from events.services import assign_group_to_user
from operations.models import StaffAuditLog
from stalls.models import (
    CatalogProduct,
    ItemNature,
    MapSpot,
    MapZone,
    ProductCategory,
    ProductSubcategory,
    Stall,
    StallAssignment,
    StallProduct,
    StockMode,
)


class CoreV2ViewsTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.event = EventCampaign.objects.create(
            code="test-2026",
            name="Evento test",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.category_food, _ = ProductCategory.objects.get_or_create(
            slug="alimento",
            defaults={"name": "Alimento", "sort_order": 1},
        )
        self.subcategory_snack, _ = ProductSubcategory.objects.get_or_create(
            slug="snack",
            defaults={
                "category": self.category_food,
                "name": "Snack",
                "sort_order": 1,
                "default_photo_variant": "combo",
                "default_image": "core/img/products/default-alimento.svg",
            },
        )

    def _build_stall(self, *, code="stall-a", name="Puesto A"):
        return Stall.objects.create(event=self.event, code=code, name=name, status="open")

    def test_menu_v2_marks_low_stock_products(self):
        client_user = self.user_model.objects.create_user(username="buyer", password="secret")
        stall = self._build_stall()
        catalog = CatalogProduct.objects.create(sku="snack-001", name="Snack")
        product = StallProduct.objects.create(
            event=self.event,
            stall=stall,
            catalog_product=catalog,
            display_name="Papas",
            item_nature=ItemNature.INVENTORIABLE,
            category=self.category_food,
            subcategory=self.subcategory_snack,
            price_ucoin=Decimal("30.00"),
            cost_ucoin=Decimal("12.00"),
            stock_mode=StockMode.FINITE,
            stock_qty=100,
            is_active=True,
        )
        product.stock_qty = 15
        product.save()

        self.client.login(username="buyer", password="secret")
        response = self.client.get(reverse("menu_alimentos"))

        self.assertEqual(response.status_code, 200)
        menu_stalls = response.context["menu_stalls"]
        self.assertEqual(len(menu_stalls), 1)
        self.assertTrue(menu_stalls[0]["items"][0]["is_low_stock"])

    def test_vendor_can_create_no_inventoriable_product(self):
        vendor = self.user_model.objects.create_user(username="vendor", password="secret")
        staff = self.user_model.objects.create_user(username="staff", password="secret")
        stall = self._build_stall(code="stall-b", name="Puesto B")
        zone = MapZone.objects.create(event=self.event, name="Zona B", sort_order=1)
        spot = MapSpot.objects.create(event=self.event, zone=zone, label="B-01", x=1, y=1)
        StallAssignment.objects.create(
            event=self.event,
            stall=stall,
            vendor_user=vendor,
            spot=spot,
            assigned_by_staff=staff,
        )
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor", password="secret")
        response = self.client.post(
            reverse("vendedor_productos"),
            {
                "action": "save_product",
                "display_name": "Servicio de recarga",
                "description": "Asistencia en caja",
                "item_nature": ItemNature.NO_INVENTORIABLE,
                "category_id": str(self.category_food.id),
                "subcategory_id": str(self.subcategory_snack.id),
                "price_ucoin": "20.00",
                "cost_ucoin": "5.00",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        product = StallProduct.objects.filter(event=self.event, stall=stall).first()
        self.assertIsNotNone(product)
        self.assertEqual(product.item_nature, ItemNature.NO_INVENTORIABLE)
        self.assertEqual(product.stock_mode, StockMode.UNLIMITED)
        self.assertIsNone(product.stock_qty)
        self.assertIsNone(product.low_stock_threshold)

    def test_menu_post_adds_product_to_v2_cart(self):
        client_user = self.user_model.objects.create_user(username="buyer2", password="secret")
        stall = self._build_stall(code="stall-c", name="Puesto C")
        catalog = CatalogProduct.objects.create(sku="drink-001", name="Bebida")
        product = StallProduct.objects.create(
            event=self.event,
            stall=stall,
            catalog_product=catalog,
            display_name="Agua fresca",
            item_nature=ItemNature.INVENTORIABLE,
            category=self.category_food,
            subcategory=self.subcategory_snack,
            price_ucoin=Decimal("18.00"),
            cost_ucoin=Decimal("8.00"),
            stock_mode=StockMode.FINITE,
            stock_qty=10,
            is_active=True,
        )

        self.client.login(username="buyer2", password="secret")
        response = self.client.post(
            reverse("menu_alimentos"),
            {"stall_product_id": str(product.id), "action": "add"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            CommerceCartItem.objects.filter(event=self.event, user=client_user, stall_product=product).exists()
        )


class StaffPanelAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.event = EventCampaign.objects.create(
            code="staff-2026",
            name="Evento staff",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.staff_user = self.user_model.objects.create_user(
            username="staff-user",
            email="staff@example.com",
            password="secret",
        )
        self.vendor_user = self.user_model.objects.create_user(
            username="vendor-user",
            email="vendor@example.com",
            password="secret",
        )
        self.client_user = self.user_model.objects.create_user(
            username="client-user",
            email="client@example.com",
            password="secret",
        )
        self.super_user = self.user_model.objects.create_superuser(
            username="root-user",
            email="root@example.com",
            password="secret",
        )
        for user in [self.staff_user, self.vendor_user, self.client_user, self.super_user]:
            EventMembership.objects.update_or_create(
                event=self.event,
                user=user,
                defaults={"profile_type": "comunidad", "matricula": f"MAT-{user.id}"},
            )

        assign_group_to_user(event=self.event, user=self.staff_user, group_name="staff")
        assign_group_to_user(event=self.event, user=self.vendor_user, group_name="vendedor")

    def test_vendor_can_access_vendor_panel(self):
        self.client.login(username="vendor-user", password="secret")
        response = self.client.get(reverse("vendedor"))
        self.assertEqual(response.status_code, 200)

    def test_staff_without_vendor_redirects_to_staff_panel(self):
        self.client.login(username="staff-user", password="secret")
        response = self.client.get(reverse("vendedor"))
        self.assertRedirects(response, reverse("staff_panel"))
        response_productos = self.client.get(reverse("vendedor_productos"))
        self.assertRedirects(response_productos, reverse("staff_panel"))
        response_ventas = self.client.get(reverse("vendedor_ventas"))
        self.assertRedirects(response_ventas, reverse("staff_panel"))
        response_mapa = self.client.get(reverse("vendedor_mapa"))
        self.assertRedirects(response_mapa, reverse("staff_panel"))

    def test_client_without_vendor_redirects_to_cliente(self):
        self.client.login(username="client-user", password="secret")
        response = self.client.get(reverse("vendedor"))
        self.assertRedirects(response, reverse("cliente"))

    def test_superuser_without_vendor_role_cannot_access_vendor_panel(self):
        self.client.login(username="root-user", password="secret")
        response = self.client.get(reverse("vendedor"))
        self.assertRedirects(response, reverse("cliente"))

    def test_dropdown_hides_vendor_for_staff_without_vendor_role(self):
        self.client.login(username="staff-user", password="secret")
        response = self.client.get(reverse("cliente"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/vendedor/" role="menuitem">Vendedor')
        self.assertContains(response, 'href="/staff/" role="menuitem">Staff')

    def test_dropdown_shows_vendor_for_vendor_user(self):
        self.client.login(username="vendor-user", password="secret")
        response = self.client.get(reverse("cliente"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/vendedor/" role="menuitem">Vendedor')

    def test_staff_panel_rejects_non_staff(self):
        self.client.login(username="client-user", password="secret")
        response = self.client.get(reverse("staff_panel"))
        self.assertRedirects(response, reverse("cliente"))

    def test_staff_panel_search_by_username_email_matricula(self):
        target_user = self.user_model.objects.create_user(
            username="search-me",
            email="search-me@example.com",
            password="secret",
        )
        EventMembership.objects.update_or_create(
            event=self.event,
            user=target_user,
            defaults={"profile_type": "comunidad", "matricula": "A01234567"},
        )
        self.client.login(username="staff-user", password="secret")

        response_username = self.client.get(reverse("staff_panel"), {"q": "search-me"})
        self.assertContains(response_username, "search-me")

        response_email = self.client.get(reverse("staff_panel"), {"q": "search-me@example.com"})
        self.assertContains(response_email, "search-me")

        response_matricula = self.client.get(reverse("staff_panel"), {"q": "A01234567"})
        self.assertContains(response_matricula, "search-me")

    def test_staff_can_grant_and_revoke_vendor_role_with_audit(self):
        self.client.login(username="staff-user", password="secret")
        response_grant = self.client.post(
            reverse("staff_panel"),
            {
                "action": "grant_role",
                "target_user_id": str(self.client_user.id),
                "group_name": "vendedor",
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response_grant.status_code, 200)
        self.assertTrue(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="vendedor").exists()
        )
        self.assertTrue(StaffAuditLog.objects.filter(event=self.event, action_type="grant_role").exists())

        response_revoke = self.client.post(
            reverse("staff_panel"),
            {
                "action": "revoke_role",
                "target_user_id": str(self.client_user.id),
                "group_name": "vendedor",
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response_revoke.status_code, 200)
        self.assertFalse(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="vendedor").exists()
        )
        self.assertTrue(StaffAuditLog.objects.filter(event=self.event, action_type="revoke_role").exists())

    def test_staff_cannot_revoke_own_staff_role(self):
        self.client.login(username="staff-user", password="secret")
        response = self.client.post(
            reverse("staff_panel"),
            {
                "action": "revoke_role",
                "target_user_id": str(self.staff_user.id),
                "group_name": "staff",
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EventUserGroup.objects.filter(event=self.event, user=self.staff_user, group__name="staff").exists()
        )

    def test_staff_can_assign_vendor_to_stall_and_spot(self):
        zone = MapZone.objects.create(event=self.event, name="Zona S", sort_order=1)
        spot = MapSpot.objects.create(event=self.event, zone=zone, label="S-01", x=0, y=0)
        stall = Stall.objects.create(event=self.event, code="staff-stall", name="Puesto Staff", status="open")

        self.client.login(username="staff-user", password="secret")
        response = self.client.post(
            reverse("staff_panel"),
            {
                "action": "assign_vendor",
                "vendor_user_id": str(self.vendor_user.id),
                "stall_id": str(stall.id),
                "spot_id": str(spot.id),
                "next_query": "",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        assignment = StallAssignment.objects.filter(event=self.event, vendor_user=self.vendor_user).first()
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.stall_id, stall.id)
        self.assertEqual(assignment.spot_id, spot.id)
        self.assertTrue(StaffAuditLog.objects.filter(event=self.event, action_type="assign_vendor").exists())
