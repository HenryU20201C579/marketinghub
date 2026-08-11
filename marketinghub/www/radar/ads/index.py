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
