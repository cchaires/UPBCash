from django.db import migrations


class Migration(migrations.Migration):
    """
    Elimina los modelos legacy del sistema de wallet y recargas (v1).
    Reemplazados por accounting.TopupRecord, accounting.WalletBalanceCache,
    accounting.LedgerTransaction/LedgerEntry y operations.SupportTicket.
    """

    dependencies = [
        ("core", "0004_remove_legacy_food_purchase"),
    ]

    operations = [
        migrations.DeleteModel(name="RechargeIssue"),
        migrations.DeleteModel(name="Recharge"),
        migrations.DeleteModel(name="WalletLedger"),
        migrations.DeleteModel(name="Wallet"),
        migrations.DeleteModel(name="UserProfile"),
    ]
