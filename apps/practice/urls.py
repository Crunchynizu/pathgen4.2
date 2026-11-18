from django.urls import path

from . import editor, views

app_name = "practice"

urlpatterns = [
    path("learn/exercises/<int:exercise_id>/", views.exercise, name="exercise"),
    path("learn/exercises/<int:exercise_id>/start/", views.start, name="start"),
    path("learn/exercises/<int:exercise_id>/answer/", views.answer, name="answer"),
    path("learn/exercises/<int:exercise_id>/hint/", views.hint, name="hint"),
    path("learn/exercises/<int:exercise_id>/move-on/", views.move_on, name="move_on"),
    path("learn/exercises/<int:exercise_id>/feedback/", views.generate_feedback, name="feedback"),
    path("teacher/exercises/<int:exercise_id>/", views.teacher_exercise, name="teacher_exercise"),
    # The editor (docs/pages.md #5) and its dialogs (docs/modals.md #4-#6).
    path("teacher/exercises/new/", editor.new, name="editor_new"),
    path("teacher/exercises/<int:exercise_id>/edit/", editor.edit, name="editor"),
    path("teacher/exercises/<int:exercise_id>/draft/", editor.start_draft, name="start_draft"),
    path("teacher/exercises/<int:exercise_id>/publish/", editor.publish, name="publish"),
    path("teacher/exercises/<int:exercise_id>/unpublish/", editor.unpublish, name="unpublish"),
    path("teacher/exercises/<int:exercise_id>/delete/", editor.delete, name="delete"),
    path("media/<path:name>", editor.figure, name="figure"),
]
