from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from events.services import assert_event_writable

from .models import (
    LedgerAccount,
    LedgerAccountType,
    LedgerEntry,
    LedgerTransaction,
    LedgerTxStatus,
    LedgerTxType,
    StaffCreditGrant,
    TopupChannel,
    TopupRecord,
    TopupStatus,
    WalletBalanceCache,
)

UCOIN_TO_MXN_RATE = Decimal("1.00")


def _money(amount):
    return Decimal(amount).quantize(Decimal("0.01"))


class WalletService:
    PLATFORM_CASH_CODE = "PLATFORM_CASH"
    PLATFORM_REVENUE_CODE = "PLATFORM_REVENUE"
    PLATFORM_EXPIRY_CODE = "PLATFORM_EXPIRY"

    @classmethod
    def _wallet_account_code(cls, user_id):
        return f"WALLET_USER_{user_id}"

    @classmethod
    def ensure_account(cls, *, event, code, name, account_type, owner_user=None, owner_stall=None):
        account, _ = LedgerAccount.objects.get_or_create(
            event=event,
            code=code,
            defaults={
                "name": name,
                "account_type": account_type,
                "owner_user": owner_user,
                "owner_stall": owner_stall,
                "is_active": True,
            },
        )
        return account

    @classmethod
    def ensure_platform_accounts(cls, *, event):
        cash = cls.ensure_account(
            event=event,
            code=cls.PLATFORM_CASH_CODE,
            name="Caja plataforma",
            account_type=LedgerAccountType.ASSET,
        )
        revenue = cls.ensure_account(
            event=event,
            code=cls.PLATFORM_REVENUE_CODE,
            name="Ingreso plataforma",
            account_type=LedgerAccountType.REVENUE,
        )
        expiry = cls.ensure_account(
            event=event,
            code=cls.PLATFORM_EXPIRY_CODE,
            name="Ingreso por expiracion",
            account_type=LedgerAccountType.REVENUE,
        )
        return cash, revenue, expiry

    @classmethod
    def ensure_user_wallet_account(cls, *, event, user):
        return cls.ensure_account(
            event=event,
            code=cls._wallet_account_code(user.id),
            name=f"Wallet de {user.username}",
            account_type=LedgerAccountType.LIABILITY,
            owner_user=user,
        )

    @classmethod
    def get_balance_cache_for_update(cls, *, event, user):
        return WalletBalanceCache.objects.select_for_update().get_or_create(event=event, user=user)[0]

    @classmethod
    def get_balance(cls, *, event, user):
        cache, _ = WalletBalanceCache.objects.get_or_create(event=event, user=user)
        return cache.balance_ucoin

    @classmethod
    def set_balance(cls, *, event, user, balance):
        cache, _ = WalletBalanceCache.objects.get_or_create(event=event, user=user)
        cache.balance_ucoin = _money(balance)
        cache.save(update_fields=["balance_ucoin", "updated_at"])
        return cache

    @classmethod
    def apply_balance_delta(cls, *, event, user, delta):
        cache = cls.get_balance_cache_for_update(event=event, user=user)
        cache.balance_ucoin = _money(cache.balance_ucoin + _money(delta))
        cache.save(update_fields=["balance_ucoin", "updated_at"])
        return cache

    @classmethod
    def post_transaction(
        cls,
        *,
        event,
        tx_type,
        idempotency_key,
        created_by_user=None,
        reference_model="",
        reference_id="",
        entries,
    ):
        existing = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

        tx = LedgerTransaction.objects.create(
            event=event,
            tx_type=tx_type,
            status=LedgerTxStatus.POSTED,
            idempotency_key=idempotency_key,
            created_by_user=created_by_user,
            reference_model=reference_model,
            reference_id=str(reference_id or ""),
        )

        amount_sum = Decimal("0.00")
        for account, amount, description in entries:
            signed = _money(amount)
            amount_sum += signed
            LedgerEntry.objects.create(
                transaction=tx,
                account=account,
                amount_mxn_signed=signed,
                description=description,
            )

        if amount_sum != Decimal("0.00"):
            raise ValueError("La transaccion contable no esta balanceada.")

        return tx

    @classmethod
    @transaction.atomic
    def record_online_topup(
        cls,
        *,
        event,
        user,
        amount_ucoin,
        provider="PayPal",
        provider_ref="",
        source_reference="",
    ):
        assert_event_writable(event)
        amount = _money(amount_ucoin)
        if amount <= 0:
            raise ValueError("El monto de recarga debe ser mayor a cero.")

        if source_reference:
            topup, created = TopupRecord.objects.get_or_create(
                event=event,
                source_reference=source_reference,
                defaults={
                    "user": user,
                    "channel": TopupChannel.ONLINE,
                    "amount_ucoin": amount,
                    "status": TopupStatus.SUCCESS,
                    "provider": provider,
                    "provider_ref": provider_ref,
                },
            )
            if not created:
                return topup
        else:
            topup = TopupRecord.objects.create(
                event=event,
                user=user,
                channel=TopupChannel.ONLINE,
                amount_ucoin=amount,
                status=TopupStatus.SUCCESS,
                provider=provider,
                provider_ref=provider_ref,
            )

        cash_account, _, _ = cls.ensure_platform_accounts(event=event)
        wallet_account = cls.ensure_user_wallet_account(event=event, user=user)
        cls.post_transaction(
            event=event,
            tx_type=LedgerTxType.TOPUP_ONLINE,
            idempotency_key=f"topup_online:{event.id}:{topup.id}",
            created_by_user=user,
            reference_model="topup_record",
            reference_id=topup.id,
            entries=[
                (wallet_account, amount, "Aumento de saldo de usuario"),
                (cash_account, -amount, "Entrada en caja por recarga"),
            ],
        )
        cls.apply_balance_delta(event=event, user=user, delta=amount)
        return topup

    @classmethod
    @transaction.atomic
    def grant_cash_topup(
        cls,
        *,
        event,
        client_user,
        staff_user,
        amount_ucoin,
        reason="",
    ):
        assert_event_writable(event)
        amount = _money(amount_ucoin)
        if amount <= 0:
            raise ValueError("El monto debe ser mayor a cero.")

        topup = TopupRecord.objects.create(
            event=event,
            user=client_user,
            channel=TopupChannel.CASH_STAFF,
            amount_ucoin=amount,
            status=TopupStatus.SUCCESS,
            provider="cash",
            provider_ref="staff",
            staff_user=staff_user,
        )
        grant = StaffCreditGrant.objects.create(
            event=event,
            client_user=client_user,
            staff_user=staff_user,
            amount_ucoin=amount,
            reason=reason,
        )

        cash_account, _, _ = cls.ensure_platform_accounts(event=event)
        wallet_account = cls.ensure_user_wallet_account(event=event, user=client_user)
        cls.post_transaction(
            event=event,
            tx_type=LedgerTxType.TOPUP_CASH,
            idempotency_key=f"topup_cash:{event.id}:{topup.id}",
            created_by_user=staff_user,
            reference_model="topup_record",
            reference_id=topup.id,
            entries=[
                (wallet_account, amount, "Aumento de saldo por recarga en efectivo"),
                (cash_account, -amount, "Entrada en caja por staff"),
            ],
        )
        cls.apply_balance_delta(event=event, user=client_user, delta=amount)
        return topup, grant

    @classmethod
    @transaction.atomic
    def record_purchase(cls, *, event, user, amount_ucoin, reference_model, reference_id, created_by_user=None):
        assert_event_writable(event)
        amount = _money(amount_ucoin)
        if amount <= 0:
            raise ValueError("El monto de compra debe ser mayor a cero.")

        wallet_cache = cls.get_balance_cache_for_update(event=event, user=user)
        if wallet_cache.balance_ucoin < amount:
            raise ValueError("Saldo insuficiente.")
        return cls.record_purchase_mirror(
            event=event,
            user=user,
            amount_ucoin=amount,
            reference_model=reference_model,
            reference_id=reference_id,
            created_by_user=created_by_user or user,
            balance_cache=wallet_cache,
        )

    @classmethod
    def record_purchase_mirror(
        cls,
        *,
        event,
        user,
        amount_ucoin,
        reference_model,
        reference_id,
        created_by_user=None,
        balance_cache=None,
    ):
        assert_event_writable(event)
        amount = _money(amount_ucoin)
        if amount <= 0:
            raise ValueError("El monto de compra debe ser mayor a cero.")
        wallet_cache = balance_cache or cls.get_balance_cache_for_update(event=event, user=user)
        idempotency_key = f"purchase:{event.id}:{reference_model}:{reference_id}"
        tx_already_exists = LedgerTransaction.objects.filter(idempotency_key=idempotency_key).exists()

        _, revenue_account, _ = cls.ensure_platform_accounts(event=event)
        wallet_account = cls.ensure_user_wallet_account(event=event, user=user)
        cls.post_transaction(
            event=event,
            tx_type=LedgerTxType.PURCHASE,
            idempotency_key=idempotency_key,
            created_by_user=created_by_user or user,
            reference_model=reference_model,
            reference_id=reference_id,
            entries=[
                (wallet_account, -amount, "Descuento de wallet por compra"),
                (revenue_account, amount, "Reconocimiento de ingreso"),
            ],
        )
        if not tx_already_exists:
            wallet_cache.balance_ucoin = _money(wallet_cache.balance_ucoin - amount)
            wallet_cache.save(update_fields=["balance_ucoin", "updated_at"])
        return wallet_cache

    @classmethod
    @transaction.atomic
    def expire_remaining_balance(cls, *, event, user, created_by_user=None):
        assert_event_writable(event)
        wallet_cache = cls.get_balance_cache_for_update(event=event, user=user)
        amount = _money(wallet_cache.balance_ucoin)
        if amount <= 0:
            return wallet_cache

        _, _, expiry_account = cls.ensure_platform_accounts(event=event)
        wallet_account = cls.ensure_user_wallet_account(event=event, user=user)
        cls.post_transaction(
            event=event,
            tx_type=LedgerTxType.EXPIRY,
            idempotency_key=f"expiry:{event.id}:{user.id}:{timezone.now().date().isoformat()}",
            created_by_user=created_by_user,
            reference_model="event_campaign",
            reference_id=event.id,
            entries=[
                (wallet_account, -amount, "Expiracion de saldo al cierre de evento"),
                (expiry_account, amount, "Ingreso por expiracion"),
            ],
        )
        wallet_cache.balance_ucoin = Decimal("0.00")
        wallet_cache.save(update_fields=["balance_ucoin", "updated_at"])
        return wallet_cache

    @classmethod
    def reconcile_balance_from_ledger(cls, *, event, user):
        wallet_account = cls.ensure_user_wallet_account(event=event, user=user)
        total = (
            LedgerEntry.objects.filter(transaction__event=event, account=wallet_account)
            .aggregate(total=Sum("amount_mxn_signed"))
            .get("total")
            or Decimal("0.00")
        )
        cache = cls.set_balance(event=event, user=user, balance=total)
        return cache.balance_ucoin
