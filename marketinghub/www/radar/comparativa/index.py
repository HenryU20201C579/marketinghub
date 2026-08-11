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

# Paleta oficial de Google Calendar (12 colores)
# https://developers.google.com/calendar/api/v3/reference/colors
PALETA = [
	"#d50000",  # Tomate
	"#e67c73",  # Flamingo
	"#f4511e",  # Mandarina
	"#f6bf26",  # Plátano
	"#33b679",  # Salvia
	"#0b8043",  # Bosque (basil)
	"#039be5",  # Pavo real (peacock)
	"#3f51b5",  # Arándano (blueberry)
	"#7986cb",  # Lavanda
	"#8e24aa",  # Uva (grape)
	"#616161",  # Grafito
	"#a79b8e",  # Abedul (birch)
]

# Exportado para el frontend
PALETA_LABELS = [
	{"color": "#d50000", "nombre": "Tomate"},
	{"color": "#e67c73", "nombre": "Flamingo"},
	{"color": "#f4511e", "nombre": "Mandarina"},
	{"color": "#f6bf26", "nombre": "Plátano"},
	{"color": "#33b679", "nombre": "Salvia"},
	{"color": "#0b8043", "nombre": "Bosque"},
	{"color": "#039be5", "nombre": "Pavo real"},
	{"color": "#3f51b5", "nombre": "Arándano"},
	{"color": "#7986cb", "nombre": "Lavanda"},
	{"color": "#8e24aa", "nombre": "Uva"},
	{"color": "#616161", "nombre": "Grafito"},
	{"color": "#a79b8e", "nombre": "Abedul"},
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
	"""Lista de competidores con color asignado (para leyenda + filtros).
	Usa el campo `color` si está seteado; sino asigna uno estable por hash."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	comps = frappe.db.get_all(
		"Competidor",
		fields=["name", "color"],
		order_by="nombre_comercial asc",
	)
	return [
		{
			"nombre": c["name"],
			"color": c["color"] or _color_for(c["name"]),
			"personalizado": bool(c["color"]),
		}
		for c in comps
	]


@frappe.whitelist()
def obtener_paleta():
	"""Devuelve la paleta oficial disponible para el color picker."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	return PALETA_LABELS


@frappe.whitelist()
def guardar_color_competidor(competidor=None, color=None):
	"""Guarda el color personalizado de un competidor."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & {"Marketinghub-Radar-Administrar",
	                 "Marketinghub-Radar-Analista",
	                 "System Manager"}):
		frappe.throw("Solo un admin o analista puede cambiar colores.",
		             frappe.PermissionError)
	if not competidor:
		frappe.throw("competidor es obligatorio")
	# color puede ser hex (#rrggbb) o vacío para resetear al hash
	if color and not (color.startswith("#") and len(color) in (4, 7)):
		frappe.throw(f"Color inválido: {color!r} (debe ser #rrggbb o vacío)")
	frappe.db.set_value("Competidor", competidor, "color", color or None)
	frappe.db.commit()
	nuevo = color or _color_for(competidor)
	return {"ok": True, "color": nuevo, "personalizado": bool(color)}


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
	# Precargar colores personalizados de todos los competidores en juego (una sola query)
	comps_en_juego = list({p["competidor"] for p in posts if p.get("competidor")})
	colores_custom = {}
	if comps_en_juego:
		for c in frappe.db.get_all(
			"Competidor",
			filters={"name": ["in", comps_en_juego]},
			fields=["name", "color"],
		):
			colores_custom[c.name] = c.color  # puede ser None
	# adjuntar color por competidor: personalizado si existe, sino hash estable
	for p in posts:
		comp = p.get("competidor") or ""
		p["color"] = colores_custom.get(comp) or _color_for(comp)
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
