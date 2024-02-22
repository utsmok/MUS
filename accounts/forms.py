from allauth.account.forms import SignupForm
from django import forms


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(max_length=30, label="First Name")

    def clean_email(self):
        email = self.cleaned_data["email"]
        if not email.endswith("@utwente.nl"):
            raise forms.ValidationError("Use your UT email")
        return email
