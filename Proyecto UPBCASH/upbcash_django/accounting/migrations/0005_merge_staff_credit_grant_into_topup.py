from django.db import migrations, models


def migrate_reason_to_topup(apps, schema_editor):
    TopupRecord = apps.get_model("accounting", "TopupRecord")
    StaffCreditGrant = apps.get_model("accounting", "StaffCreditGrant")
    db_alias = schema_editor.connection.alias

    for grant in StaffCreditGrant.objects.using(db_alias).all().iterator():
        topup = (
            TopupRecord.objects.using(db_alias)
            .filter(
                event_id=grant.event_id,
                user_id=grant.client_user_id,
                staff_user_id=grant.staff_user_id,
                amount_ucoin=grant.amount_ucoin,
                channel="cash_staff",
            )
            .order_by("created_at")
            .first()
        )
        if topup and not topup.reason:
            topup.reason = grant.reason
            topup.save(update_fields=["reason"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0004_rename_ledger_entry_amount_and_trigger"),
    ]

    operations = [
        migrations.AddField(
            model_name="topuprecord",
            name="reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunPython(migrate_reason_to_topup, reverse_code=noop_reverse),
        migrations.RemoveConstraint(
            model_name="staffcreditgrant",
            name="check_staff_credit_amount_positive",
        ),
        migrations.DeleteModel(
            name="StaffCreditGrant",
        ),
    ]
