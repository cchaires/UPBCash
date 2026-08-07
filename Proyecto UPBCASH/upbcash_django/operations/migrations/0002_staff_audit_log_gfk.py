import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# Mapa de valores historicos de target_model (strings sueltos) hacia el modelo
# Django real que representan.
#
# "events.EventUserGroup" -> auth.user: bug preexistente corregido en el mismo
# refactor que introduce esta migracion. sync_user_roles/revoke_role loguean
# hoy `target_id=target_user.id`, es decir el string decia "EventUserGroup"
# pero el id siempre fue de un User real.
#
# "accounting.StaffCreditGrant" se omite a proposito: ese modelo fue eliminado
# en la fase anterior del refactor (unificado dentro de TopupRecord) y no hay
# forma confiable de recuperar el TopupRecord equivalente desde el log
# historico sin inventar datos - esos registros quedan con
# target_content_type=None tras esta migracion.
MODEL_MAP = {
    "events.EventUserGroup": ("auth", "user"),
    "stalls.MapSpot": ("stalls", "mapspot"),
    "stalls.StallVendorMembership": ("stalls", "stallvendormembership"),
    "stalls.StallLocationAssignment": ("stalls", "stalllocationassignment"),
    "accounting.TopupRecord": ("accounting", "topuprecord"),
}


def backfill_target_gfk(apps, schema_editor):
    StaffAuditLog = apps.get_model("operations", "StaffAuditLog")
    ContentType = apps.get_model("contenttypes", "ContentType")
    db_alias = schema_editor.connection.alias

    ct_cache = {}
    for log in StaffAuditLog.objects.using(db_alias).exclude(target_model="").iterator():
        mapping = MODEL_MAP.get(log.target_model)
        if not mapping:
            continue  # valor desconocido (ej. accounting.StaffCreditGrant): se deja sin GFK
        if log.target_model not in ct_cache:
            app_label, model = mapping
            ct_cache[log.target_model], _ = ContentType.objects.using(db_alias).get_or_create(
                app_label=app_label, model=model
            )
        try:
            object_id = int(log.target_id)
        except (TypeError, ValueError):
            continue
        log.target_content_type = ct_cache[log.target_model]
        log.target_object_id = object_id
        log.save(update_fields=["target_content_type", "target_object_id"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0001_initial"),
        ("stalls", "0007_delete_stallassignment"),
        ("accounting", "0005_merge_staff_credit_grant_into_topup"),
        ("contenttypes", "0002_remove_content_type_name"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="staffauditlog",
            name="target_content_type",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="contenttypes.contenttype",
            ),
        ),
        migrations.AddField(
            model_name="staffauditlog",
            name="target_object_id",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="staffauditlog",
            index=models.Index(
                fields=["target_content_type", "target_object_id"],
                name="operations__target__79ae23_idx",
            ),
        ),
        migrations.RunPython(backfill_target_gfk, reverse_code=noop_reverse),
        migrations.RemoveField(model_name="staffauditlog", name="target_id"),
        migrations.RemoveField(model_name="staffauditlog", name="target_model"),
    ]
