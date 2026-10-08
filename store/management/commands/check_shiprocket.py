# store/management/commands/create_test_shipment.py

import requests
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from store.models import Order, Shipment
from store.shiprocket import ShiprocketError, create_shiprocket_order


class Command(BaseCommand):
    help = "Sends one existing order to Shiprocket and prints the full result or error"

    def add_arguments(self, parser):
        parser.add_argument("order_number", help="The order number (long code) shown in admin")

    def handle(self, *args, **options):
        try:
            order = Order.objects.get(order_number=options["order_number"])
        except (Order.DoesNotExist, ValueError, ValidationError):
            raise CommandError("No order found with that order number.")

        if hasattr(order, "shipment"):
            self.stdout.write(self.style.WARNING(
                "This order already has a shipment record "
                f"(Shiprocket order id: {order.shipment.shiprocket_order_id}). Nothing sent."
            ))
            return

        self.stdout.write(f"Sending order {order.order_number} to Shiprocket...")
        try:
            result = create_shiprocket_order(order)
        except ShiprocketError as error:
            self.stdout.write(self.style.ERROR(f"\nShiprocket rejected it:\n{error}"))
            return
        except requests.RequestException as error:
            self.stdout.write(self.style.ERROR(f"\nCould not reach Shiprocket: {error}"))
            return

        Shipment.objects.create(
            order=order,
            shiprocket_order_id=str(result.get("order_id", "")),
            shiprocket_shipment_id=str(result.get("shipment_id", "")),
            tracking_status=Shipment.STATUS_PENDING,
        )

        self.stdout.write(self.style.SUCCESS("\nShiprocket accepted the order."))
        self.stdout.write(f"  Shiprocket order id:    {result.get('order_id')}")
        self.stdout.write(f"  Shiprocket shipment id: {result.get('shipment_id')}")
        self.stdout.write("Check Orders in your Shiprocket dashboard to see it.")