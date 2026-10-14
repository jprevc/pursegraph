from django.urls import path

from . import views

urlpatterns = [
    path("members/", views.member_list, name="members"),
    path("members/new/", views.new_member, name="new_member"),
    path("members/<int:pk>/reset-link/", views.reset_link, name="member_reset_link"),
    path("members/<int:pk>/active/", views.set_active, name="member_active"),
    path("members/<int:pk>/admin/", views.set_admin, name="member_admin"),
    path("set-password/<uidb64>/<token>/", views.SetPasswordView.as_view(), name="set_password"),
]
