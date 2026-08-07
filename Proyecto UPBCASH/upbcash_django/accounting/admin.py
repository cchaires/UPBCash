from django.contrib import admin

from .models import LedgerAccount, LedgerEntry, LedgerTransaction, TopupRecord, WalletBalanceCache


@admin.register(LedgerAccount)
class LedgerAccountAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "event", "account_type", "owner_user", "owner_stall", "is_active")
    list_filter = ("event", "account_type", "is_active")
    search_fields = ("code", "name")


class LedgerEntryInline(admin.TabularInline):
    model = LedgerEntry
    extra = 0
    readonly_fields = ("account", "amount_ucoin_signed", "description")
    can_delete = False


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "tx_type", "status", "created_by_user", "created_at")
    list_filter = ("event", "tx_type", "status")
    search_fields = ("id", "idempotency_key")
    inlines = [LedgerEntryInline]
    date_hierarchy = "created_at"


@admin.register(TopupRecord)
class TopupRecordAdmin(admin.ModelAdmin):
    """list_filter + date_hierarchy dan una vista lista para reportes de dirección:
    cuanto se recargo por canal/estado y en que rango de fechas."""

    list_display = ("event", "user", "channel", "amount_ucoin", "status", "staff_user", "created_at")
    list_filter = ("event", "channel", "status")
    search_fields = ("user__username", "provider_ref", "source_reference", "reason")
    date_hierarchy = "created_at"


@admin.register(WalletBalanceCache)
class WalletBalanceCacheAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "balance_ucoin", "updated_at")
    list_filter = ("event",)
    search_fields = ("user__username",)
