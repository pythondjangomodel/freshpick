# store/models.py

import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify


# ---------- Accounts ----------

class User(AbstractUser):
    """Custom user model. Set AUTH_USER_MODEL = 'store.User' in settings.py
    BEFORE running your first migration — this can't be changed afterward."""
    phone_number = models.CharField(max_length=15, blank=True)
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.email


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)   # Shiprocket needs this for serviceability checks
    country = models.CharField(max_length=100, default="India")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} — {self.city}, {self.pincode}"


# ---------- Catalog ----------

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    """Weight, dimensions, and hsn_code are here now so Shiprocket integration
    doesn't require a schema migration later."""
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    weight_kg = models.DecimalField(max_digits=6, decimal_places=3, default=0.5)
    length_cm = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    breadth_cm = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    height_cm = models.DecimalField(max_digits=6, decimal_places=2, default=10)
    hsn_code = models.CharField(max_length=10, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    is_primary = models.BooleanField(default=False)

    def __str__(self):
        return f"Image for {self.product.name}"


class ProductVariant(models.Model):
    """Optional — only needed if products have size/color options."""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=100)          # e.g. "Size"
    value = models.CharField(max_length=100)         # e.g. "Large"
    price_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} — {self.name}: {self.value}"


# ---------- Cart ----------

class Cart(models.Model):
    """One cart per logged-in user; guest carts are tracked by session_key instead."""
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name="cart"
    )
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())

    def __str__(self):
        return f"Cart {self.id} ({self.user or self.session_key})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("cart", "product", "variant")

    @property
    def unit_price(self):
        if self.variant and self.variant.price_override:
            return self.variant.price_override
        return self.product.price

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"


# ---------- Orders ----------

class Order(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"      # payment successful — triggers Shiprocket shipment
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order_number = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    shipping_address = models.ForeignKey(Address, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.order_number} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    variant = models.ForeignKey(ProductVariant, null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)  # snapshot at purchase time

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name} (Order {self.order.order_number})"


# ---------- Payments ----------

class Payment(models.Model):
    STATUS_CREATED = "created"
    STATUS_SUCCESS = "success"     # -> flips Order.status to 'confirmed', fires shipping signal
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    gateway = models.CharField(max_length=50, default="razorpay")
    gateway_order_id = models.CharField(max_length=100, blank=True)
    gateway_payment_id = models.CharField(max_length=100, blank=True)
    gateway_signature = models.CharField(max_length=255, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment for {self.order.order_number} ({self.status})"


# ---------- Shipping ----------

class Shipment(models.Model):
    """Created once an Order is confirmed. shiprocket_order_id / shipment_id come back
    from Shiprocket's create-order API response; tracking_status is updated by the webhook."""

    STATUS_PENDING = "pending"
    STATUS_PICKED_UP = "picked_up"
    STATUS_IN_TRANSIT = "in_transit"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PICKED_UP, "Picked up"),
        (STATUS_IN_TRANSIT, "In transit"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="shipment")

    shiprocket_order_id = models.CharField(max_length=100, blank=True)
    shiprocket_shipment_id = models.CharField(max_length=100, blank=True)
    awb_code = models.CharField(max_length=100, blank=True)     # airway bill / tracking number
    courier_name = models.CharField(max_length=100, blank=True)

    tracking_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    tracking_url = models.URLField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Shipment for {self.order.order_number} ({self.tracking_status})"