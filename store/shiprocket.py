# store/shiprocket.py

import re

import requests
from django.conf import settings
from django.core.cache import cache

BASE_URL = "https://apiv2.shiprocket.in/v1/external"
TOKEN_CACHE_KEY = "shiprocket_auth_token"


class ShiprocketError(Exception):
    """Raised when Shiprocket (or our own checks) reject an order.
    The message includes Shiprocket's own reason so you can see what to fix."""


def _login():
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": settings.SHIPROCKET_EMAIL,
            "password": settings.SHIPROCKET_PASSWORD,
        },
        timeout=15,
    )
    if response.status_code != 200:
        raise ShiprocketError(f"Login failed ({response.status_code}): {response.text}")

    token = response.json()["token"]
    # Shiprocket tokens last about 10 days. Cache for 9 so we rarely log in again.
    cache.set(TOKEN_CACHE_KEY, token, timeout=60 * 60 * 24 * 9)
    return token


def _get_auth_token():
    return cache.get(TOKEN_CACHE_KEY) or _login()


def _request(method, path, **kwargs):
    """Calls Shiprocket with the saved token. If the token has expired (401),
    logs in again once and retries. Any other failure raises ShiprocketError
    with Shiprocket's own message."""
    response = None
    for attempt in range(2):
        headers = {
            "Authorization": f"Bearer {_get_auth_token()}",
            "Content-Type": "application/json",
        }
        response = requests.request(
            method, f"{BASE_URL}{path}", headers=headers, timeout=20, **kwargs
        )
        if response.status_code == 401 and attempt == 0:
            cache.delete(TOKEN_CACHE_KEY)
            continue
        break

    if not response.ok:
        raise ShiprocketError(f"{method} {path} failed ({response.status_code}): {response.text}")
    return response.json()


def _clean_phone(number):
    """Keeps digits only and uses the last 10, so '+91 98765 43210' becomes '9876543210'."""
    return re.sub(r"\D", "", number or "")[-10:]


def create_shiprocket_order(order):
    """Builds the order Shiprocket expects from our Order, OrderItem and Address
    models and creates it. Returns Shiprocket's response, which includes
    order_id and shipment_id."""

    address = order.shipping_address
    items = list(order.items.select_related("product"))

    if not items:
        raise ShiprocketError("This order has no items.")

    phone = _clean_phone(address.phone_number)
    if len(phone) != 10:
        raise ShiprocketError(
            f"Phone number '{address.phone_number}' is not a valid 10-digit number. "
            "Fix it on the customer's address."
        )

    pincode = (address.pincode or "").strip()
    if not re.fullmatch(r"\d{6}", pincode):
        raise ShiprocketError(f"Pincode '{address.pincode}' is not a valid 6-digit pincode.")

    # Orders made in admin may have no payment record, so look it up safely.
    payment = getattr(order, "payment", None)
    is_prepaid = bool(payment and payment.gateway == "razorpay")

    order_items = []
    for item in items:
        line = {
            "name": item.product.name,
            "sku": str(item.product.id),
            "units": item.quantity,
            "selling_price": float(item.unit_price),
        }
        if item.product.hsn_code:
            line["hsn"] = item.product.hsn_code
        order_items.append(line)

    # Shiprocket wants one weight and one box size for the whole shipment.
    # Weight is the sum of every item; the box uses the heaviest item's size.
    total_weight = sum(float(item.product.weight_kg) * item.quantity for item in items)
    heaviest = max(items, key=lambda i: i.product.weight_kg)

    payload = {
        "order_id": str(order.order_number),
        "order_date": order.created_at.strftime("%Y-%m-%d %H:%M"),
        "pickup_location": settings.SHIPROCKET_PICKUP_LOCATION,
        "billing_customer_name": address.full_name,
        "billing_last_name": "",
        "billing_address": address.address_line1,
        "billing_address_2": address.address_line2,
        "billing_city": address.city,
        "billing_pincode": pincode,
        "billing_state": address.state,
        "billing_country": address.country,
        "billing_email": order.user.email,
        "billing_phone": phone,
        "shipping_is_billing": True,
        "order_items": order_items,
        "payment_method": "Prepaid" if is_prepaid else "COD",
        "sub_total": float(order.subtotal),
        "length": float(heaviest.product.length_cm),
        "breadth": float(heaviest.product.breadth_cm),
        "height": float(heaviest.product.height_cm),
        "weight": total_weight or 0.5,
    }

    result = _request("POST", "/orders/create/adhoc", json=payload)

    # Shiprocket can answer with a normal status code but no order inside.
    # Without this check we would save a blank shipment and think it worked.
    if not result.get("order_id"):
        raise ShiprocketError(f"Shiprocket did not return an order id. Full response: {result}")

    return result