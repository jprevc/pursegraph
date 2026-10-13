from django.urls import path

from . import views

urlpatterns = [
    path("import/", views.import_statements, name="import"),
    path("transactions/", views.transactions, name="transactions"),
]
