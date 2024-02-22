from django.shortcuts import render
from allauth.account.views import (
    LoginView,
    SignupView,
    ConfirmEmailView,
    EmailVerificationSentView,
)
from django.urls import include, path
from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from django.contrib.auth import logout
from django.contrib import messages


class MyLoginView(LoginView):
    template_name = "accounts/login.html"

    def form_invalid(self, form):
        response = super().form_invalid(form)
        user = self.request.user

        if user.is_authenticated and not user.is_active:
            messages.error(self.request, "Account not active")

        return response


"""class MySignupView(SignupView):   
    template_name = 'accounts/signup.html'
    def form_valid(self, form):
        response = super().form_valid(form)
        logout(self.request)
        return response
"""


def verify_email(request):
    # Manually verify email
    # Mark email verified on user
    return EmailVerificationSentView.as_view()(request)


@receiver(user_signed_up)
def set_inactive(request, user, **kwargs):
    user.is_active = False
    user.save()
