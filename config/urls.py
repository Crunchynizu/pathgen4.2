from django.contrib import admin
from django.urls import include, path

from config.views import health

urlpatterns = [
    path("health/", health, name="health"),
    # Django's own tools. The product's admin console (/admin-console/) is a separate page.
    path("django-admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.classrooms.urls")),
    path("", include("apps.assessments.urls")),
    path("", include("apps.practice.urls")),
    path("", include("apps.curriculum.urls")),
    path("", include("apps.dashboards.urls")),
]
