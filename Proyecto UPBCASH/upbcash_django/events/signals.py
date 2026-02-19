from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import ensure_user_client_membership


@receiver(post_save, sender=get_user_model())
def bootstrap_default_event_membership(sender, instance, created, **kwargs):
    if not created:
        return
    ensure_user_client_membership(user=instance)
