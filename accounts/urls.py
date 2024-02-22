from .views import MyLoginView, MySignupView, verify_email
from django.urls import include, path

urlpatterns = [
    path("login/", MyLoginView.as_view()),
    path("verify-email/", verify_email, name="account_verify_email"),
    """path('signup/', MySignupView.as_view()), 
      """,
]
