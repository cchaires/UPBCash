from django.urls import path

from . import api_views

urlpatterns = [
    path("events/<int:event_id>/map/state", api_views.MapStateView.as_view(), name="api_event_map_state"),
    path("events/<int:event_id>/map/spots", api_views.MapSpotCreateView.as_view(), name="api_event_map_spots_create"),
    path(
        "events/<int:event_id>/map/spots/<int:spot_id>",
        api_views.MapSpotDetailView.as_view(),
        name="api_event_map_spot_detail",
    ),
    path(
        "events/<int:event_id>/stalls/<int:stall_id>/assign-spot",
        api_views.AssignStallSpotView.as_view(),
        name="api_event_assign_stall_spot",
    ),
    path(
        "events/<int:event_id>/stalls/<int:stall_id>/add-vendor",
        api_views.AddVendorToStallView.as_view(),
        name="api_event_add_vendor_to_stall",
    ),
    path("events/<int:event_id>/staff/assign-vendor", api_views.AssignVendorView.as_view(), name="api_assign_vendor"),
    path("events/<int:event_id>/staff/assign-spot", api_views.AssignSpotView.as_view(), name="api_assign_spot"),
    path("events/<int:event_id>/staff/grant-ucoins", api_views.GrantUcoinsView.as_view(), name="api_grant_ucoins"),
]
