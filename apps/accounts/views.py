from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.dashboards.navigation import sections_for

from .forms import DisplayNameForm, ProfilePasswordForm, SignInForm
from .permissions import landing_url


class SignInView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = SignInForm
    redirect_authenticated_user = True

    def get_success_url(self):
        target = self.get_redirect_url()
        if target and url_has_allowed_host_and_scheme(target, allowed_hosts={self.request.get_host()}):
            return target
        return landing_url(self.request.user)


class SignOutView(LogoutView):
    """POST only (Django's LogoutView refuses GET), so a link can't sign anyone out."""

    next_page = "accounts:login"


@login_required
def profile(request):
    user = request.user
    name_form = DisplayNameForm(instance=user)
    password_form = ProfilePasswordForm(user)

    if request.method == "POST":
        if request.POST.get("form") == "name":
            name_form = DisplayNameForm(request.POST, instance=user)
            if name_form.is_valid():
                name_form.save()
                messages.success(request, "Your display name is saved.")
                return redirect("accounts:profile")
        elif request.POST.get("form") == "password":
            password_form = ProfilePasswordForm(user, request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, "Your password is changed.")
                return redirect("accounts:profile")

    return render(
        request,
        "accounts/profile.html",
        {
            "name_form": name_form,
            "password_form": password_form,
            "back_url": landing_url(user),
            "nav": "profile",
            "section": "profile",
            "sections": sections_for(user),
        },
    )
