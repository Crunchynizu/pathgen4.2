from django.urls import path

from . import views

app_name = "classrooms"

urlpatterns = [
    path("admin-console/accounts/new-teacher/", views.create_teacher, name="create_teacher"),
    path("admin-console/accounts/new-student/", views.create_student, name="create_student"),
    path("admin-console/classes/new/", views.create_classroom, name="create_classroom"),
]
