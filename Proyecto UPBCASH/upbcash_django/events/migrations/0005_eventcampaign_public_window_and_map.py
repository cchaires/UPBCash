# Generated manually to support campaign/public windows and map settings.

from django.db import migrations, models


def backfill_public_window(apps, schema_editor):
    EventCampaign = apps.get_model("events", "EventCampaign")
    for campaign in EventCampaign.objects.all().iterator():
        update_fields = []
        if campaign.public_starts_at is None:
            campaign.public_starts_at = campaign.starts_at
            update_fields.append("public_starts_at")
        if campaign.public_ends_at is None:
            campaign.public_ends_at = campaign.ends_at
            update_fields.append("public_ends_at")
        if getattr(campaign, "max_map_spots", 0) <= 0:
            campaign.max_map_spots = 5
            update_fields.append("max_map_spots")
        if update_fields:
            campaign.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0004_sync_profile_group_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventcampaign",
            name="public_starts_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventcampaign",
            name="public_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventcampaign",
            name="max_map_spots",
            field=models.PositiveIntegerField(default=5),
        ),
        migrations.AddField(
            model_name="eventcampaign",
            name="map_image",
            field=models.FileField(blank=True, null=True, upload_to="events/maps/"),
        ),
        migrations.AddIndex(
            model_name="eventcampaign",
            index=models.Index(fields=["status", "public_starts_at"], name="events_evt_stat_pub_idx"),
        ),
        migrations.AddIndex(
            model_name="eventcampaign",
            index=models.Index(fields=["public_starts_at", "public_ends_at"], name="events_evt_pub_window_idx"),
        ),
        migrations.RunPython(backfill_public_window, migrations.RunPython.noop),
    ]
