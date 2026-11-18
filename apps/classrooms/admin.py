from django.contrib import admin

from .models import Classroom, StudentProfile


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ("name", "teacher", "created_at")
    search_fields = ("name", "teacher__username")


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "classroom")
    list_filter = ("classroom",)
    search_fields = ("user__username", "user__display_name")
