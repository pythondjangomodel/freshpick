# store/urls.py

from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView

from . import views

app_name = "store"

urlpatterns = [
    path("", views.product_list_view, name="product_list"),
    path("product/<slug:slug>/", views.product_detail_view, name="product_detail"),
    path("cart/", views.cart_detail_view, name="cart_detail"),
    path("cart/add/<int:product_id>/", views.cart_add_view, name="cart_add"),
    path("cart/update/<int:item_id>/", views.cart_update_view, name="cart_update"),
    path("cart/remove/<int:item_id>/", views.cart_remove_view, name="cart_remove"),
    path("checkout/", views.checkout_view, name="checkout"),
    path("checkout/confirm/<int:address_id>/", views.checkout_confirm_view, name="checkout_confirm"),
    path("signup/", views.signup_view, name="signup"),
    path("login/", LoginView.as_view(template_name="store/login.html"), name="login"),
    path("order/success/<uuid:order_number>/", views.order_success_view, name="order_success"),
    path("payment/callback/", views.payment_callback_view, name="payment_callback"),
    path("logout/", LogoutView.as_view(next_page="store:product_list"), name="logout"),
    path("orders/", views.order_list_view, name="order_list"),
    path("orders/<uuid:order_number>/track/", views.order_tracking_view, name="order_tracking"),
]