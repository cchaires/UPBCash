from django.urls import path

from . import api_views

urlpatterns = [
    path("events/<int:event_id>/cart/checkout", api_views.CartCheckoutView.as_view(), name="api_checkout_cart"),
    path("orders/<int:order_id>/qr/verify", api_views.VerifyOrderQrView.as_view(), name="api_verify_order_qr"),
]
