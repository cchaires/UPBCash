from django.db import models

# Convencion de nombres monetarios del proyecto: todo monto/saldo se expresa en
# la moneda virtual interna "ucoin" y el campo debe llevar el sufijo `_ucoin`
# (o `_ucoin_signed` cuando el valor puede ser negativo, como en el ledger de
# doble entrada). No existe conversion a moneda real: `UCOIN_TO_MXN_RATE` en
# `accounting.services` esta fijada a 1.00.


class EventScopedModel(models.Model):
    """Base abstracta para modelos que pertenecen a un unico EventCampaign.

    Cada subclase DEBE re-declarar `event` unicamente para fijar su propio
    `related_name` (los related_names existentes no siguen un patron mecanico,
    asi que no se generan dinamicamente para no romper accesos ya usados en
    services/views, ej. `event.ledger_accounts.all()`).
    """

    event = models.ForeignKey("events.EventCampaign", on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True
