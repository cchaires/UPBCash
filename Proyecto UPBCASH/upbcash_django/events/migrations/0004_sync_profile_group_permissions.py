from django.db import migrations

PROFILE_PERMISSIONS = {
    "cliente": [
        "access_cliente_portal",
        "checkout_cart",
    ],
    "vendedor": [
        "access_vendedor_portal",
        "manage_vendor_products",
        "soft_delete_vendor_products",
        "manage_vendor_stall_image",
        "verify_order_qr",
    ],
    "staff": [
        "access_staff_panel",
        "manage_event_profiles",
        "assign_vendor_stall",
        "grant_ucoins",
    ],
}

PERMISSION_LABELS = {
    "access_cliente_portal": "Puede acceder al portal cliente",
    "checkout_cart": "Puede ejecutar checkout de carrito",
    "access_vendedor_portal": "Puede acceder al portal vendedor",
    "manage_vendor_products": "Puede crear y editar productos de vendedor",
    "soft_delete_vendor_products": "Puede desactivar productos de vendedor",
    "manage_vendor_stall_image": "Puede administrar imagen de su tienda",
    "verify_order_qr": "Puede verificar QR de orden",
    "access_staff_panel": "Puede acceder al panel staff",
    "manage_event_profiles": "Puede gestionar perfiles por evento",
    "assign_vendor_stall": "Puede asignar vendedor a puesto y espacio",
    "grant_ucoins": "Puede otorgar ucoins a clientes",
}


def sync_profile_group_permissions(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    ContentType = apps.get_model("contenttypes", "ContentType")
    EventUserGroup = apps.get_model("events", "EventUserGroup")

    all_codenames = sorted({codename for codenames in PROFILE_PERMISSIONS.values() for codename in codenames})
    content_type, _created = ContentType.objects.get_or_create(
        app_label=EventUserGroup._meta.app_label,
        model=EventUserGroup._meta.model_name,
    )
    permissions_by_codename = {}
    for codename in all_codenames:
        permission, _permission_created = Permission.objects.get_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": PERMISSION_LABELS[codename]},
        )
        permissions_by_codename[codename] = permission

    for group_name, codenames in PROFILE_PERMISSIONS.items():
        group, _created = Group.objects.get_or_create(name=group_name)
        current_custom_permissions = list(
            group.permissions.filter(content_type=content_type, codename__in=all_codenames)
        )
        to_remove = [permission for permission in current_custom_permissions if permission.codename not in codenames]
        if to_remove:
            group.permissions.remove(*to_remove)

        to_add = [permissions_by_codename[codename] for codename in codenames if codename in permissions_by_codename]
        if to_add:
            group.permissions.add(*to_add)


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0003_alter_eventusergroup_options"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(sync_profile_group_permissions, migrations.RunPython.noop),
    ]
