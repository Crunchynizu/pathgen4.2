from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class PathgenUserAdmin(UserAdmin):
    list_display = ("username", "display_name", "role", "is_active")
    list_filter = ("role", "is_active")
    fieldsets = UserAdmin.fieldsets + (("PathGen", {"fields": ("role", "display_name")}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("PathGen", {"fields": ("role", "display_name")}),)
