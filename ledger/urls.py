from django.urls import path

from . import views

urlpatterns = [
    path("import/", views.import_statements, name="import"),
    path("statements/<int:pk>/delete/", views.delete_statement, name="delete_statement"),
    path("transactions/", views.transactions, name="transactions"),
    path("review/", views.review_queue, name="review_queue"),
    path("transactions/<int:pk>/outcome/", views.transaction_outcome, name="transaction_outcome"),
    path(
        "transactions/<int:pk>/counterpart/",
        views.transaction_counterpart,
        name="transaction_counterpart",
    ),
    path("categories/", views.categories, name="categories"),
    path("categories/add/", views.add_category, name="add_category"),
    path("categories/<int:pk>/rename/", views.rename_category, name="rename_category"),
    path("categories/<int:pk>/move/", views.move_category, name="move_category"),
    path("categories/<int:pk>/delete/", views.delete_category, name="delete_category"),
    path("categories/<int:pk>/subcategories/add/", views.add_subcategory, name="add_subcategory"),
    path("subcategories/<int:pk>/rename/", views.rename_subcategory, name="rename_subcategory"),
    path("subcategories/<int:pk>/move/", views.move_subcategory, name="move_subcategory"),
    path("subcategories/<int:pk>/delete/", views.delete_subcategory, name="delete_subcategory"),
    path("rules/", views.rules, name="rules"),
    path("rules/new/", views.new_rule, name="new_rule"),
    path("rules/reorder/", views.reorder_rules, name="reorder_rules"),
    path("rules/<int:pk>/edit/", views.edit_rule, name="edit_rule"),
    path("rules/<int:pk>/apply/", views.apply_rule, name="apply_rule"),
    path("rules/<int:pk>/move/", views.move_rule, name="move_rule"),
    path("rules/<int:pk>/delete/", views.delete_rule, name="delete_rule"),
]
