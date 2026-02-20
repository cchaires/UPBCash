# Generated manually to support stall memberships and spot assignments.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0005_eventcampaign_public_window_and_map"),
        ("stalls", "0003_stall_image"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StallVendorMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Propietario"), ("member", "Miembro")],
                        default="member",
                        max_length=16,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assigned_by_staff",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_vendor_memberships_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stall_vendor_memberships",
                        to="events.eventcampaign",
                    ),
                ),
                (
                    "stall",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vendor_memberships",
                        to="stalls.stall",
                    ),
                ),
                (
                    "vendor_user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stall_vendor_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["stall__name", "vendor_user__username", "id"],
            },
        ),
        migrations.CreateModel(
            name="StallLocationAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("assigned_at", models.DateTimeField(auto_now_add=True)),
                (
                    "assigned_by_staff",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="staff_spot_assignments_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stall_location_assignments",
                        to="events.eventcampaign",
                    ),
                ),
                (
                    "spot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="stall_location_assignments",
                        to="stalls.mapspot",
                    ),
                ),
                (
                    "stall",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="location_assignments",
                        to="stalls.stall",
                    ),
                ),
            ],
            options={
                "ordering": ["-assigned_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="stallvendormembership",
            constraint=models.UniqueConstraint(fields=("event", "vendor_user"), name="uniq_vendor_membership_per_event"),
        ),
        migrations.AddConstraint(
            model_name="stallvendormembership",
            constraint=models.UniqueConstraint(
                fields=("event", "stall", "vendor_user"),
                name="uniq_vendor_membership_by_stall",
            ),
        ),
        migrations.AddIndex(
            model_name="stallvendormembership",
            index=models.Index(fields=["event", "stall"], name="stalls_svm_event_stall_idx"),
        ),
        migrations.AddIndex(
            model_name="stallvendormembership",
            index=models.Index(fields=["event", "vendor_user"], name="stalls_svm_event_vendor_idx"),
        ),
        migrations.AddConstraint(
            model_name="stalllocationassignment",
            constraint=models.UniqueConstraint(fields=("event", "stall"), name="uniq_location_assignment_by_stall_event"),
        ),
        migrations.AddConstraint(
            model_name="stalllocationassignment",
            constraint=models.UniqueConstraint(fields=("event", "spot"), name="uniq_location_assignment_by_spot_event"),
        ),
        migrations.AddIndex(
            model_name="stalllocationassignment",
            index=models.Index(fields=["event", "stall"], name="stalls_sla_event_stall_idx"),
        ),
        migrations.AddIndex(
            model_name="stalllocationassignment",
            index=models.Index(fields=["event", "spot"], name="stalls_sla_event_spot_idx"),
        ),
    ]
