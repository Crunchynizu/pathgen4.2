"""Read-only views for checking. Published pools are frozen: change content in
content/question_bank.json and run import_bank, which makes a new version."""
from django.contrib import admin

from .models import AnswerChoice, Exercise, ExerciseAssignment, ExerciseRevision, Question


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Exercise)
class ExerciseAdmin(ReadOnlyAdmin):
    list_display = ("id", "lesson", "owner_teacher", "status", "active_revision")


@admin.register(ExerciseRevision)
class RevisionAdmin(ReadOnlyAdmin):
    list_display = ("exercise", "number", "title", "target_count", "state", "published_at", "source_version")


class ChoiceInline(admin.TabularInline):
    model = AnswerChoice
    fields = ("position", "text", "is_correct")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(Question)
class QuestionAdmin(ReadOnlyAdmin):
    list_display = ("item_key", "revision", "skill", "difficulty", "junyi_template", "difficulty_value", "review_status")
    list_filter = ("skill", "difficulty", "review_status")
    search_fields = ("item_key", "prompt")
    inlines = [ChoiceInline]


@admin.register(ExerciseAssignment)
class AssignmentAdmin(ReadOnlyAdmin):
    list_display = ("exercise", "classroom", "status", "published_at")
