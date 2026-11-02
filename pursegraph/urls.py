from django.contrib.auth import views as auth_views
from django.urls import include, path

from members.login import LoginView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("dashboard.urls")),
    path("", include("ledger.urls")),
    path("", include("members.urls")),
]
