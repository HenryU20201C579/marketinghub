"""Vista Calendario tipo Google Calendar de publicaciones de competencia."""
import frappe
import hashlib
from datetime import date, datetime, timedelta

no_cache = 1

VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)

# Paleta de 12 colores distinguibles para asignar por competidor
PALETA = [
	"#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
	"#ec4899", "#06b6d4", "#f97316", "#84cc16", "#a855f7",
	"#14b8a6", "#f43f5e",
]


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/comparativa"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Calendario · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)


def _color_for(nombre):
	"""Asigna un color estable de la paleta usando hash del nombre."""
	if not nombre:
		return "#94a3b8"
	h = hashlib.md5(nombre.encode()).digest()[0]
	return PALETA[h % len(PALETA)]


@frappe.whitelist()
def obtener_competidores():
	"""Lista de competidores con color asignado (para leyenda + filtros)."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	comps = frappe.db.get_all(
		"Competidor",
		fields=["name"],
		order_by="nombre_comercial asc",
	)
	return [{"nombre": c["name"], "color": _color_for(c["name"])} for c in comps]


@frappe.whitelist()
def obtener_eventos(desde=None, hasta=None, plataforma=None,
                    competidor=None, tier_orden_max=None):
	"""Devuelve publicaciones en el rango [desde, hasta] (fechas YYYY-MM-DD).

	tier_orden_max: filtra tier <= N (menor orden = mejor tier). Ej. tier_orden_max=5
	solo devuelve los 5 mejores tiers.
	"""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	if not desde or not hasta:
		frappe.throw("desde y hasta son obligatorios (YYYY-MM-DD)")

	filters = {
		"fecha_publicacion": ["between", [desde, hasta]],
	}
	if plataforma:
		filters["plataforma"] = plataforma
	if competidor:
		filters["competidor"] = competidor
	if tier_orden_max:
		filters["tier_orden"] = ["<=", int(tier_orden_max)]

	posts = frappe.db.get_all(
		"Publicacion Competencia",
		filters=filters,
		fields=[
			"name", "competidor", "plataforma", "url_publicacion",
			"fecha_publicacion", "titulo_hook", "vistas_actual",
			"likes_actual", "engagement_pct", "es_viral", "tier",
			"tier_orden", "estado",
		],
		order_by="fecha_publicacion asc",
		limit=2000,
	)
	# adjuntar color por competidor
	for p in posts:
		p["color"] = _color_for(p["competidor"] or "")
		# fecha_publicacion viene como date object — a string YYYY-MM-DD
		if p.get("fecha_publicacion") and hasattr(p["fecha_publicacion"], "isoformat"):
			p["fecha_publicacion"] = p["fecha_publicacion"].isoformat()
	return posts


@frappe.whitelist()
def obtener_conteos_por_dia(anio=None, plataforma=None, competidor=None):
	"""Para vista Año: cuenta posts por día en todo el año (para el heatmap)."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	anio = int(anio or date.today().year)

	filtros = "WHERE YEAR(fecha_publicacion) = %(anio)s"
	params = {"anio": anio}
	if plataforma:
		filtros += " AND plataforma = %(plataforma)s"
		params["plataforma"] = plataforma
	if competidor:
		filtros += " AND competidor = %(competidor)s"
		params["competidor"] = competidor

	rows = frappe.db.sql(f"""
		SELECT DATE(fecha_publicacion) AS f, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		{filtros}
		GROUP BY DATE(fecha_publicacion)
	""", params, as_dict=True)

	return {str(r.f): int(r.c) for r in rows}


@frappe.whitelist()
def obtener_tiers():
	"""Lista de tiers para el filtro."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	s = frappe.get_cached_doc("Radar Settings")
	tiers = []
	for t in sorted(s.tiers_viralidad or [], key=lambda x: x.orden):
		tiers.append({
			"orden": t.orden, "nombre": t.nombre,
			"es_viral": bool(t.es_viral),
		})
	return tiers
