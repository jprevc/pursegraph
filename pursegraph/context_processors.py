from dashboard.views import VIEWS

# The navigation item each page belongs to, by URL name. Every dashboard view belongs to Dashboard.
ITEMS = {
    "dashboard": "dashboard",
    **{name: "dashboard" for name in VIEWS},
    "transactions": "transactions",
    "review_queue": "review_queue",
    "import": "import",
    "delete_statement": "import",
    "rules": "rules",
    "new_rule": "rules",
    "edit_rule": "rules",
    "apply_rule": "rules",
    "categories": "categories",
    "suggestion_settings": "suggestion_settings",
    "api_and_webhooks": "api_and_webhooks",
    "revoke_token": "api_and_webhooks",
    "delete_webhook": "api_and_webhooks",
    "accounts": "accounts",
    "new_account": "accounts",
    "edit_account": "accounts",
    "delete_account": "accounts",
    "members": "members",
    "new_member": "members",
}
# The items under Manage, which opens on their pages.
MANAGE = {"rules", "categories", "suggestion_settings", "api_and_webhooks", "accounts", "members"}


def navigation(request):
    """The current navigation item, `nav`, and whether the Manage group is open."""
    match = request.resolver_match
    nav = ITEMS.get(match.url_name) if match else None
    return {"nav": nav, "manage_open": nav in MANAGE}
