import frappe
from marketinghub.api.meta_ads import (
    VIEW_ROLES,
    _can_view,
    _is_admin,
)


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/meta_ads"
        raise frappe.Redirect

    context.no_cache = 1
    context.title = "Marketing Intelligence | VentaHub"
    context.no_access = not _can_view()
    context.required_roles = list(VIEW_ROLES)
    context.can_edit = _is_admin()

    # Config Chatwoot para el link "Ir a Chatwoot" en las filas.
    cfg = frappe.get_site_config()
    context.chatwoot_base_url = (cfg.get("chatwoot_url") or "").rstrip("/")
    context.chatwoot_account_id = int(cfg.get("chatwoot_account_id") or 0)
