"""The curriculum contract (docs/system.md, "Curriculum contract"), seeded by stable codes.

Running it again updates names and links in place and never adds duplicates.
"""
from django.db import transaction

from .models import Lesson, LessonSkill, Skill, SkillPrerequisite

LESSONS = [
    # code, title, summary
    ("integer_foundation", "Integer Foundations",
     "Integers on the number line, opposites, absolute value, comparing and ordering."),
    ("integer_addition", "Adding Integers", "Add integers with the same and different signs."),
    ("integer_subtraction", "Subtracting Integers", "Subtract integers by adding the opposite."),
    ("integer_multiplication", "Multiplying Integers", "Multiply integers and find the sign of a product."),
    ("integer_division", "Dividing Integers", "Divide integers and find the sign of a quotient."),
    ("integer_expressions_applications", "Expressions and Applications",
     "Order of operations with integers, and real situations with signed quantities."),
]

SKILLS = [
    # code, short name, full name, canonical lesson
    ("INT_NUMBER_LINE", "Number line",
     "Identify and represent integers and zero on a number line.", "integer_foundation"),
    ("INT_OPPOSITE_POS4", "Opposites", "Find the opposite of an integer.", "integer_foundation"),
    ("INT_ABS_COMPARE", "Absolute value", "Interpret and calculate absolute value.", "integer_foundation"),
    ("INT_ORDER_NEG", "Compare and order", "Compare and order integers.", "integer_foundation"),
    ("INT_ADD_NEG", "Addition", "Add integers.", "integer_addition"),
    ("INT_SUB_NEG", "Subtraction", "Subtract integers.", "integer_subtraction"),
    ("INT_MULT_NEG", "Multiplication", "Multiply integers.", "integer_multiplication"),
    ("INT_DIV_NEG", "Division", "Divide integers.", "integer_division"),
    ("INT_EXPR_NEG", "Expressions",
     "Evaluate integer expressions using the order of operations.", "integer_expressions_applications"),
    ("INT_CONTEXT", "Signed quantities",
     "Solve situations involving signed quantities and changes.", "integer_expressions_applications"),
]

# Only Expressions and Applications has the approved cumulative review of skills 5-8.
REVIEW_SCOPE = {
    "integer_expressions_applications": ["INT_ADD_NEG", "INT_SUB_NEG", "INT_MULT_NEG", "INT_DIV_NEG"],
}

# Review suggestions (docs/special_algo.md, section 4). The spec's example is subtraction drawing on
# opposites and addition; the rest follow the lesson order. Drafts for the team to confirm.
PREREQUISITES = [
    ("INT_OPPOSITE_POS4", "INT_NUMBER_LINE"),
    ("INT_ABS_COMPARE", "INT_NUMBER_LINE"),
    ("INT_ORDER_NEG", "INT_NUMBER_LINE"),
    ("INT_ADD_NEG", "INT_NUMBER_LINE"),
    ("INT_SUB_NEG", "INT_OPPOSITE_POS4"),
    ("INT_SUB_NEG", "INT_ADD_NEG"),
    ("INT_MULT_NEG", "INT_ADD_NEG"),
    ("INT_DIV_NEG", "INT_MULT_NEG"),
    ("INT_EXPR_NEG", "INT_ADD_NEG"),
    ("INT_EXPR_NEG", "INT_SUB_NEG"),
    ("INT_EXPR_NEG", "INT_MULT_NEG"),
    ("INT_EXPR_NEG", "INT_DIV_NEG"),
    ("INT_CONTEXT", "INT_ADD_NEG"),
    ("INT_CONTEXT", "INT_SUB_NEG"),
]


@transaction.atomic
def seed_curriculum():
    """Create or update every lesson, skill, scope and prerequisite. Returns the counts."""
    lessons = {}
    for order, (code, title, summary) in enumerate(LESSONS, start=1):
        lesson, _ = Lesson.objects.update_or_create(
            code=code,
            defaults={
                "title": title,
                "summary": summary,
                "sort_order": order,
                "template_name": f"lessons/{code}.html",
                # Draft pages written 18 Nov from 3.0's lessons; the math teacher checks them.
                "content_status": Lesson.ContentStatus.DELIVERED,
            },
        )
        lessons[code] = lesson

    skills = {}
    for order, (code, short_name, name, lesson_code) in enumerate(SKILLS, start=1):
        skill, _ = Skill.objects.update_or_create(
            code=code,
            defaults={"short_name": short_name, "name": name, "sort_order": order, "lesson": lessons[lesson_code]},
        )
        skills[code] = skill

    wanted = set()
    for code, *_rest, lesson_code in SKILLS:
        wanted.add((lesson_code, code, LessonSkill.Scope.TAUGHT))
    for lesson_code, codes in REVIEW_SCOPE.items():
        for code in codes:
            wanted.add((lesson_code, code, LessonSkill.Scope.REVIEW))
    for lesson_code, code, scope in wanted:
        LessonSkill.objects.update_or_create(
            lesson=lessons[lesson_code], skill=skills[code], defaults={"scope": scope}
        )
    for link in LessonSkill.objects.select_related("lesson", "skill"):
        if (link.lesson.code, link.skill.code, link.scope) not in wanted:
            link.delete()

    wanted_links = set(PREREQUISITES)
    for skill_code, prerequisite_code in wanted_links:
        SkillPrerequisite.objects.get_or_create(skill=skills[skill_code], prerequisite=skills[prerequisite_code])
    for link in SkillPrerequisite.objects.select_related("skill", "prerequisite"):
        if (link.skill.code, link.prerequisite.code) not in wanted_links:
            link.delete()

    return {
        "lessons": Lesson.objects.count(),
        "skills": Skill.objects.count(),
        "lesson_skills": LessonSkill.objects.count(),
        "prerequisites": SkillPrerequisite.objects.count(),
    }
