import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Mapa de valores historicos de reference_model (strings sueltos) hacia el
# modelo Django real que representan.
MODEL_MAP = {
    "topup_record": ("accounting", "topuprecord"),
    "sales_order": ("commerce", "salesorder"),
    "event_campaign": ("events", "eventcampaign"),
}


def backfill_reference_gfk(apps, schema_editor):
    LedgerTransaction = apps.get_model("accounting", "LedgerTransaction")
    ContentType = apps.get_model("contenttypes", "ContentType")
    db_alias = schema_editor.connection.alias

    ct_cache = {}
    for tx in LedgerTransaction.objects.using(db_alias).exclude(reference_model="").iterator():
        mapping = MODEL_MAP.get(tx.reference_model)
        if not mapping:
            continue  # valor desconocido: se deja sin GFK, no se inventa dato
        if tx.reference_model not in ct_cache:
            app_label, model = mapping
            # get_or_create (no get): al correr todas las migraciones desde cero
            # (ej. base de datos de tests) las ContentType aun no existen porque
            # create_contenttypes se dispara via post_migrate al final de todo
            # el comando migrate, no incrementalmente por app.
            ct_cache[tx.reference_model], _ = ContentType.objects.using(db_alias).get_or_create(
                app_label=app_label, model=model
            )
        try:
            object_id = int(tx.reference_id)
        except (TypeError, ValueError):
            continue
        tx.reference_content_type = ct_cache[tx.reference_model]
        tx.reference_object_id = object_id
        tx.save(update_fields=["reference_content_type", "reference_object_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0005_merge_staff_credit_grant_into_topup"),
        ("commerce", "0002_initial"),
        ("events", "0005_eventcampaign_public_window_and_map"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="ledgertransaction",
            name="reference_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="ledgertransaction",
            name="reference_object_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="ledgertransaction",
            index=models.Index(
                fields=["reference_content_type", "reference_object_id"],
                name="accounting__referen_c64e08_idx",
            ),
        ),
        migrations.RunPython(backfill_reference_gfk, reverse_code=noop_reverse),
        migrations.RemoveField(model_name="ledgertransaction", name="reference_id"),
        migrations.RemoveField(model_name="ledgertransaction", name="reference_model"),
    ]
