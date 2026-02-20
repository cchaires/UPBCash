from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounting.models import WalletBalanceCache
from accounting.services import WalletService
from events.models import CampaignStatus, EventCampaign


class Command(BaseCommand):
    help = "Cierra un evento, expira saldos UCoin restantes y deja el evento en solo lectura."

    def add_arguments(self, parser):
        parser.add_argument("event_code")

    @transaction.atomic
    def handle(self, *args, **options):
        event = EventCampaign.objects.filter(code=options["event_code"]).first()
        if not event:
            raise CommandError("Evento no encontrado.")
        if event.status == CampaignStatus.CLOSED:
            self.stdout.write(self.style.WARNING("El evento ya estaba cerrado."))
            return

        balances = WalletBalanceCache.objects.filter(event=event, balance_ucoin__gt=0).select_related("user")
        for cache in balances:
            WalletService.expire_remaining_balance(event=event, user=cache.user)

        event.status = CampaignStatus.CLOSED
        now = timezone.now()
        event.ends_at = min(event.ends_at, now)
        event.public_ends_at = min(event.public_ends_at or now, now)
        event.save(update_fields=["status", "ends_at", "public_ends_at"])
        self.stdout.write(self.style.SUCCESS(f"Evento {event.code} cerrado correctamente."))
