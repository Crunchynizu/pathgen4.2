"""Read-only: the curriculum comes from seed_curriculum, keyed by stable codes."""
from django.contrib import admin

from .models import Lesson, LessonSkill, Skill, SkillPrerequisite


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Lesson)
class LessonAdmin(ReadOnlyAdmin):
    list_display = ("sort_order", "code", "title", "content_status")


@admin.register(Skill)
class SkillAdmin(ReadOnlyAdmin):
    list_display = ("sort_order", "code", "short_name", "lesson")


@admin.register(LessonSkill)
class LessonSkillAdmin(ReadOnlyAdmin):
    list_display = ("lesson", "skill", "scope")


@admin.register(SkillPrerequisite)
class SkillPrerequisiteAdmin(ReadOnlyAdmin):
    list_display = ("skill", "prerequisite")
