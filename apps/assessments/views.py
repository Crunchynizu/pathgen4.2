from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import STUDENT, TEACHER, role_required
from apps.classrooms.models import Classroom

from . import services
from .models import Kind


def _kind(kind):
    if kind not in Kind.values:
        raise Http404("No such assessment.")
    return kind


def _selections(post):
    return {key[5:]: value for key, value in post.items() if key.startswith("item-")}


def _is_fetch(request):
    return request.headers.get("x-requested-with") == "fetch"


@role_required(STUDENT)
def take(request, kind, error=None, first_missing=None):
    kind = _kind(kind)
    journey = services.journey_for(request.user)
    attempt = journey.pretest if kind == Kind.PRETEST else journey.posttest
    context = {"kind": kind, "label": Kind(kind).label, "journey": journey, "attempt": attempt, "error": error}

    if attempt is None:
        reason = services.can_start(request.user, kind)
        context["state"] = "blocked" if reason else "intro"
        context["reason"] = reason
        form = services.published_form(kind) if kind == Kind.PRETEST else (journey.release and journey.release.posttest_form)
        context["item_count"] = form.items.count() if form else 0
    elif attempt.is_submitted:
        context["state"] = "submitted"
    else:
        context["state"] = "in_progress"
        saved = dict(attempt.answers.values_list("item_id", "selected_index"))
        items = list(attempt.form.items.order_by("position"))
        context["items"] = [
            {
                "id": item.id,
                "position": item.position,
                "prompt": item.prompt,
                "choices": list(enumerate(item.choices)),
                "selected": saved.get(item.id),
            }
            for item in items
        ]
        context["answered"] = sum(1 for item in context["items"] if item["selected"] is not None)
        context["first_missing"] = first_missing
    return render(request, "assessments/assessment.html", context, status=400 if error else 200)


@require_POST
@role_required(STUDENT)
def start(request, kind):
    kind = _kind(kind)
    try:
        services.start_attempt(request.user, kind)
    except services.AssessmentError as error:
        messages.error(request, str(error))
        return redirect("dashboards:learn")
    return redirect("assessments:take", kind=kind)


@require_POST
@role_required(STUDENT)
def save(request, kind):
    kind = _kind(kind)
    attempt = services.attempt_for(request.user, kind)
    if attempt is None:
        raise Http404("Start the test first.")
    saved = services.save_answers(attempt, _selections(request.POST))
    if _is_fetch(request):
        if not saved:
            return JsonResponse({"saved": False, "reason": "submitted"}, status=409)
        return JsonResponse({"saved": True, "at": timezone.localtime().strftime("%I:%M %p").lstrip("0")})
    if saved:
        messages.success(request, "Your answers are saved.")
    return redirect("assessments:take", kind=kind)


@require_POST
@role_required(STUDENT)
def submit(request, kind):
    kind = _kind(kind)
    attempt = services.attempt_for(request.user, kind)
    if attempt is None:
        raise Http404("Start the test first.")
    services.save_answers(attempt, _selections(request.POST))
    try:
        services.submit_attempt(attempt)
    except services.IncompleteSubmission as error:
        return take(request, kind, error=str(error), first_missing=error.first_missing_position)
    return redirect("assessments:take", kind=kind)


@require_POST
@role_required(TEACHER)
def open_posttest(request, class_id):
    classroom = get_object_or_404(Classroom, pk=class_id, teacher=request.user)
    try:
        _release, created = services.open_posttest(classroom, request.user)
    except services.AssessmentError as error:
        messages.error(request, str(error))
    else:
        if created:
            messages.success(request, f"The posttest is open for {classroom.name}.")
        else:
            messages.info(request, f"The posttest was already open for {classroom.name}.")
    return redirect("dashboards:teacher_class", class_id=classroom.id)
