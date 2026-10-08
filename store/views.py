# store/views.py
import razorpay
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404

from .forms import AddressForm, SignupForm
from .models import (
    Product, Category, Cart, CartItem, ProductVariant,
    Address, Order, OrderItem, Payment,
)
from .utils import find_stock_problems

razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def _get_or_create_cart(request):
    """Guests get a cart tied to their browser session; logged-in users get one tied to their account."""
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user)
    else:
        if not request.session.session_key:
            request.session.create()
        cart, _ = Cart.objects.get_or_create(session_key=request.session.session_key, user=None)
    return cart


def product_list_view(request):
    products = Product.objects.filter(is_active=True).select_related("category")

    category_slug = request.GET.get("category")
    if category_slug:
        products = products.filter(category__slug=category_slug)

    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(name__icontains=query)

    categories = Category.objects.all()
    return render(
        request,
        "store/product_list.html",
        {
            "products": products,
            "categories": categories,
            "active_category": category_slug,
            "query": query,
        },
    )


def product_detail_view(request, slug):
    product = get_object_or_404(Product.objects.select_related("category"), slug=slug, is_active=True)
    variants = product.variants.all()
    return render(request, "store/product_detail.html", {"product": product, "variants": variants})


def cart_detail_view(request):
    cart = _get_or_create_cart(request)
    return render(request, "store/cart_detail.html", {"cart": cart})


def cart_add_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    cart = _get_or_create_cart(request)

    variant_id = request.POST.get("variant_id")
    variant = get_object_or_404(ProductVariant, pk=variant_id) if variant_id else None
    quantity = int(request.POST.get("quantity", 1))

    item, created = CartItem.objects.get_or_create(cart=cart, product=product, variant=variant)
    item.quantity = item.quantity + quantity if not created else quantity
    item.save()

    return redirect("store:cart_detail")


def cart_update_view(request, item_id):
    cart = _get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    quantity = int(request.POST.get("quantity", 1))
    if quantity <= 0:
        item.delete()
    else:
        item.quantity = quantity
        item.save()
    return redirect("store:cart_detail")


def cart_remove_view(request, item_id):
    cart = _get_or_create_cart(request)
    item = get_object_or_404(CartItem, pk=item_id, cart=cart)
    item.delete()
    return redirect("store:cart_detail")


# ---------- Checkout ----------

@login_required
def checkout_view(request):
    cart = _get_or_create_cart(request)

    if not cart.items.exists():
        return redirect("store:cart_detail")

    addresses = request.user.addresses.all()
    form = AddressForm()

    if request.method == "POST":
        if "add_address" in request.POST:
            form = AddressForm(request.POST)
            if form.is_valid():
                address = form.save(commit=False)
                address.user = request.user
                address.save()
                return redirect("store:checkout")

        elif "proceed" in request.POST:
            address_id = request.POST.get("address_id")
            if address_id:
                return redirect("store:checkout_confirm", address_id=address_id)

    return render(request, "store/checkout.html", {
        "cart": cart,
        "addresses": addresses,
        "form": form,
    })


@login_required
def checkout_confirm_view(request, address_id):
    cart = _get_or_create_cart(request)
    address = get_object_or_404(Address, pk=address_id, user=request.user)

    if not cart.items.exists():
        return redirect("store:cart_detail")

    if request.method == "POST":
        # Stop the order before anything is created if the cart asks for more than we have.
        problems = find_stock_problems(cart)
        if problems:
            for problem in problems:
                messages.error(request, problem)
            return redirect("store:cart_detail")

        payment_method = request.POST.get("payment_method", "cod")

        with transaction.atomic():
            subtotal = cart.total_price
            shipping_fee = 0
            total = subtotal + shipping_fee

            order = Order.objects.create(
                user=request.user,
                shipping_address=address,
                subtotal=subtotal,
                shipping_fee=shipping_fee,
                total=total,
            )

            for item in cart.items.select_related("product", "variant"):
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    variant=item.variant,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                )

            payment = Payment.objects.create(
                order=order,
                amount=total,
                gateway="cod" if payment_method == "cod" else "razorpay",
                status=Payment.STATUS_CREATED,
            )

        if payment_method == "cod":
            cart.items.all().delete()
            return redirect("store:order_success", order_number=order.order_number)

        # Card payment: create a Razorpay order and send the user to the payment page.
        # Cart is NOT cleared yet -- only after payment actually succeeds.
        razorpay_order = razorpay_client.order.create({
            "amount": int(total * 100),  # Razorpay expects paise, not rupees
            "currency": "INR",
            "receipt": str(order.order_number),
        })
        payment.gateway_order_id = razorpay_order["id"]
        payment.save()

        return render(request, "store/payment.html", {
            "order": order,
            "razorpay_key": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order["id"],
            "amount_paise": int(total * 100),
        })

    return render(request, "store/checkout_confirm.html", {"address": address, "cart": cart})


@login_required
def order_success_view(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    return render(request, "store/order_success.html", {"order": order})


# ---------- Accounts ----------

def signup_view(request):
    if request.user.is_authenticated:
        return redirect("store:product_list")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("store:product_list")
    else:
        form = SignupForm()

    return render(request, "store/signup.html", {"form": form})


@login_required
def order_list_view(request):
    orders = (
        request.user.orders
        .select_related("shipping_address")
        .prefetch_related("items__product")
        .order_by("-created_at")
    )
    return render(request, "store/order_list.html", {"orders": orders})


@login_required
def payment_callback_view(request):
    if request.method != "POST":
        return redirect("store:cart_detail")

    payment_id = request.POST.get("razorpay_payment_id")
    order_id = request.POST.get("razorpay_order_id")
    signature = request.POST.get("razorpay_signature")

    payment = get_object_or_404(Payment, gateway_order_id=order_id, order__user=request.user)

    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        })
    except razorpay.errors.SignatureVerificationError:
        payment.status = Payment.STATUS_FAILED
        payment.save()
        return render(request, "store/payment_failed.html", {"order": payment.order})

    payment.gateway_payment_id = payment_id
    payment.gateway_signature = signature
    payment.status = Payment.STATUS_SUCCESS
    payment.save()

    payment.order.status = Order.STATUS_CONFIRMED
    payment.order.save()

    cart = _get_or_create_cart(request)
    cart.items.all().delete()

    return redirect("store:order_success", order_number=payment.order.order_number)


@login_required
def order_tracking_view(request, order_number):
    order = get_object_or_404(Order, order_number=order_number, user=request.user)
    shipment = getattr(order, "shipment", None)

    step_statuses = [
        (Order.STATUS_PENDING, "Order placed"),
        (Order.STATUS_CONFIRMED, "Confirmed"),
        (Order.STATUS_SHIPPED, "Shipped"),
        (Order.STATUS_DELIVERED, "Delivered"),
    ]
    keys = [status for status, _ in step_statuses]
    current = keys.index(order.status) if order.status in keys else -1

    steps = [
        {"label": label, "done": index <= current}
        for index, (_, label) in enumerate(step_statuses)
    ]

    return render(request, "store/order_tracking.html", {
        "order": order,
        "shipment": shipment,
        "steps": steps,
    })