"""Read-only views for checking. The locked test and students' answers are never edited here."""
from django.contrib import admin

from .models import AssessmentAnswer, AssessmentAttempt, AssessmentForm, AssessmentItem, ClassAssessmentRelease


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class ItemInline(admin.TabularInline):
    model = AssessmentItem
    fields = ("position", "skill", "prompt", "correct_index")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(AssessmentForm)
class AssessmentFormAdmin(ReadOnlyAdmin):
    list_display = ("kind", "revision", "title", "state", "locked")
    inlines = [ItemInline]


@admin.register(ClassAssessmentRelease)
class ReleaseAdmin(ReadOnlyAdmin):
    list_display = ("classroom", "posttest_form", "opened_by", "opened_at")


class AnswerInline(admin.TabularInline):
    model = AssessmentAnswer
    fields = ("item", "selected_index", "is_correct", "last_saved_at")
    readonly_fields = fields
    extra = 0
    can_delete = False


@admin.register(AssessmentAttempt)
class AttemptAdmin(ReadOnlyAdmin):
    list_display = ("student", "kind", "classroom", "state", "correct_count", "item_count", "submitted_at")
    list_filter = ("kind", "state", "classroom")
    inlines = [AnswerInline]
