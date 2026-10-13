from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("review/", views.review_queue, name="review_queue"),
]
