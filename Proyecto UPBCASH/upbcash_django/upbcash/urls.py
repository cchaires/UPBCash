from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("api/", include("commerce.api_urls")),
    path("api/", include("operations.api_urls")),
]
