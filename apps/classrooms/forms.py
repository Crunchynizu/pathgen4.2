from django import forms
from django.contrib.auth import get_user_model

from .models import Classroom

User = get_user_model()


class _AccountFields(forms.Form):
    display_name = forms.CharField(label="Name", max_length=150)
    username = forms.CharField(
        label="Username",
        max_length=150,
        help_text="Used to sign in. Letters, numbers and @ . + - _ only.",
        widget=forms.TextInput(attrs={"autocapitalize": "none", "autocomplete": "off"}),
    )
    password = forms.CharField(
        label="Starting password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 8 characters, not only numbers. They can change it on their profile.",
    )


class TeacherCreateForm(_AccountFields):
    prefix = "teacher"


class StudentCreateForm(_AccountFields):
    prefix = "student"
    classroom = forms.ModelChoiceField(
        label="Class", queryset=Classroom.objects.select_related("teacher"), empty_label="Choose a class"
    )


class ClassroomCreateForm(forms.Form):
    prefix = "class"
    name = forms.CharField(label="Class name", max_length=120)
    teacher = forms.ModelChoiceField(
        label="Teacher",
        queryset=User.objects.filter(role=User.Role.TEACHER).order_by("display_name", "username"),
        empty_label="Choose a teacher",
    )
