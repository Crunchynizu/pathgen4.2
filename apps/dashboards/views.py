"""Role dashboards (docs/pages.md, templates 3, 4 and 6).

Every view checks the role, and teacher views also check that the class is theirs.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import ADMIN, STUDENT, TEACHER, landing_url, role_required
from apps.assessments.models import AssessmentAnswer, AssessmentAttempt, AssessmentForm, Kind
from apps.assessments.services import coverage, journey_for, release_for, score_change
from apps.classrooms.forms import ClassroomCreateForm, StudentCreateForm, TeacherCreateForm
from apps.classrooms.models import Classroom, StudentProfile
from apps.curriculum.models import Lesson, LessonSkill, Skill, SkillPrerequisite
from apps.practice.models import Exercise, ExerciseAssignment, ExerciseSession, StudentSkillMastery
from apps.practice.authoring import draft_of
from apps.practice.services import active_assignments, exercise_cards
from learning import progress

from .navigation import ADMIN_SECTIONS, TEACHER_SECTIONS

User = get_user_model()



@login_required
def home(request):
    return redirect(landing_url(request.user))


# ---- Admin console ------------------------------------------------------------------------

@role_required(ADMIN)
def admin_console(request, section):
    return render_admin_console(request, section)


def render_admin_console(request, section, *, teacher_form=None, class_form=None, student_form=None,
                         open_dialog=None):
    if section not in dict(ADMIN_SECTIONS):
        raise Http404("No such section.")
    teachers = User.objects.filter(role=User.Role.TEACHER).annotate(class_count=Count("classrooms")).order_by(
        "display_name", "username"
    )
    classes = Classroom.objects.select_related("teacher").annotate(student_count=Count("students"))
    context = {
        "section": section,
        "sections": ADMIN_SECTIONS,
        "open_dialog": open_dialog,
        "teachers": teachers,
        "classes": classes,
        "teacher_form": teacher_form or TeacherCreateForm(),
        "class_form": class_form or ClassroomCreateForm(),
        "student_form": student_form or StudentCreateForm(),
    }
    if section == "overview":
        context["counts"] = {
            "teachers": teachers.count(),
            "classes": classes.count(),
            "students": StudentProfile.objects.count(),
            "lessons": Lesson.objects.count(),
            "skills": Skill.objects.count(),
            "pretests": AssessmentAttempt.objects.filter(kind=Kind.PRETEST, state="submitted").count(),
            "posttests": AssessmentAttempt.objects.filter(kind=Kind.POSTTEST, state="submitted").count(),
        }
    elif section == "accounts":
        context["students"] = StudentProfile.objects.select_related("user", "classroom").order_by(
            "classroom__name", "user__username"
        )
        context["admins"] = User.objects.filter(role=User.Role.ADMIN).order_by("username")
    elif section == "lessons":
        context["lessons"] = Lesson.objects.prefetch_related(
            Prefetch("skill_links", queryset=LessonSkill.objects.select_related("skill").order_by("skill__sort_order"))
        ).order_by("sort_order")
        context["prerequisites"] = SkillPrerequisite.objects.select_related(
            "skill", "prerequisite__lesson"
        ).order_by("skill__sort_order", "prerequisite__sort_order")
    elif section == "assessments":
        forms = []
        for form in AssessmentForm.objects.order_by("kind", "-revision"):
            counts, missing = coverage(form)
            forms.append({"form": form, "items": form.items.count(), "coverage": counts.items(), "missing": missing,
                          "attempts": form.attempts.count()})
        context["forms"] = forms
    return render(request, "dashboards/admin_dashboard.html", context, status=400 if open_dialog else 200)


# ---- Teacher dashboard --------------------------------------------------------------------

def _class_summaries(teacher):
    classes = (
        Classroom.objects.filter(teacher=teacher)
        .annotate(student_count=Count("students", distinct=True))
        .order_by("name")
    )
    summaries = []
    for classroom in classes:
        submitted = AssessmentAttempt.objects.filter(classroom=classroom, state="submitted")
        summaries.append(
            {
                "classroom": classroom,
                "students": classroom.student_count,
                "pretests": submitted.filter(kind=Kind.PRETEST).count(),
                "posttests": submitted.filter(kind=Kind.POSTTEST).count(),
                "release": release_for(classroom),
                "exercises": active_assignments(classroom).count(),
            }
        )
    return summaries


@role_required(TEACHER)
def teacher_dashboard(request, section):
    if section not in dict(TEACHER_SECTIONS):
        raise Http404("No such section.")
    context = {"section": section, "sections": TEACHER_SECTIONS}
    if section in ("overview", "classes"):
        context["summaries"] = _class_summaries(request.user)
    if section in ("overview", "exercises"):
        exercises = list(
            Exercise.objects.filter(owner_teacher=request.user)
            .select_related("lesson", "active_revision")
            .prefetch_related(
                Prefetch("assignments", queryset=ExerciseAssignment.objects.select_related("classroom")),
            )
            .annotate(pool=Count("active_revision__questions", distinct=True))
            .order_by("lesson__sort_order", "id")
        )
        for exercise in exercises:
            exercise.draft = draft_of(exercise)
            exercise.shown = exercise.draft or exercise.active_revision
        context["exercises"] = exercises
        context["drafts"] = [e for e in exercises if e.active_revision_id is None]
        context["published"] = [e for e in exercises if e.active_revision_id is not None]
    return render(request, "dashboards/teacher_dashboard.html", context)


def _practice_by_student(students, exercise_ids):
    """Per student: assigned exercises finished, and first-try right out of asked (first sessions)."""
    result = {}
    for session in ExerciseSession.objects.filter(student__in=students, exercise_id__in=exercise_ids, status="completed"):
        row = result.setdefault(session.student_id, {"finished": set(), "right": 0, "asked": 0})
        row["finished"].add(session.exercise_id)
        if session.attempt_number == 1:
            row["right"] += session.first_try_correct or 0
            row["asked"] += session.target_count
    for row in result.values():
        row["finished"] = len(row["finished"])
        row["percent"] = round(100 * row["right"] / row["asked"], 1) if row["asked"] else None
    return result


def _skill_gaps(students):
    """Per skill: how many students read Doing well / Needs practice / Not yet practiced."""
    total = len(students)
    counts = {}
    for row in StudentSkillMastery.objects.filter(student__in=students, evidence_count__gt=0):
        text = progress.label(row.mastery_probability, row.evidence_count)
        bucket = counts.setdefault(row.skill_id, {progress.DOING_WELL: 0, progress.NEEDS_PRACTICE: 0})
        bucket[text] += 1
    gaps = []
    for skill in Skill.objects.order_by("sort_order"):
        bucket = counts.get(skill.id, {progress.DOING_WELL: 0, progress.NEEDS_PRACTICE: 0})
        well, needs = bucket[progress.DOING_WELL], bucket[progress.NEEDS_PRACTICE]
        gaps.append({"skill": skill, "well": well, "needs": needs, "none": total - well - needs})
    return gaps


def _scores_by_skill(roster):
    """Per skill: percent correct on the pretest and the posttest, for students with both tests."""
    paired = [row["user"] for row in roster if row["change"] is not None]
    if not paired:
        return [], 0
    tally = {}
    answers = AssessmentAnswer.objects.filter(
        attempt__student__in=paired, attempt__state="submitted",
    ).values_list("attempt__kind", "item__skill_id", "is_correct")
    for kind, skill_id, correct in answers:
        bucket = tally.setdefault(skill_id, {Kind.PRETEST: [0, 0], Kind.POSTTEST: [0, 0]})
        bucket[kind][0] += int(bool(correct))
        bucket[kind][1] += 1
    rows = []
    for skill in Skill.objects.order_by("sort_order"):
        if skill.id not in tally:
            continue
        pre, post = tally[skill.id][Kind.PRETEST], tally[skill.id][Kind.POSTTEST]
        pre_pct = round(100 * pre[0] / pre[1], 1) if pre[1] else None
        post_pct = round(100 * post[0] / post[1], 1) if post[1] else None
        change = round(post_pct - pre_pct, 1) if pre_pct is not None and post_pct is not None else None
        rows.append({"skill": skill, "pre": pre_pct, "post": post_pct, "change": change,
                     "items": pre[1] // len(paired)})
    return rows, len(paired)


def _charts(gaps, by_skill):
    """Data for static/js/charts.js; the tables on the page hold the same numbers."""
    return {
        "gaps": {
            "labels": [gap["skill"].short_name for gap in gaps],
            "series": [
                {"label": "Needs practice", "color": "#d4920f", "values": [gap["needs"] for gap in gaps]},
                {"label": "Doing well", "color": "#158a4f", "values": [gap["well"] for gap in gaps]},
                {"label": "Not yet practiced", "color": "#c7cfd6", "values": [gap["none"] for gap in gaps]},
            ],
            "stacked": True, "unit": "students",
        },
        "scores": {
            "labels": [row["skill"].short_name for row in by_skill],
            "series": [
                {"label": "Pretest", "color": "#0a9db8", "values": [row["pre"] for row in by_skill]},
                {"label": "Posttest", "color": "#5b4fd6", "values": [row["post"] for row in by_skill]},
            ],
            "stacked": False, "unit": "%", "max": 100,
        },
    }


def _scores_by_student(students):
    scores = {}
    for attempt in AssessmentAttempt.objects.filter(student__in=students):
        scores.setdefault(attempt.student_id, {})[attempt.kind] = attempt
    return scores


@role_required(TEACHER)
def teacher_class(request, class_id):
    classroom = get_object_or_404(Classroom, pk=class_id, teacher=request.user)
    profiles = list(StudentProfile.objects.filter(classroom=classroom).select_related("user").order_by("user__username"))
    scores = _scores_by_student([profile.user for profile in profiles])
    roster = []
    for profile in profiles:
        own = scores.get(profile.user_id, {})
        pre, post = own.get(Kind.PRETEST), own.get(Kind.POSTTEST)
        change = score_change(pre, post)
        roster.append({"user": profile.user, "pre": pre, "post": post, "change": change})
    assignments = list(active_assignments(classroom))
    practice = _practice_by_student([row["user"] for row in roster], [a.exercise_id for a in assignments])
    for row in roster:
        row["practice"] = practice.get(row["user"].id, {"finished": 0, "right": 0, "asked": 0})
    gaps = _skill_gaps([row["user"] for row in roster])
    by_skill, paired_count = _scores_by_skill(roster)
    return render(
        request,
        "dashboards/teacher_dashboard.html",
        {
            "section": "classes",
            "sections": TEACHER_SECTIONS,
            "view": "class",
            "classroom": classroom,
            "roster": roster,
            "release": release_for(classroom),
            "pretests_done": sum(1 for row in roster if row["pre"] and row["pre"].is_submitted),
            "assignments": assignments,
            "assigned_count": len(assignments),
            "gaps": gaps,
            "by_skill": by_skill,
            "paired_count": paired_count,
            "charts": _charts(gaps, by_skill),
            "has_posttest": AssessmentForm.objects.filter(kind=Kind.POSTTEST, state="published").exists(),
        },
    )


@role_required(TEACHER)
def teacher_student(request, class_id, student_id):
    classroom = get_object_or_404(Classroom, pk=class_id, teacher=request.user)
    profile = get_object_or_404(StudentProfile.objects.select_related("user"), classroom=classroom, user_id=student_id)
    journey = journey_for(profile.user)
    return render(
        request,
        "dashboards/teacher_dashboard.html",
        {
            "section": "classes",
            "sections": TEACHER_SECTIONS,
            "view": "student",
            "classroom": classroom,
            "student": profile.user,
            "journey": journey,
            "skills": _skill_rows(profile.user),
            "practice_sessions": ExerciseSession.objects.filter(student=profile.user)
            .select_related("exercise__lesson", "revision").order_by("exercise__lesson__sort_order", "attempt_number"),
        },
    )


# ---- Student journey ----------------------------------------------------------------------

def _skill_rows(student):
    """The ten skills with their labels, and a review suggestion when a skill needs practice
    (docs/special_algo.md §4: prerequisites suggest review; they never lock anything)."""
    saved = {row.skill_id: row for row in StudentSkillMastery.objects.filter(student=student)}
    skills = list(Skill.objects.select_related("lesson").order_by("sort_order"))
    labels = {}
    for skill in skills:
        row = saved.get(skill.id)
        labels[skill.id] = progress.label(row.mastery_probability if row else None, row.evidence_count if row else 0)
    links = {}
    for link in SkillPrerequisite.objects.select_related("prerequisite__lesson"):
        links.setdefault(link.skill_id, []).append(link.prerequisite)
    rows = []
    for skill in skills:
        text = labels[skill.id]
        review = []
        if text == progress.NEEDS_PRACTICE:
            review = [p for p in links.get(skill.id, []) if labels[p.id] != progress.DOING_WELL]
        rows.append({"skill": skill, "label": text, "tone": progress.tone(text), "review": review,
                     "mastery": saved[skill.id].mastery_probability if skill.id in saved else None})
    return rows


@role_required(STUDENT)
def learn(request):
    journey = journey_for(request.user)
    cards = exercise_cards(request.user) if journey.pretest_done else []
    per_lesson = {}
    for card in cards:
        per_lesson.setdefault(card["exercise"].lesson_id, []).append(card)

    skills = _skill_rows(request.user)
    stages = [{
        "kind": "pretest",
        "title": "Pretest",
        "state": "done" if journey.pretest_done else "current",
        "url": "assessments:take",
        "arg": "pretest",
    }]
    lessons = list(Lesson.objects.order_by("sort_order"))
    for lesson in lessons:
        stages.append({
            "kind": "lesson",
            "lesson": lesson,
            "title": lesson.title,
            "state": "open" if journey.pretest_done else "locked",
            "exercises": len(per_lesson.get(lesson.id, [])),
            "finished": sum(1 for card in per_lesson.get(lesson.id, []) if card["finished"]),
            "skills": [row for row in skills if row["skill"].lesson_id == lesson.id],
        })
    # "Up next": the first lesson with practice still to do (the first lesson if none is left).
    lesson_stages = [stage for stage in stages if stage["kind"] == "lesson"]
    up_next = next((stage for stage in lesson_stages if stage["finished"] < stage["exercises"]),
                   lesson_stages[0] if lesson_stages else None)
    practice_total = sum(stage["exercises"] for stage in lesson_stages)
    practice_done = sum(stage["finished"] for stage in lesson_stages)
    stages.append({
        "kind": "posttest",
        "title": "Posttest",
        "state": "done" if journey.posttest_done else ("current" if journey.posttest_open else "locked"),
        "url": "assessments:take",
        "arg": "posttest",
    })
    return render(
        request,
        "dashboards/student_dashboard.html",
        {
            "nav": "journey",
            "journey": journey,
            "stages": stages,
            "skills": skills,
            "first_lesson": lessons[0] if lessons else None,
            "up_next": up_next,
            "practice_total": practice_total,
            "practice_done": practice_done,
            "skills_well": sum(1 for row in skills if row["tone"] == "well"),
        },
    )
