"""Calendario de publicaciones de competencia (/radar/comparativa).

El frontend es el diseño del zip servido tal cual: `index.html` es un documento
standalone (no extiende `templates/web.html`) y `calendario.css` es copia
literal del CSS del diseño. Lo único que cambia son los datos, que se resuelven
aquí y se inyectan con Jinja sobre el mismo markup y las mismas clases.
"""
import hashlib
import re
from datetime import date, timedelta
from urllib.parse import urlencode

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
MESES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
# La rejilla del diseño empieza en domingo
WEEKDAYS = ["Dom", "Lun", "Mar", "Mié", "Jue", "Vie", "Sáb"]
INICIALES = ["D", "L", "M", "X", "J", "V", "S"]
CHIPS_POR_CELDA = 3
REDES = {"TikTok": "TT", "Instagram": "IG", "YouTube": "YT", "Facebook": "FB", "Twitter": "X"}

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


# ============ ARMADO DE LA VISTA ============

def _dom_de_la_semana(d):
	"""Domingo de la semana de `d` (weekday(): lunes=0 … domingo=6)."""
	return d - timedelta(days=(d.weekday() + 1) % 7)


def _parse_fecha(valor, defecto):
	try:
		anio, mes, dia = (int(x) for x in str(valor).split("-"))
		return date(anio, mes, dia)
	except (ValueError, TypeError, AttributeError):
		return defecto


def _parse_mes(valor, defecto):
	try:
		anio, mes = (int(x) for x in str(valor).split("-"))
		return date(anio, mes, 1)
	except (ValueError, TypeError, AttributeError):
		return defecto.replace(day=1)


def _sumar_meses(d, n):
	mes = d.month - 1 + n
	return date(d.year + mes // 12, mes % 12 + 1, 1)


def _url(**cambios):
	"""URL de la página conservando los parámetros actuales salvo los indicados."""
	params = {
		k: v for k, v in frappe.form_dict.items()
		if k in ("mes", "dia", "vista", "plataforma", "tier", "competidor") and v
	}
	params.update({k: v for k, v in cambios.items() if v})
	for k, v in cambios.items():
		if not v:
			params.pop(k, None)
	return "/radar/comparativa" + ("?" + urlencode(params) if params else "")


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/comparativa"
		raise frappe.Redirect

	context.no_cache = 1
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	if context.no_access:
		return

	hoy = date.today()
	fd = frappe.form_dict
	vista = fd.get("vista") if fd.get("vista") in ("dia", "semana", "mes") else "mes"
	mes_ancla = _parse_mes(fd.get("mes"), hoy)
	dia_sel = _parse_fecha(fd.get("dia"), hoy if not fd.get("mes") else mes_ancla)
	if fd.get("dia"):
		mes_ancla = dia_sel.replace(day=1)
	plataforma = fd.get("plataforma") or ""
	tier = fd.get("tier") or ""
	competidor = fd.get("competidor") or ""

	# Rango visible: mes completo (6 semanas desde el domingo previo) o una semana
	if vista == "mes":
		inicio = _dom_de_la_semana(mes_ancla)
		celdas_n = 42
	else:
		inicio = _dom_de_la_semana(dia_sel)
		celdas_n = 7
	fin = inicio + timedelta(days=celdas_n - 1)

	posts = _posts(inicio, fin, plataforma, tier, competidor)
	por_dia = {}
	for p in posts:
		por_dia.setdefault(p["fecha"], []).append(p)

	# El mini calendario siempre muestra el mes del ancla
	mini_inicio = _dom_de_la_semana(mes_ancla)
	mini_posts = por_dia if vista == "mes" else _agrupar(
		_posts(mini_inicio, mini_inicio + timedelta(days=41), plataforma, tier, competidor)
	)

	context.vista = vista
	context.mes_label = _label_rango(vista, mes_ancla, inicio)
	context.total_label = f"{len(posts)} publicacion{'es' if len(posts) != 1 else ''}"
	context.celdas = _celdas(inicio, celdas_n, mes_ancla, hoy, dia_sel, por_dia)
	context.mini = _mini(mini_inicio, mes_ancla, hoy, dia_sel, mini_posts)
	context.mini_label = f"{MESES_CORTO[mes_ancla.month - 1]} {mes_ancla.year}"
	context.weekdays = WEEKDAYS
	context.iniciales = INICIALES
	context.plataformas = _plataformas()
	context.tiers = _tiers()
	context.competidores = _competidores(inicio, fin)
	context.f_plataforma = plataforma
	context.f_tier = tier
	context.dia_titulo = f"{dia_sel.day} de {MESES[dia_sel.month - 1]}"
	dia_posts = por_dia.get(dia_sel.isoformat(), [])
	context.dia_posts = dia_posts
	context.dia_sub = f"{len(dia_posts)} publicacion{'es' if len(dia_posts) != 1 else ''}"

	# Navegación
	salto = 1 if vista == "mes" else 0
	if vista == "mes":
		prev_ancla, next_ancla = _sumar_meses(mes_ancla, -salto), _sumar_meses(mes_ancla, salto)
		context.url_prev = _url(mes=prev_ancla.strftime("%Y-%m"), dia="")
		context.url_next = _url(mes=next_ancla.strftime("%Y-%m"), dia="")
	else:
		context.url_prev = _url(dia=(dia_sel - timedelta(days=7)).isoformat(), mes="")
		context.url_next = _url(dia=(dia_sel + timedelta(days=7)).isoformat(), mes="")
	context.url_hoy = _url(mes="", dia="")
	context.url_vista = {v: _url(vista="" if v == "mes" else v) for v in ("dia", "semana", "mes")}


def _agrupar(posts):
	out = {}
	for p in posts:
		out.setdefault(p["fecha"], []).append(p)
	return out


def _posts(desde, hasta, plataforma, tier, competidor):
	filtros = {"fecha_publicacion": ["between", [desde.isoformat(), hasta.isoformat()]]}
	if plataforma:
		filtros["plataforma"] = plataforma
	if tier:
		filtros["tier"] = tier
	if competidor:
		filtros["competidor"] = competidor

	rows = frappe.db.get_all(
		"Publicacion Competencia",
		filters=filtros,
		fields=[
			"name", "competidor", "plataforma", "url_publicacion", "fecha_publicacion",
			"titulo_hook", "vistas_actual", "engagement_pct", "tier", "tier_orden",
		],
		order_by="fecha_publicacion asc, vistas_actual desc",
		limit=2000,
	)
	sufijos = _sufijos_competidor()
	out = []
	for r in rows:
		f = r.fecha_publicacion
		orden = int(r.tier_orden or 0)
		if orden and orden <= 3:
			tier_cls = " cal-tier--dragon"
		elif orden and orden <= 7:
			tier_cls = " cal-tier--cetro"
		else:
			tier_cls = ""
		url = (r.url_publicacion or "").strip()
		out.append({
			"nombre": r.name,
			"fecha": f.isoformat() if hasattr(f, "isoformat") else str(f),
			"titulo": _limpiar(r.titulo_hook) or r.name,
			"competidor": r.competidor or "",
			"plataforma": r.plataforma or "",
			"red": REDES.get(r.plataforma, (r.plataforma or "--")[:2].upper()),
			"tier": r.tier or "Sin tier",
			"tier_cls": tier_cls,
			"sufijo": sufijos.get(r.competidor or "", ""),
			"url": url if url.startswith(("http://", "https://")) else "",
		})
	return out


def _sufijos_competidor():
	"""El diseño distingue dos competidores: el base y el `--b`."""
	comps = frappe.db.get_all("Competidor", fields=["name"], order_by="name asc")
	return {c.name: ("--b" if i % 2 else "") for i, c in enumerate(comps)}


def _celdas(inicio, cuantas, mes_ancla, hoy, dia_sel, por_dia):
	celdas = []
	for i in range(cuantas):
		d = inicio + timedelta(days=i)
		iso = d.isoformat()
		posts = por_dia.get(iso, [])
		celdas.append({
			"n": d.day,
			"iso": iso,
			"fuera": d.month != mes_ancla.month,
			"hoy": d == hoy,
			"sel": d == dia_sel,
			"total": len(posts),
			"chips": posts[:CHIPS_POR_CELDA],
			"mas": max(0, len(posts) - CHIPS_POR_CELDA),
			"url": _url(dia=iso),
		})
	return celdas


def _mini(inicio, mes_ancla, hoy, dia_sel, por_dia):
	dias = []
	for i in range(42):
		d = inicio + timedelta(days=i)
		iso = d.isoformat()
		if d == hoy:
			cls = " cal-mini__n--today"
		elif d == dia_sel:
			cls = " cal-mini__n--sel"
		elif d.month != mes_ancla.month:
			cls = " cal-mini__n--out"
		else:
			cls = ""
		dias.append({
			"n": d.day,
			"cls": cls,
			"dot": bool(por_dia.get(iso)),
			"url": _url(dia=iso),
		})
	return dias


def _label_rango(vista, mes_ancla, inicio):
	if vista == "mes":
		return f"{MESES[mes_ancla.month - 1]} {mes_ancla.year}"
	fin = inicio + timedelta(days=6)
	if inicio.month == fin.month:
		return f"{inicio.day} – {fin.day} {MESES_CORTO[inicio.month - 1]} {inicio.year}"
	return (f"{inicio.day} {MESES_CORTO[inicio.month - 1]} – "
	        f"{fin.day} {MESES_CORTO[fin.month - 1]} {fin.year}")


def _plataformas():
	rows = frappe.db.sql("""
		SELECT DISTINCT plataforma FROM `tabPublicacion Competencia`
		WHERE plataforma IS NOT NULL AND plataforma != '' ORDER BY plataforma
	""", as_dict=True)
	return [r.plataforma for r in rows]


def _tiers():
	try:
		s = frappe.get_cached_doc("Radar Settings")
		return [t.nombre for t in sorted(s.tiers_viralidad or [], key=lambda x: x.orden)]
	except Exception:
		return []


def _competidores(desde, fin):
	comps = frappe.db.get_all("Competidor", fields=["name"], order_by="name asc")
	conteos = dict(frappe.db.sql("""
		SELECT competidor, COUNT(*) FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion BETWEEN %s AND %s AND competidor IS NOT NULL
		GROUP BY competidor
	""", (desde.isoformat(), fin.isoformat())))
	activo = frappe.form_dict.get("competidor") or ""
	return [
		{
			"nombre": c.name,
			"sufijo": "--b" if i % 2 else "",
			"total": int(conteos.get(c.name, 0)),
			"on": not activo or activo == c.name,
			"url": _url(competidor="" if activo == c.name else c.name),
		}
		for i, c in enumerate(comps)
	]


# ============ ENDPOINTS ============

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
