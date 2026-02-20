# Data migration: copies legacy StallAssignment data to new membership/location models.

from django.db import migrations


def forward_copy_stall_assignment(apps, schema_editor):
    StallAssignment = apps.get_model("stalls", "StallAssignment")
    StallVendorMembership = apps.get_model("stalls", "StallVendorMembership")
    StallLocationAssignment = apps.get_model("stalls", "StallLocationAssignment")
    MapSpot = apps.get_model("stalls", "MapSpot")

    assigned_spot_ids = []
    for legacy in StallAssignment.objects.all().iterator():
        StallVendorMembership.objects.get_or_create(
            event_id=legacy.event_id,
            vendor_user_id=legacy.vendor_user_id,
            defaults={
                "stall_id": legacy.stall_id,
                "role": "owner",
                "assigned_by_staff_id": legacy.assigned_by_staff_id,
            },
        )
        StallVendorMembership.objects.get_or_create(
            event_id=legacy.event_id,
            stall_id=legacy.stall_id,
            vendor_user_id=legacy.vendor_user_id,
            defaults={
                "role": "owner",
                "assigned_by_staff_id": legacy.assigned_by_staff_id,
            },
        )

        assignment, created = StallLocationAssignment.objects.get_or_create(
            event_id=legacy.event_id,
            stall_id=legacy.stall_id,
            defaults={
                "spot_id": legacy.spot_id,
                "assigned_by_staff_id": legacy.assigned_by_staff_id,
            },
        )
        if not created and assignment.spot_id != legacy.spot_id:
            assignment.spot_id = legacy.spot_id
            assignment.assigned_by_staff_id = legacy.assigned_by_staff_id
            assignment.save(update_fields=["spot", "assigned_by_staff"])

        assigned_spot_ids.append(legacy.spot_id)

    if assigned_spot_ids:
        MapSpot.objects.filter(id__in=assigned_spot_ids).update(status="assigned")


class Migration(migrations.Migration):

    dependencies = [
        ("stalls", "0004_stall_vendor_membership_and_location"),
    ]

    operations = [
        migrations.RunPython(forward_copy_stall_assignment, migrations.RunPython.noop),
    ]
