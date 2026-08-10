"""Matriz de publicaciones por mes × competidor."""
import frappe
from datetime import date

no_cache = 1

VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)

METRICAS = {
	"posts":    ("COUNT(*)",                                "Cantidad de publicaciones"),
	"vistas":   ("SUM(COALESCE(vistas_actual, 0))",         "Suma de vistas"),
	"virales":  ("SUM(CASE WHEN es_viral = 1 THEN 1 ELSE 0 END)", "Cantidad de virales"),
	"eng_avg":  ("ROUND(AVG(COALESCE(engagement_pct, 0)), 2)", "Engagement % promedio"),
}


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/comparativa"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Comparativa · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.anio_actual = date.today().year


@frappe.whitelist()
def obtener_matriz(anio=None, plataforma=None, metrica=None):
	"""Devuelve dict {competidor: {1..12: valor}, ...} + años disponibles."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)

	anio = int(anio or date.today().year)
	metrica = metrica if metrica in METRICAS else "posts"
	sql_expr, _ = METRICAS[metrica]

	# años disponibles
	anios = [r[0] for r in frappe.db.sql("""
		SELECT DISTINCT YEAR(fecha_publicacion)
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion IS NOT NULL
		ORDER BY 1 DESC
	""") if r[0]]
	if not anios:
		anios = [date.today().year]

	# plataformas disponibles
	plataformas = [r[0] for r in frappe.db.sql("""
		SELECT DISTINCT plataforma FROM `tabPublicacion Competencia`
		WHERE plataforma IS NOT NULL AND plataforma != ''
		ORDER BY plataforma
	""") if r[0]]

	filtros_sql = "WHERE YEAR(fecha_publicacion) = %(anio)s"
	params = {"anio": anio}
	if plataforma:
		filtros_sql += " AND plataforma = %(plataforma)s"
		params["plataforma"] = plataforma

	rows = frappe.db.sql(f"""
		SELECT
			competidor,
			MONTH(fecha_publicacion) AS mes,
			{sql_expr} AS valor
		FROM `tabPublicacion Competencia`
		{filtros_sql}
		GROUP BY competidor, MONTH(fecha_publicacion)
		ORDER BY competidor, mes
	""", params, as_dict=True)

	# Estructura {competidor: {mes: valor}}
	matriz = {}
	for r in rows:
		if not r.competidor:
			continue
		matriz.setdefault(r.competidor, {})[r.mes] = float(r.valor or 0)

	# Ordenar por total desc
	competidores_sorted = sorted(
		matriz.keys(),
		key=lambda c: sum(matriz[c].values()),
		reverse=True,
	)

	return {
		"anio": anio,
		"anios_disponibles": anios,
		"plataformas": plataformas,
		"metrica": metrica,
		"metricas_disponibles": [
			{"key": k, "label": v[1]} for k, v in METRICAS.items()
		],
		"competidores": competidores_sorted,
		"matriz": matriz,
	}
