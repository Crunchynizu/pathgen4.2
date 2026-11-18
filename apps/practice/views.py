from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import STUDENT, TEACHER, role_required
from apps.assessments.services import pretest_submitted
from apps.dashboards.navigation import TEACHER_SECTIONS

from . import engine, feedback, services
from .models import Exercise, ExerciseSession, SessionQuestion


def _exercise_for_student(request, exercise_id):
    """The exercise if this student may see it: assigned to their class, or already started."""
    item = get_object_or_404(Exercise.objects.select_related("lesson", "active_revision"), pk=exercise_id)
    sessions = engine.sessions_for(request.user, item)
    if not sessions and not services.student_can_open(request.user, item):
        raise Http404("This exercise isn't assigned to your class.")
    return item, sessions


def _page(exercise_id, done=None):
    url = reverse("practice:exercise", args=[exercise_id])
    return f"{url}?done={done}" if done else url


def _choices(question, hide_key=True):
    return [
        {"id": c.id, "letter": c.letter, "text": c.text, "is_correct": None if hide_key else c.is_correct}
        for c in question.choices.order_by("position")
    ]


def _session_rows(sessions):
    rows = []
    for session in sessions:
        if not session.is_completed:
            continue
        rows.append({
            "session": session,
            "feedback": getattr(session, "feedback", None),
            "items": session.items.select_related("question__skill").order_by("position"),
        })
    return rows


@role_required(STUDENT)
def exercise(request, exercise_id):
    """The shared exercise screen: start, question, retry, checked answer, results (docs/pages.md #13)."""
    if not pretest_submitted(request.user):
        messages.info(request, "Take the pretest first. Then all six lessons and their practice open.")
        return redirect("dashboards:learn")
    item, sessions = _exercise_for_student(request, exercise_id)
    open_session = next((s for s in sessions if not s.is_completed), None)
    revision = open_session.revision if open_session else item.active_revision
    context = {
        "exercise": item,
        "lesson": item.lesson,
        "revision": revision,
        "skills": revision.required_skills.order_by("sort_order"),
        "assigned": services.student_can_open(request.user, item),
        "sessions": sessions,
    }

    done_id = request.GET.get("done")
    if done_id and done_id.isdigit():
        checked = (
            SessionQuestion.objects.filter(pk=int(done_id), session__student=request.user, session__exercise=item,
                                           completed_at__isnull=False)
            .select_related("question__skill", "session").first()
        )
        if checked:
            attempts = list(checked.attempts.order_by("attempt_number"))
            context.update({
                "state": "checked",
                "item": checked,
                "session": checked.session,
                "choices": _choices(checked.question, hide_key=False),
                "picked": [a.choice_id for a in attempts],
                "attempts": attempts,
            })
            return render(request, "practice/exercise.html", context)

    if open_session:
        current = engine.current_item(open_session)
        if current is None and not engine.repair(open_session):
            context.update({"state": "stuck", "session": open_session})
            return render(request, "practice/exercise.html", context, status=503)
        current = current or engine.current_item(open_session)
        if current.shown_at is None:
            SessionQuestion.objects.filter(pk=current.pk, shown_at__isnull=True).update(shown_at=timezone.now())
        attempts = list(current.attempts.order_by("attempt_number"))
        context.update({
            "state": "retry" if attempts else "question",
            "session": open_session,
            "item": current,
            "choices": _choices(current.question),
            "first_choice": attempts[0].choice_id if attempts else None,
            "done_count": open_session.items.filter(completed_at__isnull=False).count(),
        })
        return render(request, "practice/exercise.html", context)

    if sessions:
        context.update({
            "state": "results",
            "results": _session_rows(sessions),
            "can_retake": len(sessions) == 1 and context["assigned"],
            "llm_enabled": feedback.generation_enabled(),
        })
        return render(request, "practice/exercise.html", context)

    context["state"] = "start"
    return render(request, "practice/exercise.html", context)


def _open_session(request, exercise_id):
    session = (
        ExerciseSession.objects.filter(student=request.user, exercise_id=exercise_id, status="in_progress")
        .select_related("revision").first()
    )
    if session is None:
        raise Http404("There is no practice in progress.")
    return session


@require_POST
@role_required(STUDENT)
def start(request, exercise_id):
    if not pretest_submitted(request.user):
        return redirect("dashboards:learn")
    item, _sessions = _exercise_for_student(request, exercise_id)
    try:
        engine.start(request.user, item, retake=request.POST.get("retake") == "1")
    except engine.PracticeError as error:
        messages.error(request, str(error))
    return redirect(_page(item.id))


@require_POST
@role_required(STUDENT)
def answer(request, exercise_id):
    session = _open_session(request, exercise_id)
    try:
        item = engine.answer(session, request.POST.get("item"), request.POST.get("choice"),
                             request.POST.get("active_seconds"), request.POST.get("video_seconds"))
    except engine.PracticeError as error:
        messages.error(request, str(error))
        return redirect(_page(exercise_id))
    return redirect(_page(exercise_id, item.id if item.is_completed else None))


@require_POST
@role_required(STUDENT)
def hint(request, exercise_id):
    session = _open_session(request, exercise_id)
    try:
        engine.reveal_hint(session, request.POST.get("item"))
    except engine.PracticeError as error:
        messages.error(request, str(error))
    return redirect(_page(exercise_id) + "#hint")


@require_POST
@role_required(STUDENT)
def move_on(request, exercise_id):
    session = _open_session(request, exercise_id)
    try:
        item = engine.move_on(session, request.POST.get("item"))
    except engine.PracticeError as error:
        messages.error(request, str(error))
        return redirect(_page(exercise_id))
    return redirect(_page(exercise_id, item.id if item.is_completed else None))


@require_POST
@role_required(STUDENT)
def generate_feedback(request, exercise_id):
    """docs/rag.md, v1 default: the results page asks once; the saved text is already showing."""
    session_id = request.POST.get("session", "")
    session = get_object_or_404(
        ExerciseSession, pk=int(session_id) if session_id.isdigit() else 0, student=request.user,
        exercise_id=exercise_id, status=ExerciseSession.Status.COMPLETED,
    )
    saved = getattr(session, "feedback", None)
    if saved is None:
        raise Http404("No feedback for this practice.")
    saved = feedback.generate(saved)
    return JsonResponse({
        "status": saved.generation,
        "generated": saved.source == saved.Source.GENERATED,
        "text": saved.text,
    })


@role_required(TEACHER)
def teacher_exercise(request, exercise_id):
    """Read-only view of the live pool (the editor is at practice:editor)."""
    item = get_object_or_404(
        Exercise.objects.select_related("lesson", "active_revision"), pk=exercise_id, owner_teacher=request.user
    )
    revision = item.active_revision or item.revisions.order_by("-number").first()
    questions = (
        revision.questions.select_related("skill").prefetch_related("choices").order_by("author_order")
        if revision
        else []
    )
    return render(
        request,
        "practice/teacher_exercise.html",
        {
            "exercise": item,
            "revision": revision,
            "questions": questions,
            "skills": revision.required_skills.order_by("sort_order") if revision else [],
            "assignments": item.assignments.select_related("classroom").order_by("classroom__name"),
            "problems": services.validate_revision(revision) if revision and not revision.is_published else [],
            "section": "exercises",
            "sections": TEACHER_SECTIONS,
        },
    )
