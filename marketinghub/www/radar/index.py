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
def obtener_stats_graficos():
	"""Datos para los 3 gráficos del dashboard."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	from datetime import date, timedelta

	hoy = date.today()
	hace_6m = date(hoy.year, hoy.month, 1) - timedelta(days=180)

	# 1. Posts por mes últimos 6 meses (barras)
	posts_mes = frappe.db.sql("""
		SELECT DATE_FORMAT(fecha_publicacion, '%%Y-%%m') AS mes, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY mes ORDER BY mes
	""", (hace_6m,), as_dict=True)

	# 2. Engagement promedio por competidor (líneas horizontales / barras)
	eng_comp = frappe.db.sql("""
		SELECT competidor, ROUND(AVG(engagement_pct), 2) AS eng, COUNT(*) AS n
		FROM `tabPublicacion Competencia`
		WHERE engagement_pct IS NOT NULL AND competidor IS NOT NULL
		GROUP BY competidor ORDER BY eng DESC
	""", as_dict=True)

	# 3. Distribución por tier (circular)
	tiers = frappe.db.sql("""
		SELECT COALESCE(tier, 'Sin tier') AS tier, tier_orden, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		GROUP BY tier, tier_orden
		ORDER BY tier_orden ASC
	""", as_dict=True)

	return {
		"posts_por_mes": posts_mes,
		"engagement_competidor": eng_comp,
		"distribucion_tiers": tiers,
	}


@frappe.whitelist()
def obtener_contadores():
	"""Retorna contadores para el dashboard."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)

	from datetime import date, timedelta
	hoy = date.today()
	hace_24h = hoy - timedelta(days=1)

	return {
		"categorias": frappe.db.count("Categoria Competencia"),
		"competidores": frappe.db.count("Competidor", filters={"activo": 1}),
		"cuentas": frappe.db.count("Cuenta Social", filters={"activo": 1}),
		"publicaciones": frappe.db.count("Publicacion Competencia"),
		"virales": frappe.db.count("Publicacion Competencia", filters={"es_viral": 1}),
		"virales_hoy": frappe.db.count("Publicacion Competencia", filters={
			"es_viral": 1,
			"fecha_publicacion": [">=", hace_24h],
		}),
		"nuevos": frappe.db.count("Publicacion Competencia", filters={"estado": "Nuevo"}),
	}
