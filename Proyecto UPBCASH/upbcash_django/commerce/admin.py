from django.contrib import admin

from .models import CartItem, OrderDeliveryLog, OrderQrToken, SalesOrder, SalesOrderItem


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0
    readonly_fields = ("stall_product", "product_name_snapshot", "unit_price_snapshot", "quantity", "line_total_snapshot")
    can_delete = False


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    """list_filter por status/stall + date_hierarchy: base directa para reportes de
    cuanto se vendio y cuanto se entrego por evento/puesto."""

    list_display = ("order_number", "event", "buyer_user", "stall", "status", "total_ucoin", "created_at", "delivered_at")
    list_filter = ("event", "status", "stall")
    search_fields = ("order_number", "buyer_user__username")
    inlines = [SalesOrderItemInline]
    date_hierarchy = "created_at"


admin.site.register(CartItem)
admin.site.register(OrderQrToken)
admin.site.register(OrderDeliveryLog)
