"""/radar/demo — la maqueta del zip servida LITERAL, con datos de ejemplo.

Sirve solo para comparar contra /radar (mismo CSS, mismo markup, datos reales).
El HTML es idéntico al del zip salvo la ruta del stylesheet.
"""
import frappe

from marketinghub.www.radar.index import VIEW_ROLES, _has_role

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/demo"
		raise frappe.Redirect

	if not _has_role(VIEW_ROLES):
		raise frappe.PermissionError

	context.no_cache = 1
