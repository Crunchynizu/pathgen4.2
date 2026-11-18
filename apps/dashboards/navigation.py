"""Sidebar sections (docs/pages.md, "Navigation"). Profile and Sign out are added by the sidebar."""
ADMIN_SECTIONS = [
    ("overview", "Overview"),
    ("accounts", "Accounts"),
    ("classes", "Classes"),
    ("lessons", "Lessons"),
    ("assessments", "Assessments"),
]
TEACHER_SECTIONS = [("overview", "Overview"), ("classes", "My Classes"), ("exercises", "Exercises")]


def sections_for(user):
    if user.is_app_admin:
        return ADMIN_SECTIONS
    if user.is_teacher:
        return TEACHER_SECTIONS
    return []
