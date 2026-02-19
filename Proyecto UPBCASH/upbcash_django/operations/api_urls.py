from django.urls import path

from . import api_views

urlpatterns = [
    path("events/<int:event_id>/staff/assign-vendor", api_views.assign_vendor_api, name="api_assign_vendor"),
    path("events/<int:event_id>/staff/assign-spot", api_views.assign_spot_api, name="api_assign_spot"),
    path("events/<int:event_id>/staff/grant-ucoins", api_views.grant_ucoins_api, name="api_grant_ucoins"),
]
