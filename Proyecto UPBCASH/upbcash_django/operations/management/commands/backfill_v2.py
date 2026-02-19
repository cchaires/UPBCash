from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounting.models import WalletBalanceCache
from accounting.services import WalletService
from commerce.services import CheckoutService
from core.models import FoodItem, Purchase, PurchaseItem, Recharge, UserProfile, Wallet
from events.models import CampaignStatus, EventCampaign, ProfileType
from events.services import ensure_group, ensure_user_client_membership
from stalls.models import CatalogProduct, Stall, StallProduct, StockMode


class Command(BaseCommand):
    help = "Backfill de esquema legacy (core) hacia esquema v2 multi-evento."

    def add_arguments(self, parser):
        parser.add_argument("--event-code", default="legacy-boot")
        parser.add_argument("--event-name", default="Evento Legacy")
        parser.add_argument("--start-days-ago", type=int, default=3650)
        parser.add_argument("--end-days-after", type=int, default=3650)

    @transaction.atomic
    def handle(self, *args, **options):
        start = timezone.now() - timezone.timedelta(days=options["start_days_ago"])
        end = timezone.now() + timezone.timedelta(days=options["end_days_after"])
        event, _ = EventCampaign.objects.get_or_create(
            code=options["event_code"],
            defaults={
                "name": options["event_name"],
                "description": "Evento creado para migracion legacy",
                "starts_at": start,
                "ends_at": end,
                "timezone": "America/Mexico_City",
                "status": CampaignStatus.ACTIVE,
            },
        )

        for group_name in ("cliente", "vendedor", "staff"):
            ensure_group(group_name)

        self._backfill_users(event)
        self._backfill_catalog(event)
        self._backfill_recharges(event)
        self._backfill_purchases(event)
        self._backfill_wallet_balances(event)
        self.stdout.write(self.style.SUCCESS("Backfill v2 completado."))

    def _profile_type_from_legacy(self, profile):
        if not profile:
            return ProfileType.COMUNIDAD
        return ProfileType.INVITADO if profile.account_type == "invitado" else ProfileType.COMUNIDAD

    def _backfill_users(self, event):
        user_model = get_user_model()
        profile_map = {p.user_id: p for p in UserProfile.objects.select_related("user")}
        for user in user_model.objects.all():
            profile = profile_map.get(user.id)
            ensure_user_client_membership(
                user=user,
                event=event,
                profile_type=self._profile_type_from_legacy(profile),
                matricula=profile.matricula if profile else "",
                phone=profile.phone if profile else "",
                invited_by_email=profile.invited_by_email if profile else "",
                invited_by_matricula=profile.invited_by_matricula if profile else "",
            )

    def _legacy_stall(self, event):
        stall, _ = Stall.objects.get_or_create(
            event=event,
            code="legacy-stall",
            defaults={"name": "Puesto legado", "description": "Catalogo migrado", "status": "open"},
        )
        return stall

    def _backfill_catalog(self, event):
        stall = self._legacy_stall(event)
        for item in FoodItem.objects.all():
            catalog, _ = CatalogProduct.objects.get_or_create(
                sku=f"legacy-{item.code}",
                defaults={
                    "name": item.name,
                    "description": item.description,
                    "photo_variant": item.photo_variant,
                    "is_active": item.is_active,
                },
            )
            StallProduct.objects.get_or_create(
                event=event,
                stall=stall,
                catalog_product=catalog,
                defaults={
                    "display_name": item.name,
                    "price_ucoin": item.price,
                    "stock_mode": StockMode.UNLIMITED,
                    "stock_qty": None,
                    "low_stock_threshold": None,
                    "is_sold_out_manual": False,
                    "is_active": item.is_active,
                },
            )

    def _backfill_recharges(self, event):
        for recharge in Recharge.objects.select_related("user").order_by("id"):
            WalletService.record_online_topup(
                event=event,
                user=recharge.user,
                amount_ucoin=recharge.amount,
                provider=recharge.payment_method or "PayPal",
                provider_ref=recharge.code,
                source_reference=f"legacy_recharge:{recharge.id}",
            )

    def _backfill_purchases(self, event):
        purchase_rows = (
            Purchase.objects.select_related("user")
            .prefetch_related("items")
            .order_by("id")
        )
        for purchase in purchase_rows:
            rows = []
            for item in purchase.items.all():
                rows.append(
                    {
                        "code": item.food_code,
                        "name": item.food_name,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                    }
                )
            CheckoutService.mirror_legacy_purchase(
                event=event,
                user=purchase.user,
                legacy_purchase_id=purchase.id,
                amount_ucoin=purchase.total,
                legacy_cart_rows=rows,
            )
            WalletService.record_purchase_mirror(
                event=event,
                user=purchase.user,
                amount_ucoin=purchase.total,
                reference_model="legacy_purchase",
                reference_id=purchase.id,
                created_by_user=purchase.user,
            )

    def _backfill_wallet_balances(self, event):
        for wallet in Wallet.objects.select_related("user"):
            cache, _ = WalletBalanceCache.objects.get_or_create(event=event, user=wallet.user)
            cache.balance_ucoin = Decimal(wallet.balance).quantize(Decimal("0.01"))
            cache.save(update_fields=["balance_ucoin", "updated_at"])
