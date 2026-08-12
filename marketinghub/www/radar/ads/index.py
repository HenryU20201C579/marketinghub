"""Página /radar/ads — feed de anuncios de la competencia (Meta Ad Library)."""
import json
import frappe
from frappe.utils import today, add_days, getdate

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
ANALISTA_ROLES = ("Marketinghub-Radar-Analista",) + ADMIN_ROLES
VIEW_ROLES = ("Marketinghub-Radar-Ver",) + ANALISTA_ROLES


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/ads"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Ads Library · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ANALISTA_ROLES)

	context.usuario = frappe.session.user
	if context.no_access:
		return

	filas = [_fila(a) for a in listar()]
	context.filas_json = frappe.as_json(filas).replace("</", "<\\/")
	context.total = len(filas)
	context.competidores = [c for c in obtener_competidores() if any(f["marca"] == c for f in filas)]
	context.formatos = sorted({f["formato"] for f in filas if f["formato"]})
	context.etiquetas = sorted({f["etiqueta"] for f in filas if f["etiqueta"]})
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


# El diseño solo dibuja icono para estos tres formatos
GANADORAS = ("Ganador", "Ganador top")


def _fila(a):
	iso = a.get("fecha_inicio") or ""
	landing = (a.get("landing_url") or "").split("://", 1)[-1]
	if landing.startswith("www."):
		landing = landing[4:]
	archive = a.get("ad_archive_id") or ""
	return {
		"id": a["name"],
		"dias": int(a.get("dias_activo") or 0),
		"etiqueta": a.get("etiqueta_ganador") or "Sin etiqueta",
		"ganador": (a.get("etiqueta_ganador") or "") in GANADORAS,
		"activo": bool(a.get("esta_activo")),
		"marca": a.get("competidor") or "",
		"formato": a.get("formato") or "Otro",
		"pub": f"{iso[8:10]}/{iso[5:7]}/{iso[2:4]}" if len(iso) == 10 else "—",
		"iso": iso,
		"copy": _limpiar(a.get("copy_texto"))[:160] or a["name"],
		"cta": a.get("cta_type") or "—",
		"landing": landing.rstrip("/")[:60] or "—",
		"url": f"https://www.facebook.com/ads/library/?id={archive}" if archive else "",
	}


def _limpiar(texto):
	import re
	texto = re.sub(r"\s+", " ", texto or "")
	return texto.strip()


def _ultima_corrida():
	from datetime import datetime
	try:
		s = frappe.get_cached_doc("Radar Settings")
		if not s.ultima_corrida:
			return "—"
		from frappe.utils import get_datetime
		minutos = int((datetime.now() - get_datetime(s.ultima_corrida)).total_seconds() // 60)
		if minutos < 60:
			return f"hace {max(minutos, 1)} min"
		if minutos < 60 * 24:
			return f"hace {minutos // 60} h"
		return f"hace {minutos // (60 * 24)} d"
	except Exception:
		return "—"


# =============== LISTA ===============

@frappe.whitelist()
def listar(competidor=None, formato=None, etiqueta=None, activos=None, dias_min=None, q=None):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	filters = {}
	if competidor:
		filters["competidor"] = competidor
	if formato:
		filters["formato"] = formato
	if etiqueta:
		filters["etiqueta_ganador"] = etiqueta
	if activos and str(activos) in ("1", "true", "True"):
		filters["esta_activo"] = 1
	if dias_min:
		filters["dias_activo"] = [">=", int(dias_min)]

	rows = frappe.db.get_all(
		"Anuncio Competencia",
		filters=filters,
		fields=[
			"name", "ad_archive_id", "competidor", "page_name",
			"fecha_inicio", "fecha_ultimo_visto", "fecha_pausado",
			"dias_activo", "esta_activo", "etiqueta_ganador",
			"formato", "copy_texto", "cta_type", "landing_url",
			"plataformas", "n_variantes", "video_hd_url", "video_sd_url",
			"imagen_preview_url", "modified",
		],
		order_by="dias_activo desc, fecha_inicio desc",
		limit=1000,
	)
	# Filtro por búsqueda en copy
	if q:
		q_low = q.lower()
		rows = [r for r in rows if q_low in (r.copy_texto or "").lower()]

	# Colores por competidor (para el dot)
	if rows:
		comps = list({r.competidor for r in rows if r.competidor})
		colores = {}
		if comps:
			import hashlib
			PALETA = [
				"#d50000","#e67c73","#f4511e","#f6bf26","#33b679","#0b8043",
				"#039be5","#3f51b5","#7986cb","#8e24aa","#616161","#a79b8e",
			]
			for c in frappe.db.get_all("Competidor", filters={"name": ["in", comps]},
			                            fields=["name", "color"]):
				colores[c.name] = c.color or PALETA[hashlib.md5(c.name.encode()).digest()[0] % 12]
		for r in rows:
			r["color"] = colores.get(r.competidor, "#94a3b8")

	# Fechas → iso
	for r in rows:
		if r.fecha_inicio and hasattr(r.fecha_inicio, "isoformat"):
			r["fecha_inicio"] = r.fecha_inicio.isoformat()
		if r.fecha_ultimo_visto and hasattr(r.fecha_ultimo_visto, "isoformat"):
			r["fecha_ultimo_visto"] = r.fecha_ultimo_visto.isoformat()
		if r.fecha_pausado and hasattr(r.fecha_pausado, "isoformat"):
			r["fecha_pausado"] = r.fecha_pausado.isoformat()

	return rows


@frappe.whitelist()
def obtener_ad(name):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	doc = frappe.get_doc("Anuncio Competencia", name).as_dict()
	# fechas
	for f in ("fecha_inicio", "fecha_ultimo_visto", "fecha_pausado"):
		v = doc.get(f)
		if v and hasattr(v, "isoformat"):
			doc[f] = v.isoformat()
	return doc


@frappe.whitelist()
def obtener_presion():
	"""Presión publicitaria por competidor: ads activos hoy, hace 7d, hace 30d + sparkline."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	hoy = getdate(today())

	# Contamos ads activos por competidor
	rows = frappe.db.sql("""
		SELECT competidor,
		       SUM(esta_activo) AS activos,
		       SUM(CASE WHEN dias_activo >= 30 AND esta_activo=1 THEN 1 ELSE 0 END) AS ganadores,
		       SUM(CASE WHEN dias_activo < 7 AND esta_activo=1 THEN 1 ELSE 0 END) AS nuevos,
		       COUNT(*) AS total
		FROM `tabAnuncio Competencia`
		GROUP BY competidor
		ORDER BY activos DESC
	""", as_dict=True)

	# Total globales
	global_ganadores = sum(int(r.ganadores or 0) for r in rows)
	global_nuevos = sum(int(r.nuevos or 0) for r in rows)
	global_activos = sum(int(r.activos or 0) for r in rows)

	# Colores
	import hashlib
	PALETA = [
		"#d50000","#e67c73","#f4511e","#f6bf26","#33b679","#0b8043",
		"#039be5","#3f51b5","#7986cb","#8e24aa","#616161","#a79b8e",
	]
	colores = {c.name: (c.color or PALETA[hashlib.md5(c.name.encode()).digest()[0] % 12])
	           for c in frappe.db.get_all("Competidor", fields=["name", "color"])}
	for r in rows:
		r["color"] = colores.get(r.competidor, "#94a3b8")
		r["activos"] = int(r.activos or 0)
		r["ganadores"] = int(r.ganadores or 0)
		r["nuevos"] = int(r.nuevos or 0)
		r["total"] = int(r.total or 0)

	return {
		"por_competidor": rows,
		"totales": {
			"activos": global_activos,
			"ganadores": global_ganadores,
			"nuevos": global_nuevos,
		},
	}


@frappe.whitelist()
def obtener_competidores():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	return frappe.db.get_all(
		"Competidor", filters={"activo": 1},
		fields=["name", "nombre_comercial"],
		order_by="nombre_comercial asc",
	)


@frappe.whitelist()
def crear_guion_desde_ad(ad_name):
	"""Botón 'Hacer guión de este ad' — crea un Guion con el ad como referencia externa."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede crear guiones.", frappe.PermissionError)
	ad = frappe.db.get_value(
		"Anuncio Competencia", ad_name,
		["competidor", "copy_texto", "formato", "page_name"], as_dict=True,
	)
	if not ad:
		frappe.throw("Ad no encontrado.")
	# El Guion actual apunta a Publicacion Competencia; para ads no hay Link directo
	# pero guardamos referencia en el título y notas.
	titulo = f"Ad Meta: {(ad.copy_texto or ad.page_name or ad_name)[:100]}"
	notas = f"Basado en anuncio de Meta Ad Library.\n\nCompetidor: {ad.competidor or ''}\nCopy original: {ad.copy_texto or ''}\nAd ID: {ad_name}"
	doc = frappe.get_doc({
		"doctype": "Guion",
		"titulo": titulo,
		"estado": "Idea",
		"competidor_ref": ad.competidor,
		"plataforma": "Ambas",  # ads Meta corren en IG+FB
		"notas_edicion": notas,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "url": f"/radar/guion?name={doc.name}"}
