"""Radar de Competencia — herramienta tipo Excel para inteligencia competitiva.

Todo el estado vive en localStorage del navegador. Backend solo entrega la
pagina y controla acceso.
"""

import frappe
from frappe import _


VIEW_ROLES = (
	"Ventahub-Marketing-Ver",
	"Ventahub-Marketing-Administrar",
	"System Manager",
)


def _can_view():
	roles = frappe.get_roles()
	return any(r in roles for r in VIEW_ROLES)


def get_context(context):
	if frappe.session.user == "Guest":
		context.no_access = True
		context.has_access = False
		context.required_roles = ["Iniciar sesion"]
		return

	if not _can_view():
		context.no_access = True
		context.has_access = False
		context.required_roles = list(VIEW_ROLES)
		return

	context.has_access = True
