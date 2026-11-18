from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("learn/assessments/<str:kind>/", views.take, name="take"),
    path("learn/assessments/<str:kind>/start/", views.start, name="start"),
    path("learn/assessments/<str:kind>/save/", views.save, name="save"),
    path("learn/assessments/<str:kind>/submit/", views.submit, name="submit"),
    path("teacher/classes/<int:class_id>/open-posttest/", views.open_posttest, name="open_posttest"),
]
