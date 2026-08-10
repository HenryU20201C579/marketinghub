"""Dashboard del Radar de Competencia."""
import frappe

no_cache = 1

VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)
ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar"
		raise frappe.Redirect

	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Radar de Competencia"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)
	context.usuario = frappe.session.user


@frappe.whitelist()
def obtener_contadores():
	"""Retorna contadores para el dashboard."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)

	return {
		"categorias": frappe.db.count("Categoria Competencia"),
		"competidores": frappe.db.count("Competidor", filters={"activo": 1}),
		"cuentas": frappe.db.count("Cuenta Social", filters={"activo": 1}),
		"publicaciones": frappe.db.count("Publicacion Competencia"),
		"virales": frappe.db.count("Publicacion Competencia", filters={"es_viral": 1}),
		"nuevos": frappe.db.count("Publicacion Competencia", filters={"estado": "Nuevo"}),
	}
