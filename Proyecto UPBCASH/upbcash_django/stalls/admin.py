from django.contrib import admin

from .models import (
    CatalogProduct,
    MapSpot,
    MapZone,
    ProductCategory,
    ProductSubcategory,
    Stall,
    StallAssignment,
    StallProduct,
    StockMovement,
)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "sort_order")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")


@admin.register(ProductSubcategory)
class ProductSubcategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "slug", "is_active", "sort_order", "default_photo_variant")
    list_filter = ("is_active", "category")
    search_fields = ("name", "slug", "category__name")
    ordering = ("category__sort_order", "sort_order", "name")


@admin.register(StallProduct)
class StallProductAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "event",
        "stall",
        "item_nature",
        "category",
        "subcategory",
        "price_ucoin",
        "cost_ucoin",
        "stock_mode",
        "stock_qty",
        "stock_base_qty",
        "low_stock_threshold",
        "is_active",
    )
    list_filter = ("event", "item_nature", "category", "stock_mode", "is_active")
    search_fields = ("display_name", "stall__name", "catalog_product__sku")


admin.site.register(MapZone)
admin.site.register(MapSpot)
admin.site.register(Stall)
admin.site.register(StallAssignment)
admin.site.register(CatalogProduct)
admin.site.register(StockMovement)
