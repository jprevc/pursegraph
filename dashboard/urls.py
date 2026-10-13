from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("import/", views.import_statements, name="import"),
    path("review/", views.review_queue, name="review_queue"),
]
