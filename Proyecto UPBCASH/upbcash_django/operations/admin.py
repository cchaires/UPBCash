from django.contrib import admin

from .models import StaffAuditLog, SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ("summary", "event", "user", "ticket_type", "status", "created_at", "resolved_at")
    list_filter = ("event", "ticket_type", "status")
    search_fields = ("summary", "user__username")


@admin.register(StaffAuditLog)
class StaffAuditLogAdmin(admin.ModelAdmin):
    list_display = ("event", "staff_user", "action_type", "target_content_type", "target_object_id", "created_at")
    list_filter = ("event", "action_type")
    search_fields = ("staff_user__username",)
    date_hierarchy = "created_at"
