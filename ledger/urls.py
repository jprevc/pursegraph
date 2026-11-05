from django.urls import path
from django.views.generic import RedirectView

from . import api, views

urlpatterns = [
    path("import/", views.import_statements, name="import"),
    path("accounts/", views.accounts, name="accounts"),
    path("accounts/new/", views.new_account, name="new_account"),
    path("accounts/<int:pk>/edit/", views.edit_account, name="edit_account"),
    path("accounts/<int:pk>/delete/", views.delete_account, name="delete_account"),
    path("statements/<int:pk>/delete/", views.delete_statement, name="delete_statement"),
    path("transactions/", views.transactions, name="transactions"),
    path("review/", views.review_queue, name="review_queue"),
    path("review/decide/", views.review_decide, name="review_decide"),
    path("review/undo/", views.review_undo, name="review_undo"),
    path("review/split/", views.review_split, name="review_split"),
    path("transactions/<int:pk>/outcome/", views.transaction_outcome, name="transaction_outcome"),
    path("transactions/<int:pk>/split/", views.transaction_split, name="transaction_split"),
    path("transactions/<int:pk>/undo/", views.undo_outcome, name="undo_outcome"),
    path("categories/", views.categories, name="categories"),
    path("categories/add/", views.add_category, name="add_category"),
    path("categories/<int:pk>/save/", views.save_category, name="save_category"),
    path("categories/<int:pk>/move/", views.move_category, name="move_category"),
    path("categories/<int:pk>/delete/", views.delete_category, name="delete_category"),
    path("categories/<int:pk>/subcategories/add/", views.add_subcategory, name="add_subcategory"),
    path("subcategories/<int:pk>/move/", views.move_subcategory, name="move_subcategory"),
    path("subcategories/<int:pk>/delete/", views.delete_subcategory, name="delete_subcategory"),
    path("suggestions/", views.suggestion_settings, name="suggestion_settings"),
    path(
        "suggestions/accept/", views.accept_clearing_suggestions, name="accept_clearing_suggestions"
    ),
    path("suggestions/resuggest/", views.resuggest_queue, name="resuggest_queue"),
    path("api-and-webhooks/", views.api_and_webhooks, name="api_and_webhooks"),
    # The page's address before it was API & Webhooks; its actions' old addresses don't redirect.
    path("categorizers/", RedirectView.as_view(pattern_name="api_and_webhooks", permanent=True)),
    path("api-and-webhooks/tokens/<int:pk>/revoke/", views.revoke_token, name="revoke_token"),
    path("api-and-webhooks/webhooks/", views.add_webhook, name="add_webhook"),
    path("api-and-webhooks/webhooks/<int:pk>/delete/", views.delete_webhook, name="delete_webhook"),
    path("api-and-webhooks/webhooks/<int:pk>/notify/", views.notify_webhook, name="notify_webhook"),
    path("api/categorizer/v1/transactions/", api.waiting, name="api_waiting"),
    path(
        "api/categorizer/v1/transactions/<int:pk>/suggestion/",
        api.suggestion,
        name="api_suggestion",
    ),
    path("rules/", views.rules, name="rules"),
    path("rules/new/", views.new_rule, name="new_rule"),
    path("rules/preview/", views.rule_preview, name="rule_preview"),
    path("rules/reorder/", views.reorder_rules, name="reorder_rules"),
    path("rules/<int:pk>/edit/", views.edit_rule, name="edit_rule"),
    path("rules/<int:pk>/move/", views.move_rule, name="move_rule"),
    path("rules/<int:pk>/delete/", views.delete_rule, name="delete_rule"),
]
