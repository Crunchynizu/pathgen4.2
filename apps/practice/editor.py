"""The teacher exercise editor and its dialogs (docs/pages.md #5; docs/modals.md #4, #5, #6, #11),
plus the figure route that serves uploads only to people allowed to see them."""
import mimetypes

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.permissions import TEACHER, role_required
from apps.classrooms.models import Classroom
from apps.classrooms.services import classroom_of
from apps.dashboards.navigation import TEACHER_SECTIONS

from . import authoring, services
from .forms import NewExerciseForm, QuestionFormSet, RevisionForm, initial_for
from .models import Exercise, ExerciseAssignment, ExerciseSession, Question


def _owned_or_404(request, exercise_id):
    try:
        return authoring.owned(request.user, exercise_id)
    except Exercise.DoesNotExist:
        raise Http404("No such exercise.") from None


def _edit_url(exercise_id, **query):
    url = reverse("practice:editor", args=[exercise_id])
    return url + ("?" + "&".join(f"{k}={v}" for k, v in query.items()) if query else "")


def _context(request, exercise, **extra):
    draft = authoring.draft_of(exercise)
    live = exercise.active_revision
    shown = draft or live or exercise.revisions.order_by("-number").first()
    active = list(exercise.assignments.filter(status=ExerciseAssignment.Status.ACTIVE).select_related("classroom"))
    target = authoring.publishable_revision(exercise)
    context = {
        "section": "exercises",
        "sections": TEACHER_SECTIONS,
        "mode": "edit" if draft else "live",
        "exercise": exercise,
        "lesson": exercise.lesson,
        "draft": draft,
        "live": live,
        "revision": shown,
        "skills": shown.required_skills.order_by("sort_order") if shown else [],
        "single_skill": shown is not None and shown.scope == shown.Scope.SINGLE,
        "questions": shown.questions.select_related("skill").prefetch_related("choices").order_by("author_order")
        if shown else [],
        "problems": services.validate_revision(target) if target and not target.is_published else [],
        "classes": Classroom.objects.filter(teacher=request.user).order_by("name"),
        "active_class_ids": {a.classroom_id for a in active},
        "active_assignments": active,
        "can_delete": authoring.can_delete(exercise),
        "started_sessions": ExerciseSession.objects.filter(exercise=exercise, status="in_progress").count(),
        "publish_target": target,
    }
    context.update(extra)
    return context


def _forms_for(draft, data=None, files=None):
    allowed = authoring.allowed_skills(draft.exercise.lesson)
    revision_form = RevisionForm(
        data, skills=allowed,
        initial={"title": draft.title, "target_count": draft.target_count,
                 "required_skills": list(draft.required_skills.values_list("pk", flat=True))},
    )
    questions = draft.questions.select_related("skill").prefetch_related("choices").order_by("author_order")
    formset = QuestionFormSet(data, files, initial=[initial_for(q) for q in questions], prefix="q",
                              form_kwargs={"skills": allowed})
    return revision_form, formset


@role_required(TEACHER)
def new(request):
    """Start a draft for an existing lesson (docs/user_features.md "Teacher")."""
    form = NewExerciseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        exercise = authoring.create_exercise(
            request.user, form.cleaned_data["lesson"], form.cleaned_data["title"], form.cleaned_data["target_count"],
        )
        messages.success(request, "Draft saved. Add the questions below, then publish it to your classes.")
        return redirect(_edit_url(exercise.id))
    return render(request, "practice/exercise_editor.html",
                  {"section": "exercises", "sections": TEACHER_SECTIONS, "mode": "new", "new_form": form},
                  status=400 if form.errors else 200)


@role_required(TEACHER)
def edit(request, exercise_id):
    exercise = _owned_or_404(request, exercise_id)
    draft = authoring.draft_of(exercise)
    if draft is None:
        if request.method == "POST":
            return redirect(_edit_url(exercise.id))
        return render(request, "practice/exercise_editor.html",
                      _context(request, exercise, open_dialog=request.GET.get("dialog")))

    if request.method == "POST":
        revision_form, formset = _forms_for(draft, request.POST, request.FILES)
        if revision_form.is_valid() and formset.is_valid():
            entries = [form.to_entry() for form in formset.ordered_forms if form.has_changed() or form.initial]
            try:
                authoring.save_draft(
                    request.user, exercise.id, draft.id,
                    title=revision_form.cleaned_data["title"],
                    target_count=revision_form.cleaned_data["target_count"],
                    required_skills=list(revision_form.cleaned_data["required_skills"]),
                    questions=entries,
                )
            except authoring.AuthoringError as error:
                messages.error(request, str(error))
                return redirect(_edit_url(exercise.id))
            if request.POST.get("action") == "publish":
                exercise.refresh_from_db()
                if services.validate_revision(authoring.draft_of(exercise)):
                    messages.warning(request, "Draft saved. Fix the points listed below, then publish.")
                    return redirect(_edit_url(exercise.id) + "#problems")
                return redirect(_edit_url(exercise.id, dialog="publish"))
            messages.success(request, "Draft saved.")
            return redirect(_edit_url(exercise.id))
        messages.error(request, "Some fields need a fix before the draft can be saved. They're marked below."
                       + (" Choose any new pictures again." if request.FILES else ""))
        return render(request, "practice/exercise_editor.html",
                      _context(request, exercise, revision_form=revision_form, formset=formset), status=400)

    revision_form, formset = _forms_for(draft)
    return render(request, "practice/exercise_editor.html",
                  _context(request, exercise, revision_form=revision_form, formset=formset,
                           open_dialog=request.GET.get("dialog")))


@require_POST
@role_required(TEACHER)
def start_draft(request, exercise_id):
    _owned_or_404(request, exercise_id)
    try:
        authoring.start_draft(request.user, exercise_id)
    except authoring.AuthoringError as error:
        messages.error(request, str(error))
    else:
        messages.info(request, "This is a new draft, copied from the published version. Students keep the "
                               "published version until you publish this one.")
    return redirect(_edit_url(exercise_id))


@require_POST
@role_required(TEACHER)
def publish(request, exercise_id):
    _owned_or_404(request, exercise_id)
    try:
        revision = authoring.publish(request.user, exercise_id, request.POST.getlist("classes"))
    except services.PublishError as error:
        for problem in error.problems:
            messages.error(request, problem)
        return redirect(_edit_url(exercise_id))
    names = ", ".join(
        a.classroom.name for a in ExerciseAssignment.objects.filter(exercise_id=exercise_id, status="active")
        .select_related("classroom").order_by("classroom__name")
    )
    messages.success(request, f"Published “{revision.title}” to {names}.")
    return redirect(_edit_url(exercise_id))


@require_POST
@role_required(TEACHER)
def unpublish(request, exercise_id):
    _owned_or_404(request, exercise_id)
    classes = authoring.unpublish(request.user, exercise_id)
    if classes:
        messages.success(request, "Unpublished. New starts and retakes are stopped for "
                         + ", ".join(c.name for c in classes) + ". Saved results stay.")
    return redirect(_edit_url(exercise_id))


@require_POST
@role_required(TEACHER)
def delete(request, exercise_id):
    _owned_or_404(request, exercise_id)
    try:
        title = authoring.delete_draft_exercise(request.user, exercise_id)
    except authoring.AuthoringError as error:
        messages.error(request, str(error))
        return redirect(_edit_url(exercise_id))
    messages.success(request, f"Deleted the draft “{title}”.")
    return redirect("dashboards:teacher", section="exercises")


# ---- Uploaded figures ------------------------------------------------------------------------

def _may_see(user, questions):
    if user.is_app_admin:
        return True
    if user.is_teacher:
        return any(q.revision.exercise.owner_teacher_id == user.id for q in questions)
    if user.is_student:
        exercises = {q.revision.exercise for q in questions}
        revisions = {q.revision_id for q in questions}
        if ExerciseSession.objects.filter(student=user, revision_id__in=revisions).exists():
            return True
        assigned = services.active_assignments(classroom_of(user)).filter(exercise__in=exercises)
        return assigned.filter(exercise__active_revision_id__in=revisions).exists()
    return False


@login_required
def figure(request, name):
    """docs/tech_stack.md: uploads go through an authorized route, never a public folder."""
    questions = list(Question.objects.filter(figure_file=name).select_related("revision__exercise"))
    if not questions or not _may_see(request.user, questions):
        raise Http404("No such picture.")
    try:
        handle = default_storage.open(name, "rb")
    except FileNotFoundError:
        raise Http404("No such picture.") from None
    response = FileResponse(handle, content_type=mimetypes.guess_type(name)[0] or "application/octet-stream")
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response
