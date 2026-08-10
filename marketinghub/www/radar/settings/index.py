"""Página de configuración del Radar."""
import frappe

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/settings"
		raise frappe.Redirect

	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Configuración · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)


@frappe.whitelist()
def obtener_settings():
	"""Retorna los valores actuales de Radar Settings."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	s = frappe.get_cached_doc("Radar Settings")
	return {
		"umbral_viralidad": s.umbral_viralidad or 2.0,
		"piso_minimo_vistas": s.piso_minimo_vistas or 10000,
		"umbral_velocidad": s.umbral_velocidad or 3.0,
		"n_pubs_baseline": s.n_pubs_baseline or 30,
		"dias_retencion_snapshots": s.dias_retencion_snapshots or 90,
		"canal_alerta": s.canal_alerta or "In-app ERP",
	}


@frappe.whitelist()
def guardar_settings(
	umbral_viralidad=None,
	piso_minimo_vistas=None,
	umbral_velocidad=None,
	n_pubs_baseline=None,
	dias_retencion_snapshots=None,
	canal_alerta=None,
):
	"""Guarda los valores de Radar Settings."""
	if not _has_role(ADMIN_ROLES):
		frappe.throw(
			"Solo un administrador puede modificar la configuración.",
			frappe.PermissionError,
		)
	s = frappe.get_single("Radar Settings")
	if umbral_viralidad is not None:
		s.umbral_viralidad = float(umbral_viralidad)
	if piso_minimo_vistas is not None:
		s.piso_minimo_vistas = int(piso_minimo_vistas)
	if umbral_velocidad is not None:
		s.umbral_velocidad = float(umbral_velocidad)
	if n_pubs_baseline is not None:
		s.n_pubs_baseline = int(n_pubs_baseline)
	if dias_retencion_snapshots is not None:
		s.dias_retencion_snapshots = int(dias_retencion_snapshots)
	if canal_alerta is not None:
		s.canal_alerta = canal_alerta
	s.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
