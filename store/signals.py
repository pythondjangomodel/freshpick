# store/signals.py

import logging

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Order, Shipment
from .utils import send_order_confirmation_email
from .shiprocket import create_shiprocket_order

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Order)
def _store_previous_status(sender, instance, **kwargs):
    """Before saving, remember what the status WAS so we can compare after saving.
    Runs whether the save comes from checkout code, the Django admin dropdown,
    or anywhere else -- any path that calls order.save()."""
    if instance.pk:
        try:
            instance._previous_status = Order.objects.get(pk=instance.pk).status
        except Order.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None  # brand new order being created


@receiver(post_save, sender=Order)
def _on_order_confirmed(sender, instance, created, **kwargs):
    """After saving, check if status just changed INTO 'confirmed'.
    Only fires on that exact transition -- sends the email AND creates
    the Shiprocket shipment together."""
    if created:
        return  # a brand new order isn't confirmed yet, nothing to do

    previous_status = getattr(instance, "_previous_status", None)
    just_confirmed = previous_status != Order.STATUS_CONFIRMED and instance.status == Order.STATUS_CONFIRMED

    if not just_confirmed:
        return

    send_order_confirmation_email(instance)

    # Don't create a duplicate shipment if one somehow already exists for this order
    if hasattr(instance, "shipment"):
        return

    try:
        result = create_shiprocket_order(instance)
        Shipment.objects.create(
            order=instance,
            shiprocket_order_id=str(result.get("order_id", "")),
            shiprocket_shipment_id=str(result.get("shipment_id", "")),
            tracking_status=Shipment.STATUS_PENDING,
        )
    except Exception:
        # Never let a shipping API failure break order confirmation itself --
        # log it so you can see what went wrong and retry/create manually.
        logger.exception("Failed to create Shiprocket shipment for order %s", instance.order_number)