"""Forms for the teacher exercise editor (docs/pages.md #5, docs/user_features.md "Teacher")."""
from django import forms
from django.core.exceptions import ValidationError
from django.forms import formset_factory

from apps.curriculum.models import Lesson, Skill

from .authoring import MAX_VIDEO_START, check_figure, parse_youtube
from .models import Question

POSITIONS = [(1, "A"), (2, "B"), (3, "C"), (4, "D")]


class NewExerciseForm(forms.Form):
    lesson = forms.ModelChoiceField(queryset=Lesson.objects.order_by("sort_order"), empty_label="Choose a lesson")
    title = forms.CharField(max_length=160)
    target_count = forms.IntegerField(min_value=1, max_value=30, initial=4, label="Questions per session")


class RevisionForm(forms.Form):
    title = forms.CharField(max_length=160)
    target_count = forms.IntegerField(min_value=1, max_value=30, label="Questions per session")
    required_skills = forms.ModelMultipleChoiceField(
        queryset=Skill.objects.none(), widget=forms.CheckboxSelectMultiple, required=False,
        help_text="Every session asks at least one question on each of these.",
    )

    def __init__(self, *args, skills=None, **kwargs):
        super().__init__(*args, **kwargs)
        if skills is not None:
            self.fields["required_skills"].queryset = skills


class QuestionForm(forms.Form):
    source_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
    keep_figure = forms.BooleanField(required=False, widget=forms.HiddenInput)
    format = forms.ChoiceField(choices=Question.Format.choices, initial=Question.Format.TEXT, widget=forms.RadioSelect)
    prompt = forms.CharField(max_length=1000, widget=forms.Textarea(attrs={"rows": 2}), label="Question")
    choice_1 = forms.CharField(max_length=255, required=False, label="A")
    choice_2 = forms.CharField(max_length=255, required=False, label="B")
    choice_3 = forms.CharField(max_length=255, required=False, label="C")
    choice_4 = forms.CharField(max_length=255, required=False, label="D")
    correct = forms.TypedChoiceField(choices=POSITIONS, coerce=int, required=False, empty_value=None,
                                     widget=forms.RadioSelect, label="Correct answer")
    skill = forms.ModelChoiceField(queryset=Skill.objects.none(), empty_label=None)
    difficulty = forms.ChoiceField(choices=Question.Difficulty.choices, initial=Question.Difficulty.MEDIUM)
    hint = forms.CharField(max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 2}),
                           help_text="Shown only after a wrong first answer, before the one retry.")
    figure = forms.FileField(required=False, label="Picture (PNG or JPEG, up to 2 MB)",
                             widget=forms.ClearableFileInput(attrs={"accept": "image/png,image/jpeg"}))
    figure_description = forms.CharField(max_length=300, required=False, label="Short description of the picture",
                                         help_text="Read aloud by screen readers. Say what the picture shows.")
    video_url = forms.CharField(max_length=300, required=False, label="YouTube link")
    video_start = forms.IntegerField(min_value=0, max_value=MAX_VIDEO_START, required=False,
                                     label="Start at (seconds)", help_text="Filled from the link's time if it has one.")

    def __init__(self, *args, skills=None, **kwargs):
        super().__init__(*args, **kwargs)
        if skills is not None:
            self.fields["skill"].queryset = skills
            first = skills.first()
            if first and "skill" not in self.initial:
                self.fields["skill"].initial = first.pk  # keeps an untouched blank card "unchanged"

    def choice_fields(self):
        return [(self[f"choice_{n}"], n) for n in range(1, 5)]

    def clean(self):
        data = super().clean()
        kind = data.get("format")
        if kind == Question.Format.FIGURE and data.get("figure"):
            try:
                check_figure(data["figure"])
            except ValidationError as error:
                self.add_error("figure", error)
        data["video_id"] = ""
        if kind == Question.Format.VIDEO and data.get("video_url"):
            try:
                video_id, start = parse_youtube(data["video_url"])
            except ValidationError as error:
                self.add_error("video_url", error)
            else:
                data["video_id"] = video_id
                if data.get("video_start") is None:
                    data["video_start"] = start
        return data

    def to_entry(self):
        data = self.cleaned_data
        return {
            "source_id": data.get("source_id"),
            "format": data["format"],
            "prompt": data["prompt"],
            "choices": [data.get(f"choice_{n}") or "" for n in range(1, 5)],
            "correct": data.get("correct"),
            "skill": data["skill"],
            "difficulty": data["difficulty"],
            "hint": data.get("hint") or "",
            "figure_upload": data.get("figure") or None,
            "keep_figure": bool(data.get("keep_figure")),
            "figure_description": data.get("figure_description") or "",
            "video_id": data.get("video_id") or "",
            "video_start": data.get("video_start"),
        }


QuestionFormSet = formset_factory(QuestionForm, extra=1, can_order=True, can_delete=True, max_num=60,
                                  validate_max=True)


def initial_for(question):
    """A saved question as editor values."""
    choices = {c.position: c for c in question.choices.all()}
    correct = next((p for p, c in choices.items() if c.is_correct), None)
    url = f"https://youtu.be/{question.video_id}" if question.video_id else ""
    return {
        "source_id": question.id,
        "keep_figure": bool(question.figure_file or question.figure_path),
        "format": question.format,
        "prompt": question.prompt,
        **{f"choice_{n}": choices[n].text if n in choices else "" for n in range(1, 5)},
        "correct": correct,
        "skill": question.skill_id,
        "difficulty": question.difficulty,
        "hint": question.hint,
        "figure_description": question.figure_description,
        "video_url": url,
        "video_start": question.video_start_seconds,
        "ORDER": question.author_order,
        # Not form fields: shown next to the card.
        "figure_name": question.figure_file.name if question.figure_file else "",
        "figure_static": question.figure_path,
        "item_key": question.item_key,
        "junyi_template": question.junyi_template,
    }
