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
