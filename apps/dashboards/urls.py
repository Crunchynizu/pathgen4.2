from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "dashboards"

urlpatterns = [
    path("", views.home, name="home"),
    path("admin-console/", RedirectView.as_view(pattern_name="dashboards:admin", permanent=False),
         {"section": "overview"}),
    path("admin-console/<slug:section>/", views.admin_console, name="admin"),
    path("teacher/", RedirectView.as_view(pattern_name="dashboards:teacher", permanent=False),
         {"section": "overview"}),
    path("teacher/classes/<int:class_id>/", views.teacher_class, name="teacher_class"),
    path("teacher/classes/<int:class_id>/students/<int:student_id>/", views.teacher_student, name="teacher_student"),
    path("teacher/<slug:section>/", views.teacher_dashboard, name="teacher"),
    path("learn/", views.learn, name="learn"),
]
