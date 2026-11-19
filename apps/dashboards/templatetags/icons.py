"""AnimateIcons Lucide icons (docs/tech_stack.md). Decorative only: hidden from screen readers, and
the page reads the same without them (the script is checked in under static/vendor/)."""
from django import template
from django.utils.html import format_html

register = template.Library()

SECTION_ICONS = {
    "overview": "layout-dashboard",
    "accounts": "users",
    "classes": "school",
    "lessons": "book-open",
    "assessments": "clipboard-check",
    "exercises": "list-checks",
    "profile": "user",
}


@register.simple_tag
def icon(name, size=20):
    return format_html('<animate-icons class="icon" name="{}" size="{}" aria-hidden="true"></animate-icons>',
                       name, size)


@register.simple_tag
def section_icon(key, size=20):
    return icon(SECTION_ICONS.get(key, "sparkles"), size)


# Each lesson has its own color (CSS .tone-1 ... .tone-6, by sort order) and a math sign as its
# mark, so a lesson looks the same on the journey, its page and its practice.
LESSON_GLYPHS = {
    "integer_foundation": "±",
    "integer_addition": "+",
    "integer_subtraction": "−",
    "integer_multiplication": "×",
    "integer_division": "÷",
    "integer_expressions_applications": "( )",
}


@register.filter
def lesson_glyph(lesson):
    return LESSON_GLYPHS.get(getattr(lesson, "code", ""), "•")


@register.filter
def initials(user):
    """Up to two letters for the round avatar: "Demo Student 2" -> "DS"."""
    words = [word for word in str(user).split() if word[:1].isalpha()]
    return ("".join(word[0] for word in words[:2]) or str(user)[:1]).upper()
