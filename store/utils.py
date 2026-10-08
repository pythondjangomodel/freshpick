# store/utils.py

from django.core.mail import send_mail
from django.conf import settings


def send_order_confirmation_email(order):
    """Sends a plain-text order confirmation email to the customer.
    Called from signals.py whenever an order's status changes to 'confirmed'."""

    items_lines = "\n".join(
        f"  - {item.quantity} x {item.product.name} (₹{item.unit_price} each)"
        for item in order.items.select_related("product")
    )

    subject = f"Order confirmed - #{order.order_number}"
    message = f"""Hi {order.user.username},

Your order has been confirmed. Here are the details:

Order number: {order.order_number}
Items:
{items_lines}

Subtotal: ₹{order.subtotal}
Shipping: ₹{order.shipping_fee}
Total: ₹{order.total}

Shipping to:
{order.shipping_address.full_name}
{order.shipping_address.address_line1}
{order.shipping_address.city}, {order.shipping_address.state} - {order.shipping_address.pincode}

We'll notify you again once your order ships.

Thanks for shopping with us!
"""

    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        fail_silently=False,
    )

# ---------- Stock helpers ----------

from django.db.models import F
from django.db.models.functions import Greatest


def _stock_holder(item):
    """Stock is kept on the variant when the item has one, otherwise on the product."""
    return item.variant if item.variant else item.product


def find_stock_problems(cart):
    """Returns messages for any cart item that asks for more than is in stock."""
    problems = []
    for item in cart.items.select_related("product", "variant"):
        available = _stock_holder(item).stock_quantity
        if item.quantity <= available:
            continue

        label = item.product.name
        if item.variant:
            label += f" ({item.variant.value})"

        if available == 0:
            problems.append(f"{label} is out of stock. Please remove it from your cart.")
        else:
            problems.append(f"Only {available} of {label} left in stock. Please reduce the quantity.")
    return problems


def deduct_stock(order):
    """Lowers stock for every item in the order, never below zero."""
    for item in order.items.select_related("product", "variant"):
        holder = _stock_holder(item)
        type(holder).objects.filter(pk=holder.pk).update(
            stock_quantity=Greatest(F("stock_quantity") - item.quantity, 0)
        )


def restore_stock(order):
    """Puts stock back, used when a confirmed order is cancelled."""
    for item in order.items.select_related("product", "variant"):
        holder = _stock_holder(item)
        type(holder).objects.filter(pk=holder.pk).update(
            stock_quantity=F("stock_quantity") + item.quantity
        )
