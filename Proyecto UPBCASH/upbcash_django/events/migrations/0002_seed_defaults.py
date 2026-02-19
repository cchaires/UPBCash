from django.db import migrations
from django.utils import timezone


def seed_groups_and_default_event(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    EventCampaign = apps.get_model("events", "EventCampaign")

    for group_name in ("cliente", "vendedor", "staff"):
        Group.objects.get_or_create(name=group_name)

    if not EventCampaign.objects.exists():
        now = timezone.now()
        EventCampaign.objects.create(
            code="default-boot",
            name="Evento Activo",
            description="Evento inicial creado automaticamente.",
            starts_at=now - timezone.timedelta(days=1),
            ends_at=now + timezone.timedelta(days=365),
            timezone="America/Mexico_City",
            status="active",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_groups_and_default_event, migrations.RunPython.noop),
    ]
