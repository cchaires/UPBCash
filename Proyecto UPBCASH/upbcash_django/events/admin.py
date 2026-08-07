from django.contrib import admin

from .models import EventCampaign, EventMembership, EventUserGroup


@admin.register(EventCampaign)
class EventCampaignAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "starts_at", "ends_at", "max_map_spots")
    list_filter = ("status",)
    search_fields = ("code", "name")


@admin.register(EventMembership)
class EventMembershipAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "profile_type", "matricula", "created_at")
    list_filter = ("event", "profile_type")
    search_fields = ("user__username", "matricula")


admin.site.register(EventUserGroup)
