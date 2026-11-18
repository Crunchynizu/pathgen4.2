from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm

from .models import User


class SignInForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "That username and password don't match. Check them and try again.",
        "inactive": "This account is turned off. Ask your teacher or the admin.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none"})
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})


class DisplayNameForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["display_name"]
        labels = {"display_name": "Display name"}
        help_texts = {"display_name": "The name others see. Your username stays the same."}

    def clean_display_name(self):
        name = self.cleaned_data["display_name"].strip()
        if not name:
            raise forms.ValidationError("Enter a name.")
        return name


class ProfilePasswordForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Current password"
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "New password again"
