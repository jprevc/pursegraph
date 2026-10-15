from django.urls import path

from . import views

urlpatterns = [path("", views.dashboard, name="dashboard")]
for view in views.VIEWS.values():
    urlpatterns += [
        path(f"{view.path}/", views.show, {"view": view.name}, name=view.name),
        path(
            f"{view.path}/transactions/",
            views.transactions,
            {"view": view.name},
            name=f"{view.name}_transactions",
        ),
    ]
