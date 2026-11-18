"""The admin console's create dialogs (docs/modals.md, dialogs 1-3). POST only.

On a validation error the section is shown again with the dialog open and the values kept.
"""
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.accounts.permissions import ADMIN, role_required
from apps.dashboards.views import render_admin_console

from . import services
from .forms import ClassroomCreateForm, StudentCreateForm, TeacherCreateForm


def _apply_errors(form, error):
    if hasattr(error, "error_dict"):
        for field, field_errors in error.message_dict.items():
            form.add_error(field if field in form.fields else None, field_errors)
    else:
        form.add_error(None, error.messages)


@require_POST
@role_required(ADMIN)
def create_teacher(request):
    form = TeacherCreateForm(request.POST)
    if form.is_valid():
        try:
            teacher = services.create_teacher(**form.cleaned_data)
        except ValidationError as error:
            _apply_errors(form, error)
        else:
            messages.success(request, f"Teacher account {teacher.username} is ready. Next, create a class.")
            return redirect("dashboards:admin", section="accounts")
    return render_admin_console(request, "accounts", teacher_form=form, open_dialog="dialog-create-teacher")


@require_POST
@role_required(ADMIN)
def create_classroom(request):
    form = ClassroomCreateForm(request.POST)
    if form.is_valid():
        try:
            classroom = services.create_classroom(**form.cleaned_data)
        except ValidationError as error:
            _apply_errors(form, error)
        else:
            messages.success(request, f"Class {classroom.name} is ready. Next, add its students.")
            return redirect("dashboards:admin", section="classes")
    return render_admin_console(request, "classes", class_form=form, open_dialog="dialog-create-class")


@require_POST
@role_required(ADMIN)
def create_student(request):
    form = StudentCreateForm(request.POST)
    if form.is_valid():
        try:
            student = services.create_student(**form.cleaned_data)
        except ValidationError as error:
            _apply_errors(form, error)
        else:
            messages.success(request, f"Student account {student.username} is in {form.cleaned_data['classroom']}.")
            return redirect("dashboards:admin", section="accounts")
    return render_admin_console(request, "accounts", student_form=form, open_dialog="dialog-create-student")
