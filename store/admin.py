# store/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import (
    User,
    Address,
    Category,
    Product,
    ProductImage,
    ProductVariant,
    Cart,
    CartItem,
    Order,
    OrderItem,
    Payment,
    Shipment,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Extends Django's built-in UserAdmin so phone_number shows up alongside
    the standard username/password/permissions fields."""
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Extra info", {"fields": ("phone_number",)}),
    )
    list_display = ("username", "email", "phone_number", "is_staff")


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("full_name", "user", "city", "pincode", "is_default")
    search_fields = ("full_name", "pincode", "city")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "parent")
    prepopulated_fields = {"slug": ("name",)}


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    """Inlines let you add images and variants directly on the product page
    instead of navigating to separate admin screens."""
    list_display = ("name", "category", "price", "stock_quantity", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "hsn_code")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline, ProductVariantInline]


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "session_key", "total_price")
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """list_editable on 'status' lets you flip an order to 'confirmed' directly
    from the order list — handy for testing before payments are wired up."""
    list_display = ("order_number", "user", "status", "total", "created_at")
    list_filter = ("status",)
    list_editable = ("status",)
    search_fields = ("order_number", "user__username", "user__email")
    inlines = [OrderItemInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "gateway", "amount", "status", "created_at")
    list_filter = ("gateway", "status")


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("order", "awb_code", "courier_name", "tracking_status")
    list_filter = ("tracking_status",)
    search_fields = ("awb_code", "order__order_number")