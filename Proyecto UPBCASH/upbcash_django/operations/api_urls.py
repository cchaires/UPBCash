from django.urls import path

from . import api_views

urlpatterns = [
    path("events/<int:event_id>/map/state", api_views.map_state_api, name="api_event_map_state"),
    path("events/<int:event_id>/map/spots", api_views.create_map_spot_api, name="api_event_map_spots_create"),
    path("events/<int:event_id>/map/spots/<int:spot_id>", api_views.map_spot_detail_api, name="api_event_map_spot_detail"),
    path(
        "events/<int:event_id>/stalls/<int:stall_id>/assign-spot",
        api_views.assign_stall_spot_api,
        name="api_event_assign_stall_spot",
    ),
    path(
        "events/<int:event_id>/stalls/<int:stall_id>/add-vendor",
        api_views.add_vendor_to_stall_api,
        name="api_event_add_vendor_to_stall",
    ),
    path("events/<int:event_id>/staff/assign-vendor", api_views.assign_vendor_api, name="api_assign_vendor"),
    path("events/<int:event_id>/staff/assign-spot", api_views.assign_spot_api, name="api_assign_spot"),
    path("events/<int:event_id>/staff/grant-ucoins", api_views.grant_ucoins_api, name="api_grant_ucoins"),
]
