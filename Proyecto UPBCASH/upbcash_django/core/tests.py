from decimal import Decimal

from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
    StallLocationAssignment,
    StallProduct,
    StallVendorMembership,
    StallVendorRole,
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

    def _assign_stall_to_spot(self, *, stall, staff_user):
        zone = MapZone.objects.create(event=self.event, name=f"Zona-{stall.code}", sort_order=1)
        spot = MapSpot.objects.create(event=self.event, zone=zone, label=f"{stall.code}-01", x=1, y=1)
        return StallLocationAssignment.objects.create(
            event=self.event,
            stall=stall,
            spot=spot,
            assigned_by_staff=staff_user,
        )

    def _add_vendor_membership(self, *, stall, vendor_user, staff_user=None, role=StallVendorRole.OWNER):
        return StallVendorMembership.objects.create(
            event=self.event,
            stall=stall,
            vendor_user=vendor_user,
            role=role,
            assigned_by_staff=staff_user,
        )

    def test_menu_v2_marks_low_stock_products(self):
        client_user = self.user_model.objects.create_user(username="buyer", password="secret")
        staff_user = self.user_model.objects.create_user(username="buyer-staff", password="secret")
        stall = self._build_stall()
        self._assign_stall_to_spot(stall=stall, staff_user=staff_user)
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
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff)
        self._assign_stall_to_spot(stall=stall, staff_user=staff)
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

    def test_vendor_can_soft_delete_product(self):
        vendor = self.user_model.objects.create_user(username="vendor-delete", password="secret")
        staff = self.user_model.objects.create_user(username="staff-delete", password="secret")
        stall = self._build_stall(code="stall-delete", name="Puesto Delete")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff)
        self._assign_stall_to_spot(stall=stall, staff_user=staff)
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")
        catalog = CatalogProduct.objects.create(sku="delete-001", name="Producto delete")
        product = StallProduct.objects.create(
            event=self.event,
            stall=stall,
            catalog_product=catalog,
            display_name="Producto delete",
            item_nature=ItemNature.INVENTORIABLE,
            category=self.category_food,
            subcategory=self.subcategory_snack,
            price_ucoin=Decimal("10.00"),
            cost_ucoin=Decimal("4.00"),
            stock_mode=StockMode.FINITE,
            stock_qty=5,
            is_active=True,
        )

        self.client.login(username="vendor-delete", password="secret")
        response = self.client.post(
            reverse("vendedor_productos"),
            {"action": "delete_product", "product_id": str(product.id)},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertFalse(product.is_active)

    def test_vendor_can_update_and_remove_stall_image_from_tienda(self):
        vendor = self.user_model.objects.create_user(username="vendor-image", password="secret")
        staff = self.user_model.objects.create_user(username="staff-image", password="secret")
        stall = self._build_stall(code="stall-image", name="Puesto Image")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff)
        self._assign_stall_to_spot(stall=stall, staff_user=staff)
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor-image", password="secret")
        upload = SimpleUploadedFile("stall.png", b"fake-image-content", content_type="image/png")
        response_upload = self.client.post(
            reverse("vendedor_tienda"),
            {
                "name": stall.name,
                "code": stall.code,
                "description": stall.description,
                "image": upload,
            },
            follow=True,
        )
        self.assertEqual(response_upload.status_code, 200)
        stall.refresh_from_db()
        self.assertTrue(bool(stall.image))

        response_remove = self.client.post(
            reverse("vendedor_tienda"),
            {
                "name": stall.name,
                "code": stall.code,
                "description": stall.description,
                "remove_image": "on",
            },
            follow=True,
        )
        self.assertEqual(response_remove.status_code, 200)
        stall.refresh_from_db()
        self.assertFalse(bool(stall.image))

    def test_vendedor_productos_renders_add_button_and_modal(self):
        vendor = self.user_model.objects.create_user(username="vendor-image-link", password="secret")
        staff = self.user_model.objects.create_user(username="staff-image-link", password="secret")
        stall = self._build_stall(code="stall-image-link", name="Puesto Image Link")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff)
        self._assign_stall_to_spot(stall=stall, staff_user=staff)
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor-image-link", password="secret")
        response = self.client.get(reverse("vendedor_productos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Agregar producto")
        self.assertContains(response, 'id="openProductModal"')
        self.assertContains(response, 'id="productModalBackdrop"')
        self.assertNotContains(response, "La imagen de tienda solo se edita en la seccion")

    def test_vendedor_productos_invalid_create_redirects_with_open_modal(self):
        vendor = self.user_model.objects.create_user(username="vendor-modal", password="secret")
        staff = self.user_model.objects.create_user(username="staff-modal", password="secret")
        stall = self._build_stall(code="stall-modal", name="Puesto Modal")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff)
        self._assign_stall_to_spot(stall=stall, staff_user=staff)
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor-modal", password="secret")
        response = self.client.post(
            reverse("vendedor_productos"),
            {
                "action": "save_product",
                "display_name": "",
                "item_nature": ItemNature.INVENTORIABLE,
                "category_id": str(self.category_food.id),
                "subcategory_id": str(self.subcategory_snack.id),
                "price_ucoin": "20.00",
                "cost_ucoin": "5.00",
                "stock_qty": "5",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('vendedor_productos')}?open_modal=1",
            fetch_redirect_response=False,
        )

    def test_vendedor_productos_edit_query_keeps_modal_context(self):
        vendor = self.user_model.objects.create_user(username="vendor-edit", password="secret")
        staff = self.user_model.objects.create_user(username="staff-edit", password="secret")
        stall = self._build_stall(code="stall-edit", name="Puesto Edit")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff)
        self._assign_stall_to_spot(stall=stall, staff_user=staff)
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")
        catalog = CatalogProduct.objects.create(sku="edit-001", name="Editable")
        product = StallProduct.objects.create(
            event=self.event,
            stall=stall,
            catalog_product=catalog,
            display_name="Producto editable",
            item_nature=ItemNature.INVENTORIABLE,
            category=self.category_food,
            subcategory=self.subcategory_snack,
            price_ucoin=Decimal("12.00"),
            cost_ucoin=Decimal("4.00"),
            stock_mode=StockMode.FINITE,
            stock_qty=8,
            is_active=True,
        )

        self.client.login(username="vendor-edit", password="secret")
        response = self.client.get(reverse("vendedor_productos"), {"edit": product.id})

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["form_product"])
        self.assertEqual(response.context["form_product"].id, product.id)
        self.assertContains(response, f'name=\"product_id\" value=\"{product.id}\"')
        self.assertContains(response, 'searchParams.has(\"edit\")')

    def test_menu_post_adds_product_to_v2_cart(self):
        client_user = self.user_model.objects.create_user(username="buyer2", password="secret")
        staff_user = self.user_model.objects.create_user(username="buyer2-staff", password="secret")
        stall = self._build_stall(code="stall-c", name="Puesto C")
        self._assign_stall_to_spot(stall=stall, staff_user=staff_user)
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

    def test_vendor_map_context_highlights_vendor_spot(self):
        vendor = self.user_model.objects.create_user(username="vendor-map", password="secret")
        staff_user = self.user_model.objects.create_user(username="staff-map", password="secret")
        stall = self._build_stall(code="stall-map", name="Puesto Mapa")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff_user)
        vendor_assignment = self._assign_stall_to_spot(stall=stall, staff_user=staff_user)

        extra_zone = MapZone.objects.create(event=self.event, name="Zona extra", sort_order=2)
        MapSpot.objects.create(event=self.event, zone=extra_zone, label="EX-01", x=0.333, y=0.444, status="available")
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor-map", password="secret")
        response = self.client.get(reverse("vendedor_mapa"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("map_spots", response.context)
        self.assertIn("map_image_url", response.context)
        self.assertEqual(response.context["own_spot_id"], vendor_assignment.spot_id)
        self.assertTrue(any(row["is_vendor_spot"] for row in response.context["map_spots"]))
        self.assertTrue(
            any(
                row["id"] == vendor_assignment.spot_id and row["is_vendor_spot"]
                for row in response.context["map_spots"]
            )
        )

    def test_vendor_map_context_without_spot(self):
        vendor = self.user_model.objects.create_user(username="vendor-no-spot", password="secret")
        staff_user = self.user_model.objects.create_user(username="staff-no-spot", password="secret")
        stall = self._build_stall(code="stall-no-spot", name="Puesto sin spot")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff_user)
        zone = MapZone.objects.create(event=self.event, name="Zona sin asignar", sort_order=3)
        MapSpot.objects.create(event=self.event, zone=zone, label="NS-01", x=0.2, y=0.3, status="available")
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor-no-spot", password="secret")
        response = self.client.get(reverse("vendedor_mapa"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin espacio asignado")
        self.assertTrue(response.context["map_spots"])
        self.assertFalse(any(row["is_vendor_spot"] for row in response.context["map_spots"]))

    def test_vendor_map_uses_fallback_image_without_event_map(self):
        vendor = self.user_model.objects.create_user(username="vendor-fallback-map", password="secret")
        staff_user = self.user_model.objects.create_user(username="staff-fallback-map", password="secret")
        stall = self._build_stall(code="stall-fallback", name="Puesto fallback")
        self._add_vendor_membership(stall=stall, vendor_user=vendor, staff_user=staff_user)
        self._assign_stall_to_spot(stall=stall, staff_user=staff_user)
        assign_group_to_user(event=self.event, user=vendor, group_name="vendedor")

        self.client.login(username="vendor-fallback-map", password="secret")
        response = self.client.get(reverse("vendedor_mapa"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("core/img/mapa_upbc.png", response.context["map_image_url"])


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
            assign_group_to_user(event=self.event, user=user, group_name="cliente")

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

    def test_superuser_can_access_vendor_panel_without_vendor_role(self):
        self.client.login(username="root-user", password="secret")
        response = self.client.get(reverse("vendedor"))
        self.assertEqual(response.status_code, 200)

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

    def test_staff_can_sync_roles_with_audit(self):
        self.client.login(username="staff-user", password="secret")
        response_grant = self.client.post(
            reverse("staff_panel"),
            {
                "action": "sync_roles",
                "target_user_id": str(self.client_user.id),
                "group_names": ["cliente", "vendedor"],
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response_grant.status_code, 200)
        self.assertTrue(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="vendedor").exists()
        )
        self.assertTrue(StaffAuditLog.objects.filter(event=self.event, action_type="sync_roles").exists())

        response_revoke = self.client.post(
            reverse("staff_panel"),
            {
                "action": "sync_roles",
                "target_user_id": str(self.client_user.id),
                "group_names": ["cliente"],
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response_revoke.status_code, 200)
        self.assertFalse(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="vendedor").exists()
        )
        latest_log = StaffAuditLog.objects.filter(event=self.event, action_type="sync_roles").first()
        self.assertIsNotNone(latest_log)
        self.assertIn("added", latest_log.payload_json)
        self.assertIn("removed", latest_log.payload_json)
        self.assertIn("ignored", latest_log.payload_json)

    def test_staff_cannot_revoke_own_staff_role(self):
        self.client.login(username="staff-user", password="secret")
        response = self.client.post(
            reverse("staff_panel"),
            {
                "action": "sync_roles",
                "target_user_id": str(self.staff_user.id),
                "group_names": ["cliente"],
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
            reverse("api_assign_vendor", args=[self.event.id]),
            {
                "vendor_user_id": str(self.vendor_user.id),
                "stall_id": str(stall.id),
                "spot_id": str(spot.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        membership = StallVendorMembership.objects.filter(event=self.event, vendor_user=self.vendor_user).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.stall_id, stall.id)
        location = StallLocationAssignment.objects.filter(event=self.event, stall=stall).first()
        self.assertIsNotNone(location)
        self.assertEqual(location.spot_id, spot.id)
        self.assertTrue(StaffAuditLog.objects.filter(event=self.event, action_type="assign_spot_to_stall").exists())

    def test_staff_panel_only_shows_profile_roles(self):
        Group.objects.get_or_create(name="cajero")
        self.client.login(username="staff-user", password="secret")
        response = self.client.get(reverse("staff_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "cajero")
        self.assertContains(response, "cliente")
        self.assertContains(response, "vendedor")
        self.assertContains(response, "staff")

    def test_staff_can_assign_multiple_roles_in_single_sync(self):
        Group.objects.get_or_create(name="cajero")
        Group.objects.get_or_create(name="mesero")
        self.client.login(username="staff-user", password="secret")

        response = self.client.post(
            reverse("staff_panel"),
            {
                "action": "sync_roles",
                "target_user_id": str(self.client_user.id),
                "group_names": ["cliente", "vendedor", "cajero", "mesero"],
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="vendedor").exists()
        )
        self.assertFalse(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="cajero").exists()
        )
        self.assertFalse(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="mesero").exists()
        )

    def test_staff_cannot_revoke_cliente_role(self):
        self.client.login(username="staff-user", password="secret")
        response = self.client.post(
            reverse("staff_panel"),
            {
                "action": "sync_roles",
                "target_user_id": str(self.client_user.id),
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="cliente").exists()
        )

    def test_blocked_roles_not_rendered_or_applied(self):
        Group.objects.get_or_create(name="admin")
        self.client.login(username="staff-user", password="secret")

        response = self.client.get(reverse("staff_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, ">admin<")

        post_response = self.client.post(
            reverse("staff_panel"),
            {
                "action": "sync_roles",
                "target_user_id": str(self.client_user.id),
                "group_names": ["cliente", "admin"],
                "next_query": "",
            },
            follow=True,
        )
        self.assertEqual(post_response.status_code, 200)
        self.assertFalse(
            EventUserGroup.objects.filter(event=self.event, user=self.client_user, group__name="admin").exists()
        )


class EventLockAccessTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        EventCampaign.objects.filter(status=CampaignStatus.ACTIVE).update(
            status=CampaignStatus.CLOSED,
            ends_at=timezone.now() - timezone.timedelta(minutes=1),
        )

    def test_cliente_is_blocked_when_no_active_event(self):
        user = self.user_model.objects.create_user(username="locked-client", password="secret")
        self.client.login(username="locked-client", password="secret")

        response = self.client.get(reverse("cliente"))

        self.assertRedirects(response, reverse("index"), status_code=302, target_status_code=403)

    def test_staff_can_access_staff_panel_without_active_event(self):
        past_event = EventCampaign.objects.create(
            code="past-2026",
            name="Evento pasado",
            starts_at=timezone.now() - timezone.timedelta(days=5),
            ends_at=timezone.now() - timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.CLOSED,
        )
        staff_user = self.user_model.objects.create_user(username="staff-lock", password="secret")
        EventMembership.objects.update_or_create(
            event=past_event,
            user=staff_user,
            defaults={"profile_type": "comunidad", "matricula": "STAFF-LOCK"},
        )
        assign_group_to_user(event=past_event, user=staff_user, group_name="staff")

        self.client.login(username="staff-lock", password="secret")
        response = self.client.get(reverse("staff_panel"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin evento activo")


class ApiPermissionTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.event = EventCampaign.objects.create(
            code="api-2026",
            name="Evento API",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.client_user = self.user_model.objects.create_user(username="api-client", password="secret")
        self.vendor_user = self.user_model.objects.create_user(username="api-vendor", password="secret")
        self.staff_user = self.user_model.objects.create_user(username="api-staff", password="secret")

        for user in [self.client_user, self.vendor_user, self.staff_user]:
            EventMembership.objects.update_or_create(
                event=self.event,
                user=user,
                defaults={"profile_type": "comunidad", "matricula": f"API-{user.id}"},
            )
        assign_group_to_user(event=self.event, user=self.client_user, group_name="cliente")
        assign_group_to_user(event=self.event, user=self.vendor_user, group_name="vendedor")
        assign_group_to_user(event=self.event, user=self.staff_user, group_name="staff")

    def test_checkout_api_vendor_path_returns_business_error_without_cart(self):
        self.client.login(username="api-vendor", password="secret")
        response = self.client.post(reverse("api_checkout_cart", args=[self.event.id]))
        self.assertEqual(response.status_code, 400)

    def test_checkout_api_allows_cliente_permission_path(self):
        self.client.login(username="api-client", password="secret")
        response = self.client.post(reverse("api_checkout_cart", args=[self.event.id]))
        self.assertEqual(response.status_code, 400)

    def test_staff_operations_api_denies_non_staff_user(self):
        self.client.login(username="api-client", password="secret")
        response = self.client.post(reverse("api_assign_vendor", args=[self.event.id]))
        self.assertEqual(response.status_code, 403)

    def test_verify_qr_api_allows_staff_permission_path(self):
        self.client.login(username="api-staff", password="secret")
        response = self.client.post(reverse("api_verify_order_qr", args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_verify_qr_api_denies_cliente_without_vendor_permission(self):
        self.client.login(username="api-client", password="secret")
        response = self.client.post(reverse("api_verify_order_qr", args=[999999]))
        self.assertEqual(response.status_code, 403)


class VisualSystemTemplateTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()
        self.event = EventCampaign.objects.create(
            code="ui-2026",
            name="Evento UI",
            starts_at=timezone.now() - timezone.timedelta(days=1),
            ends_at=timezone.now() + timezone.timedelta(days=1),
            timezone="America/Mexico_City",
            status=CampaignStatus.ACTIVE,
        )
        self.client_user = self.user_model.objects.create_user(username="ui-client", password="secret")
        self.vendor_user = self.user_model.objects.create_user(username="ui-vendor", password="secret")
        self.staff_user = self.user_model.objects.create_user(username="ui-staff", password="secret")

        for user in [self.client_user, self.vendor_user, self.staff_user]:
            EventMembership.objects.update_or_create(
                event=self.event,
                user=user,
                defaults={"profile_type": "comunidad", "matricula": f"UI-{user.id}"},
            )

        assign_group_to_user(event=self.event, user=self.client_user, group_name="cliente")
        assign_group_to_user(event=self.event, user=self.vendor_user, group_name="vendedor")
        assign_group_to_user(event=self.event, user=self.staff_user, group_name="staff")

    def test_auth_pages_use_shared_auth_layout(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "auth-card")
        self.assertContains(response, "btn btn--primary")

    def test_cliente_shell_renders_shared_components(self):
        self.client.login(username="ui-client", password="secret")
        response = self.client.get(reverse("cliente"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app-shell")
        self.assertContains(response, "userToggle")
        self.assertContains(response, "nav__icon")

    def test_vendor_shell_renders_shared_components(self):
        self.client.login(username="ui-vendor", password="secret")
        response = self.client.get(reverse("vendedor"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app-shell")
        self.assertContains(response, "nav__icon")

    def test_staff_shell_renders_shared_components(self):
        self.client.login(username="ui-staff", password="secret")
        response = self.client.get(reverse("staff_panel"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "app-shell")
        self.assertContains(response, "staff-table")

    def test_critical_templates_do_not_render_inline_style_attributes(self):
        self.client.login(username="ui-client", password="secret")
        client_routes = [
            "cliente",
            "menu_alimentos",
            "carrito_cliente",
            "cliente_mapa",
            "historial_compras",
            "historial_recargas",
            "recarga",
        ]
        for route_name in client_routes:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "style=")
