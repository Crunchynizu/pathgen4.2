from django.urls import path

from . import views

app_name = "curriculum"

urlpatterns = [
    path("learn/lessons/<slug:code>/", views.lesson, name="lesson"),
]
