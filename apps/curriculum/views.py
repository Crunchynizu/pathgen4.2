from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.assessments.services import pretest_submitted
from apps.curriculum.models import LessonSkill
from apps.practice.models import Exercise
from apps.practice.services import exercise_cards

from .models import Lesson


@login_required
def lesson(request, code):
    """A lesson page. Students need a submitted pretest; teachers and admins can preview."""
    item = get_object_or_404(Lesson, code=code)
    user = request.user
    if user.is_student and not pretest_submitted(user):
        messages.info(request, "Take the pretest first. Then all six lessons open.")
        return redirect("dashboards:learn")

    links = LessonSkill.objects.filter(lesson=item).select_related("skill").order_by("skill__sort_order")
    taught = [link.skill for link in links if link.scope == LessonSkill.Scope.TAUGHT]
    review = [link.skill for link in links if link.scope == LessonSkill.Scope.REVIEW]

    if user.is_student:
        cards = exercise_cards(user, item)
    elif user.is_teacher:
        cards = [
            {"exercise": exercise, "revision": exercise.active_revision,
             "skills": list(exercise.active_revision.required_skills.order_by("sort_order"))}
            for exercise in Exercise.objects.filter(owner_teacher=user, lesson=item, active_revision__isnull=False)
            .select_related("active_revision")
        ]
    else:
        cards = []

    lessons = list(Lesson.objects.order_by("sort_order"))
    index = next(i for i, lesson_ in enumerate(lessons) if lesson_.pk == item.pk)
    return render(
        request,
        item.template_name,
        {
            "lesson": item,
            "taught_skills": taught,
            "review_skills": review,
            "cards": cards,
            "preview": not user.is_student,
            "previous_lesson": lessons[index - 1] if index > 0 else None,
            "next_lesson": lessons[index + 1] if index + 1 < len(lessons) else None,
        },
    )
