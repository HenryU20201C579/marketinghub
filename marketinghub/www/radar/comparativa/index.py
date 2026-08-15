"""Calendario de publicaciones de competencia (/radar/comparativa).

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`) y `calendario.css` es copia literal del CSS del
diseño. `get_context` entrega los eventos y los contadores; la rejilla, el mini
calendario y el panel del día los pinta el JS del propio diseño.
"""
import hashlib
import re
from datetime import date, datetime

from frappe.utils import get_datetime

import frappe

no_cache = 1

VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)

MESES = [
	"Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
	"Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
# El diseño abrevia la red en dos letras y distingue dos competidores (a / e)
REDES = {"Instagram": "IG", "TikTok": "TT", "Facebook": "FB", "YouTube": "YT"}

# Paleta oficial de Google Calendar (12 colores), usada por los endpoints
PALETA = [
	"#d50000", "#e67c73", "#f4511e", "#f6bf26", "#33b679", "#0b8043",
	"#039be5", "#3f51b5", "#7986cb", "#8e24aa", "#616161", "#a79b8e",
]

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

RE_EMOJI = re.compile(
	"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
	"⬀-⯿←-⇿️‍]+"
)


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def _limpiar(texto):
	return re.sub(r"\s{2,}", " ", RE_EMOJI.sub(" ", texto or "")).strip(" ·-—")


def _color_for(nombre):
	"""Asigna un color estable de la paleta usando hash del nombre."""
	if not nombre:
		return "#94a3b8"
	return PALETA[hashlib.md5(nombre.encode()).digest()[0] % len(PALETA)]


def _colores_por_competidor():
	"""{competidor: {color, personalizado}} sin dos marcas del mismo color.

	El color propio manda. Para el resto se usa el hash del nombre (estable: no
	cambia al dar de alta otras marcas) y, si ese color ya está cogido, se avanza
	por la paleta en orden alfabético para que el reparto sea determinista."""
	comps = frappe.db.get_all(
		"Competidor", fields=["name", "color"], order_by="name asc"
	)
	usados = {c["color"] for c in comps if c["color"]}
	colores = {}
	for c in comps:
		if c["color"]:
			colores[c["name"]] = {"color": c["color"], "personalizado": True}
			continue
		elegido = _color_for(c["name"])
		if elegido in usados:
			libres = [p for p in PALETA if p not in usados]
			elegido = libres[0] if libres else elegido
		usados.add(elegido)
		colores[c["name"]] = {"color": elegido, "personalizado": False}
	return colores


def _tenue(hex_color, alpha=0.13):
	"""#0b8043 -> 'rgba(11,128,67,0.13)' para el fondo de los chips."""
	h = (hex_color or "").lstrip("#")
	if len(h) == 3:
		h = "".join(c * 2 for c in h)
	if len(h) != 6:
		return "transparent"
	try:
		r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
	except ValueError:
		return "transparent"
	return f"rgba({r},{g},{b},{alpha})"


# ============ ARMADO DE LA VISTA ============

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
	if context.no_access:
		return

	# cada marca lleva su propio color (el guardado o el que le toca de la paleta)
	colores = _colores_por_competidor()
	comps = sorted(colores)

	eventos = []
	for p in frappe.db.get_all(
		"Publicacion Competencia",
		fields=[
			"name", "competidor", "plataforma", "url_publicacion", "fecha_publicacion",
			"titulo_hook", "vistas_actual", "tier", "tier_orden",
		],
		order_by="fecha_publicacion desc, vistas_actual desc",
		limit=2000,
	):
		f = p.fecha_publicacion
		iso = f.isoformat() if hasattr(f, "isoformat") else str(f or "")
		if len(iso) != 10:
			continue
		eventos.append({
			"id": p.name,
			"iso": iso,
			"anio": int(iso[:4]),
			"mes": int(iso[5:7]) - 1,   # el JS del diseño usa meses 0-11
			"dia": int(iso[8:10]),
			"plat": REDES.get(p.plataforma, (p.plataforma or "--")[:2].upper()),
			"comp": p.competidor or "",
			"titulo": _limpiar(p.titulo_hook) or p.name,
			"vistas": int(p.vistas_actual or 0),
			"tier": p.tier or "Sin tier",
			"url": (p.url_publicacion or "") if (p.url_publicacion or "").startswith(("http://", "https://")) else "",
		})

	hoy = date.today()
	context.eventos_json = frappe.as_json(eventos).replace("</", "<\\/")
	context.hoy_json = frappe.as_json({"dia": hoy.day, "mes": hoy.month - 1, "anio": hoy.year})
	context.competidores = [
		{
			"nombre": c,
			"color": colores[c]["color"],
			"tenue": _tenue(colores[c]["color"]),
			"personalizado": colores[c]["personalizado"],
		}
		for c in comps
	]
	# el JS pinta cada publicación con el color de su marca
	context.colores_json = frappe.as_json({
		c: {"color": colores[c]["color"], "tenue": _tenue(colores[c]["color"])}
		for c in comps
	}).replace("</", "<\\/")
	context.paleta = PALETA_LABELS
	context.puede_color = _has_role((
		"Marketinghub-Radar-Administrar", "Marketinghub-Radar-Analista", "System Manager",
	))
	context.tiers = _tiers()
	context.redes = [
		{"sigla": s, "nombre": n} for n, s in REDES.items()
		if any(e["plat"] == s for e in eventos)
	]
	context.mes_inicial = f"{MESES[hoy.month - 1]} {hoy.year}"
	try:
		from marketinghub.www.radar.index import obtener_contadores
		context.contadores = obtener_contadores()
	except Exception:
		context.contadores = {}
	context.ultima_corrida = _ultima_corrida()
	try:
		context.csrf_token = frappe.local.session.data.csrf_token
	except Exception:
		context.csrf_token = ""


def _tiers():
	try:
		s = frappe.get_cached_doc("Radar Settings")
		return [t.nombre for t in sorted(s.tiers_viralidad or [], key=lambda x: x.orden)]
	except Exception:
		return []


def _ultima_corrida():
	try:
		s = frappe.get_cached_doc("Radar Settings")
		if not s.ultima_corrida:
			return "—"
		cuando = get_datetime(s.ultima_corrida)
		minutos = int((datetime.now() - cuando).total_seconds() // 60)
		if minutos < 60:
			return f"hace {max(minutos, 1)} min"
		if minutos < 60 * 24:
			return f"hace {minutos // 60} h"
		return f"hace {minutos // (60 * 24)} d"
	except Exception:
		return "—"


# ============ ENDPOINTS ============

@frappe.whitelist()
def obtener_competidores():
	"""Lista de competidores con color asignado (para leyenda + filtros).
	Usa el campo `color` si está seteado; sino asigna uno estable por hash."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	colores = _colores_por_competidor()
	return [
		{"nombre": c, "color": datos["color"], "personalizado": datos["personalizado"]}
		for c, datos in sorted(colores.items())
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
	# al resetear, el color vuelve a salir del reparto automático (sin colisiones)
	asignado = _colores_por_competidor().get(competidor, {})
	return {
		"ok": True,
		"color": asignado.get("color") or _color_for(competidor),
		"tenue": _tenue(asignado.get("color") or _color_for(competidor)),
		"personalizado": bool(color),
	}


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
