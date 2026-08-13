"""Dashboard /radar/metricas — resumen agregado de todo el Radar.

Reusa el mismo estilo Retro-OS que /radar (radar-os.css). Backend agrega
metricas globales que /radar solo no expone: totales por plataforma,
ranking completo de competidores, distribucion por tier y por tipo de
contenido, tendencia diaria, y actividad del scraper.

Todos los numeros vienen de `Publicacion Competencia` (tabla que carga
el scraper cada dia). Sin cache: el usuario espera ver los efectos del
ultimo scrape en la misma pagina.
"""
import hashlib
from datetime import date, datetime, timedelta

import frappe

no_cache = 1

VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)
PALETA = [
	"#d50000", "#e67c73", "#f4511e", "#f6bf26", "#33b679", "#0b8043",
	"#039be5", "#3f51b5", "#7986cb", "#8e24aa", "#616161", "#a79b8e",
]


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def _fmt(n):
	"""210500 -> '210.5k' · 1200000 -> '1.2M'"""
	n = int(n or 0)
	for corte, sufijo in ((1_000_000, "M"), (1_000, "k")):
		if n >= corte:
			v = round(n / corte, 1)
			return f"{int(v) if v == int(v) else v}{sufijo}"
	return str(n)


def _color_competidor(name):
	if not name:
		return "#94a3b8"
	color = frappe.db.get_value("Competidor", name, "color")
	if color:
		return color
	return PALETA[hashlib.md5(name.encode()).digest()[0] % 12]


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/metricas"
		raise frappe.Redirect

	context.no_cache = 1

	if not _has_role(VIEW_ROLES):
		context.no_access = True
		context.required_roles = list(VIEW_ROLES)
		return

	# Si viene algo raro en ?dias= (letras, otro numero), caemos a 30
	try:
		dias = int(frappe.form_dict.get("dias") or 30)
	except (ValueError, TypeError):
		dias = 30
	if dias not in (7, 30, 90):
		dias = 30

	context.no_access = False
	context.dias = dias
	context.kpis = _kpis(dias)
	context.plataformas = _plataformas(dias)
	context.competidores = _ranking_competidores(dias)
	context.tiers = _distribucion_tiers(dias)
	context.tipos = _distribucion_tipos(dias)
	context.tendencia = _tendencia_diaria(min(dias, 30))
	context.scrape = _actividad_scrape()
	context.top_posts = _top_posts(dias, limite=15)


# ============ KPIs generales ============

def _kpis(dias):
	desde = date.today() - timedelta(days=dias)
	row = frappe.db.sql("""
		SELECT COUNT(*) AS pubs,
		       COALESCE(SUM(vistas_actual), 0)     AS vistas,
		       COALESCE(SUM(likes_actual), 0)      AS likes,
		       COALESCE(SUM(comentarios_actual), 0) AS comentarios,
		       COALESCE(SUM(compartidos_actual), 0) AS compartidos,
		       COALESCE(AVG(engagement_pct), 0)    AS eng_avg,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales,
		       SUM(CASE WHEN tier_orden BETWEEN 6 AND 7 THEN 1 ELSE 0 END) AS casi
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
	""", (desde,), as_dict=True)[0]

	# Comparativa periodo anterior para el delta
	desde_prev = desde - timedelta(days=dias)
	prev = frappe.db.sql("""
		SELECT COUNT(*) AS pubs, COALESCE(SUM(vistas_actual), 0) AS vistas
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND fecha_publicacion < %s
	""", (desde_prev, desde), as_dict=True)[0]

	def delta_pct(actual, previo):
		actual = int(actual or 0)
		previo = int(previo or 0)
		if not previo:
			return None
		return round((actual - previo) / previo * 100, 1)

	return {
		"pubs": int(row.pubs or 0),
		"vistas": int(row.vistas or 0),
		"vistas_fmt": _fmt(row.vistas),
		"likes": int(row.likes or 0),
		"likes_fmt": _fmt(row.likes),
		"comentarios": int(row.comentarios or 0),
		"comentarios_fmt": _fmt(row.comentarios),
		"compartidos": int(row.compartidos or 0),
		"compartidos_fmt": _fmt(row.compartidos),
		"eng_avg": round(float(row.eng_avg or 0), 2),
		"virales": int(row.virales or 0),
		"casi_virales": int(row.casi or 0),
		"cuentas_activas": frappe.db.count("Cuenta Social", filters={"activo": 1}),
		"competidores_activos": frappe.db.count("Competidor", filters={"activo": 1}),
		"pubs_delta_pct": delta_pct(row.pubs, prev.pubs),
		"vistas_delta_pct": delta_pct(row.vistas, prev.vistas),
	}


# ============ Comparativa por plataforma ============

def _plataformas(dias):
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT plataforma,
		       COUNT(*) AS pubs,
		       COALESCE(SUM(vistas_actual), 0)  AS vistas,
		       COALESCE(SUM(likes_actual), 0)   AS likes,
		       COALESCE(AVG(engagement_pct), 0) AS eng_avg,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales,
		       SUM(CASE WHEN tier_orden BETWEEN 6 AND 7 THEN 1 ELSE 0 END) AS casi
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND plataforma IS NOT NULL AND plataforma != ''
		GROUP BY plataforma
		ORDER BY pubs DESC
	""", (desde,), as_dict=True)

	total_vistas = sum(int(r.vistas or 0) for r in rows) or 1
	iconos = {"Instagram": "IG", "TikTok": "TT", "Facebook": "FB", "YouTube": "YT"}
	for r in rows:
		r["pubs"] = int(r.pubs or 0)
		r["vistas"] = int(r.vistas or 0)
		r["vistas_fmt"] = _fmt(r.vistas)
		r["likes"] = int(r.likes or 0)
		r["likes_fmt"] = _fmt(r.likes)
		r["eng_avg"] = round(float(r.eng_avg or 0), 2)
		r["virales"] = int(r.virales or 0)
		r["casi"] = int(r.casi or 0)
		r["share_vistas"] = round(r["vistas"] / total_vistas * 100, 1)
		r["icono"] = iconos.get(r.plataforma, (r.plataforma or "??")[:2].upper())
	return rows


# ============ Ranking competidores ============

def _ranking_competidores(dias):
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT competidor,
		       COUNT(*) AS pubs,
		       COALESCE(SUM(vistas_actual), 0)  AS vistas,
		       COALESCE(AVG(engagement_pct), 0) AS eng_avg,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales,
		       SUM(CASE WHEN tier_orden BETWEEN 6 AND 7 THEN 1 ELSE 0 END) AS casi,
		       MAX(vistas_actual) AS mejor_vistas
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND competidor IS NOT NULL AND competidor != ''
		GROUP BY competidor
		ORDER BY vistas DESC, virales DESC
	""", (desde,), as_dict=True)

	out = []
	for r in rows:
		mejor_url = None
		if r.mejor_vistas:
			mejor_url = frappe.db.get_value(
				"Publicacion Competencia",
				{"competidor": r.competidor, "vistas_actual": r.mejor_vistas,
				 "fecha_publicacion": [">=", desde]},
				"url_publicacion",
			)
		out.append({
			"competidor": r.competidor,
			"color": _color_competidor(r.competidor),
			"pubs": int(r.pubs or 0),
			"vistas": int(r.vistas or 0),
			"vistas_fmt": _fmt(r.vistas),
			"eng_avg": round(float(r.eng_avg or 0), 2),
			"virales": int(r.virales or 0),
			"casi": int(r.casi or 0),
			"mejor_vistas_fmt": _fmt(r.mejor_vistas or 0),
			"mejor_url": mejor_url or "",
		})
	return out


# ============ Distribucion por tier ============

def _distribucion_tiers(dias):
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT tier, tier_orden, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND tier IS NOT NULL AND tier != ''
		GROUP BY tier, tier_orden
		ORDER BY tier_orden
	""", (desde,), as_dict=True)

	# Traer color desde Tier Viralidad si existe
	colores = {}
	try:
		for t in frappe.db.get_all("Tier Viralidad", fields=["name", "color", "orden"]):
			colores[t.name] = t.color or PALETA[(t.orden or 0) % 12]
	except Exception:
		pass

	total = sum(int(r.c or 0) for r in rows) or 1
	for r in rows:
		r["c"] = int(r.c or 0)
		r["pct"] = round(r["c"] / total * 100, 1)
		r["color"] = colores.get(r.tier, PALETA[(int(r.tier_orden or 0)) % 12])
	return rows


# ============ Distribucion por tipo de contenido ============

def _distribucion_tipos(dias):
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT COALESCE(NULLIF(tipo_contenido, ''), 'Sin tipo') AS tipo,
		       COUNT(*) AS c,
		       COALESCE(AVG(engagement_pct), 0) AS eng_avg,
		       COALESCE(SUM(vistas_actual), 0)  AS vistas,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY tipo
		ORDER BY c DESC
	""", (desde,), as_dict=True)
	total = sum(int(r.c or 0) for r in rows) or 1
	for r in rows:
		r["c"] = int(r.c or 0)
		r["pct"] = round(r["c"] / total * 100, 1)
		r["eng_avg"] = round(float(r.eng_avg or 0), 2)
		r["vistas_fmt"] = _fmt(r.vistas)
		r["virales"] = int(r.virales or 0)
	return rows


# ============ Tendencia diaria ============

def _tendencia_diaria(dias):
	desde = date.today() - timedelta(days=dias - 1)
	rows = frappe.db.sql("""
		SELECT fecha_publicacion AS f, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY fecha_publicacion
	""", (desde,), as_dict=True)
	mapa = {r.f.isoformat() if hasattr(r.f, "isoformat") else str(r.f): int(r.c or 0)
	        for r in rows}
	out = []
	for i in range(dias):
		d = desde + timedelta(days=i)
		out.append({
			"fecha": d.isoformat(),
			"label": d.strftime("%d/%m"),
			"count": mapa.get(d.isoformat(), 0),
		})
	maximo = max((x["count"] for x in out), default=0)
	for x in out:
		x["h"] = round(x["count"] / maximo * 100) if maximo else 0
	return out


# ============ Actividad del scraper ============

def _actividad_scrape():
	filas = frappe.db.sql("""
		SELECT cs.name, cs.plataforma, cs.handle, cs.competidor, cs.activo,
		       COUNT(p.name) AS pubs,
		       MAX(p.fecha_ultimo_scrapeo) AS ultimo_scrape,
		       MAX(p.creation) AS ultima_creacion
		FROM `tabCuenta Social` cs
		LEFT JOIN `tabPublicacion Competencia` p ON p.cuenta_social = cs.name
		GROUP BY cs.name
		ORDER BY cs.activo DESC, ultimo_scrape DESC
	""", as_dict=True)

	ahora = datetime.now()
	for f in filas:
		f["activo"] = int(f.activo or 0)
		f["pubs"] = int(f.pubs or 0)
		ref = f.ultimo_scrape or f.ultima_creacion
		if ref:
			if hasattr(ref, "date"):
				delta = ahora - ref
			else:
				delta = ahora - datetime.fromisoformat(str(ref))
			hrs = int(delta.total_seconds() / 3600)
			if hrs < 1:
				f["hace"] = "hace <1 h"
			elif hrs < 24:
				f["hace"] = f"hace {hrs} h"
			else:
				f["hace"] = f"hace {hrs // 24} d"
			f["stale"] = hrs > 36  # más de 36 h sin scrapeo = ojo
		else:
			f["hace"] = "nunca"
			f["stale"] = True
	return filas


# ============ Top posts detallados ============

def _top_posts(dias, limite=15):
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.get_all(
		"Publicacion Competencia",
		filters={"fecha_publicacion": [">=", desde]},
		fields=[
			"name", "competidor", "plataforma", "tipo_contenido",
			"url_publicacion", "fecha_publicacion", "titulo_hook",
			"vistas_actual", "likes_actual", "comentarios_actual",
			"compartidos_actual", "engagement_pct", "tier", "tier_orden",
		],
		order_by="vistas_actual desc, engagement_pct desc",
		limit=limite,
	)
	for r in rows:
		r["vistas_fmt"] = _fmt(r.vistas_actual)
		r["likes_fmt"] = _fmt(r.likes_actual)
		r["comentarios_fmt"] = _fmt(r.comentarios_actual)
		r["engagement_pct"] = round(float(r.engagement_pct or 0), 2)
		r["color"] = _color_competidor(r.competidor)
		if r.get("fecha_publicacion") and hasattr(r["fecha_publicacion"], "isoformat"):
			r["fecha_publicacion"] = r["fecha_publicacion"].isoformat()
		r["fecha_fmt"] = (r["fecha_publicacion"][8:10] + "/" + r["fecha_publicacion"][5:7]
		                  if r.get("fecha_publicacion") and len(str(r["fecha_publicacion"])) == 10
		                  else "")
	return rows
