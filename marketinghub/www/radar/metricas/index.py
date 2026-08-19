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
	# ---- M-A: Meta Ads (nuevas cards) ----
	context.ads_kpis = _ads_kpis()
	context.ads_marca = _ads_por_marca(dias)
	context.ads_formatos = _ads_formatos(dias)
	context.ads_landings = _ads_landings_top(dias)
	# ---- M-B: Insights accionables ----
	context.hashtags = _hashtags_top(dias, limite=15)
	context.duracion_buckets = _duracion_video_buckets(dias)
	context.formato_ganador = _formato_ganador(dias)
	context.dow_engagement = _dow_engagement(dias)
	context.frecuencia_marca = _frecuencia_por_marca(dias)
	# ---- M-C: Panel financiero ----
	context.financiero = _financiero(dias)


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


# ============ M-A: Meta Ads ============

def _ads_kpis():
	"""Ads activos ahora + nuevos ultimos 7 dias + ganadores 30d+."""
	hoy = date.today()
	hace7 = hoy - timedelta(days=7)
	# Query unica para eficiencia
	row = frappe.db.sql("""
		SELECT COUNT(*) AS total,
		       SUM(esta_activo) AS activos,
		       SUM(CASE WHEN esta_activo=1 AND fecha_inicio >= %s THEN 1 ELSE 0 END) AS nuevos_7d,
		       SUM(CASE WHEN esta_activo=1 AND dias_activo >= 30 THEN 1 ELSE 0 END) AS ganadores_30d
		FROM `tabAnuncio Competencia`
	""", (hace7,), as_dict=True)[0]
	return {
		"total": int(row.total or 0),
		"activos": int(row.activos or 0),
		"nuevos_7d": int(row.nuevos_7d or 0),
		"ganadores_30d": int(row.ganadores_30d or 0),
	}


def _ads_por_marca(dias):
	"""Tabla ads por competidor: activos ahora, nuevos 7d, ganadores 30d+."""
	hace7 = date.today() - timedelta(days=7)
	rows = frappe.db.sql("""
		SELECT competidor,
		       COUNT(*) AS total,
		       SUM(esta_activo) AS activos,
		       SUM(CASE WHEN esta_activo=1 AND fecha_inicio >= %s THEN 1 ELSE 0 END) AS nuevos_7d,
		       SUM(CASE WHEN esta_activo=1 AND dias_activo >= 30 THEN 1 ELSE 0 END) AS ganadores_30d,
		       MAX(dias_activo) AS max_dias
		FROM `tabAnuncio Competencia`
		WHERE competidor IS NOT NULL AND competidor != ''
		GROUP BY competidor
		ORDER BY activos DESC, ganadores_30d DESC
	""", (hace7,), as_dict=True)
	for r in rows:
		r["total"] = int(r.total or 0)
		r["activos"] = int(r.activos or 0)
		r["nuevos_7d"] = int(r.nuevos_7d or 0)
		r["ganadores_30d"] = int(r.ganadores_30d or 0)
		r["max_dias"] = int(r.max_dias or 0)
		r["color"] = _color_competidor(r.competidor)
	return rows


def _ads_formatos(dias):
	"""Distribucion por formato de creatividad: Video/Imagen/Carrusel/Otro."""
	rows = frappe.db.sql("""
		SELECT COALESCE(NULLIF(formato, ''), 'Sin formato') AS formato,
		       COUNT(*) AS c,
		       SUM(esta_activo) AS activos
		FROM `tabAnuncio Competencia`
		GROUP BY formato
		ORDER BY c DESC
	""", as_dict=True)
	total = sum(int(r.c or 0) for r in rows) or 1
	for r in rows:
		r["c"] = int(r.c or 0)
		r["activos"] = int(r.activos or 0)
		r["pct"] = round(r["c"] / total * 100, 1)
	return rows


def _ads_landings_top(dias, limite=8):
	"""Top URLs de landing donde llevan los ads (dominio.com/path)."""
	rows = frappe.db.sql("""
		SELECT landing_url, COUNT(*) AS c, SUM(esta_activo) AS activos
		FROM `tabAnuncio Competencia`
		WHERE landing_url IS NOT NULL AND landing_url != ''
		GROUP BY landing_url
		ORDER BY activos DESC, c DESC
		LIMIT %s
	""", (limite,), as_dict=True)
	for r in rows:
		# Truncar landing a algo legible en tabla
		url = r.landing_url or ""
		corta = url.split("://", 1)[-1]
		if corta.startswith("www."):
			corta = corta[4:]
		r["corta"] = corta.rstrip("/")[:60]
		r["c"] = int(r.c or 0)
		r["activos"] = int(r.activos or 0)
	return rows


# ============ M-B: Insights accionables ============

def _hashtags_top(dias, limite=15):
	"""Top hashtags mas usados + engagement medio de los posts que los usan.

	Los hashtags vienen concatenados en la columna: '#a #b #c'. Los parseamos
	en Python (SQL no puede split-and-explode simple)."""
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT hashtags, engagement_pct
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		  AND hashtags IS NOT NULL AND hashtags != ''
	""", (desde,), as_dict=True)
	from collections import defaultdict
	usos = defaultdict(int)
	eng_sum = defaultdict(float)
	for r in rows:
		tags = [t.strip().lower() for t in str(r.hashtags).split()
		        if t.startswith("#") and len(t) > 1]
		# dedupe dentro de la misma publicacion (por si venia "#peru #peru")
		for tag in set(tags):
			usos[tag] += 1
			eng_sum[tag] += float(r.engagement_pct or 0)
	items = []
	for tag, n in usos.items():
		items.append({
			"tag": tag,
			"n": n,
			"eng_avg": round(eng_sum[tag] / n, 2) if n else 0,
		})
	items.sort(key=lambda x: (-x["n"], -x["eng_avg"]))
	items = items[:limite]
	maximo = items[0]["n"] if items else 1
	for i in items:
		i["pct"] = round(i["n"] / maximo * 100)
	return items


def _duracion_video_buckets(dias):
	"""Duracion optima de video: buckets 0-15s / 15-30s / 30-60s / 60+s con
	engagement medio de cada bucket. Solo considera pubs con duracion > 0."""
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT
			CASE
				WHEN duracion_segundos <= 15 THEN '0-15s'
				WHEN duracion_segundos <= 30 THEN '15-30s'
				WHEN duracion_segundos <= 60 THEN '30-60s'
				ELSE '60+s'
			END AS bucket,
			COUNT(*) AS c,
			COALESCE(AVG(engagement_pct), 0) AS eng_avg,
			COALESCE(AVG(vistas_actual), 0) AS vistas_avg,
			SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND duracion_segundos > 0
		GROUP BY bucket
	""", (desde,), as_dict=True)
	orden = ['0-15s', '15-30s', '30-60s', '60+s']
	buckets = {r.bucket: r for r in rows}
	out = []
	# Bucket ganador = mayor engagement medio
	max_eng = max((float(r.eng_avg or 0) for r in rows), default=0)
	for b in orden:
		r = buckets.get(b)
		if not r:
			out.append({"bucket": b, "c": 0, "eng_avg": 0, "vistas_avg": 0,
			            "virales": 0, "es_ganador": False})
			continue
		out.append({
			"bucket": b,
			"c": int(r.c or 0),
			"eng_avg": round(float(r.eng_avg or 0), 2),
			"vistas_avg": int(r.vistas_avg or 0),
			"virales": int(r.virales or 0),
			"es_ganador": max_eng > 0 and abs(float(r.eng_avg or 0) - max_eng) < 0.001,
		})
	return out


def _formato_ganador(dias):
	"""% de virales por tipo_contenido — cual formato pega mas."""
	desde = date.today() - timedelta(days=dias)
	rows = frappe.db.sql("""
		SELECT COALESCE(NULLIF(tipo_contenido, ''), 'Sin tipo') AS tipo,
		       COUNT(*) AS c,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales,
		       COALESCE(AVG(engagement_pct), 0) AS eng_avg
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY tipo
	""", (desde,), as_dict=True)
	out = []
	max_viral = 0
	for r in rows:
		c = int(r.c or 0)
		v = int(r.virales or 0)
		pct = round(v / c * 100, 1) if c else 0
		max_viral = max(max_viral, pct)
		out.append({
			"tipo": r.tipo,
			"c": c,
			"virales": v,
			"pct_viral": pct,
			"eng_avg": round(float(r.eng_avg or 0), 2),
		})
	# marcar el ganador
	for r in out:
		r["es_ganador"] = max_viral > 0 and abs(r["pct_viral"] - max_viral) < 0.001
	out.sort(key=lambda x: -x["pct_viral"])
	return out


def _dow_engagement(dias):
	"""Engagement medio por dia de la semana. Ayuda a decidir cuando postear."""
	desde = date.today() - timedelta(days=dias)
	dias_nombre = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
	rows = frappe.db.sql("""
		SELECT WEEKDAY(fecha_publicacion) AS dow,
		       COUNT(*) AS c,
		       COALESCE(AVG(engagement_pct), 0) AS eng_avg,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5 THEN 1 ELSE 0 END) AS virales
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY dow
	""", (desde,), as_dict=True)
	por_dow = {int(r.dow): r for r in rows}
	max_eng = max((float(r.eng_avg or 0) for r in rows), default=0)
	out = []
	for i in range(7):
		r = por_dow.get(i)
		eng = round(float(r.eng_avg or 0), 2) if r else 0
		out.append({
			"nombre": dias_nombre[i],
			"c": int(r.c or 0) if r else 0,
			"eng_avg": eng,
			"virales": int(r.virales or 0) if r else 0,
			"es_ganador": max_eng > 0 and abs(eng - max_eng) < 0.001,
			"pct_bar": round(eng / max_eng * 100) if max_eng else 0,
		})
	return out


def _frecuencia_por_marca(dias):
	"""Pubs/semana por marca. Ayuda a comparar ritmos."""
	desde = date.today() - timedelta(days=dias)
	semanas = max(dias / 7.0, 1)
	rows = frappe.db.sql("""
		SELECT competidor, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND competidor IS NOT NULL AND competidor != ''
		GROUP BY competidor
		ORDER BY c DESC
	""", (desde,), as_dict=True)
	max_c = max((int(r.c or 0) for r in rows), default=1)
	out = []
	for r in rows:
		c = int(r.c or 0)
		out.append({
			"competidor": r.competidor,
			"pubs": c,
			"pubs_semana": round(c / semanas, 1),
			"color": _color_competidor(r.competidor),
			"pct_bar": round(c / max_c * 100) if max_c else 0,
		})
	return out


# ============ M-C: Panel financiero ============

def _financiero(dias):
	"""Gasto Apify (posts + ads separados), credito restante, ROI."""
	hoy = date.today()
	inicio_mes = hoy.replace(day=1)

	# Gasto ads este mes (desde Radar Ads Gasto — nuevo del D1)
	try:
		gasto_ads_mes = float(frappe.db.sql("""
			SELECT COALESCE(SUM(coste_estimado_usd), 0)
			FROM `tabRadar Ads Gasto`
			WHERE fecha_scrape >= %s
		""", (inicio_mes,))[0][0] or 0)
	except Exception:
		gasto_ads_mes = 0

	# Gasto posts este mes (desde Radar Corrida — usa coste_real si existe)
	try:
		gasto_posts_mes = float(frappe.db.sql("""
			SELECT COALESCE(SUM(coste_usd), 0)
			FROM `tabRadar Corrida`
			WHERE fecha_inicio >= %s
		""", (inicio_mes,))[0][0] or 0)
	except Exception:
		gasto_posts_mes = 0

	# Insights conseguidos este mes (pubs nuevas + ads nuevos)
	try:
		insights_pubs = frappe.db.count("Publicacion Competencia",
		                                 filters={"creation": [">=", inicio_mes]})
	except Exception:
		insights_pubs = 0
	try:
		insights_ads = frappe.db.count("Anuncio Competencia",
		                                filters={"creation": [">=", inicio_mes]})
	except Exception:
		insights_ads = 0

	total_gasto = gasto_ads_mes + gasto_posts_mes
	total_insights = insights_pubs + insights_ads

	# Credito Apify (cacheado por credito_apify() 10min)
	credito = None
	try:
		from marketinghub.api.radar_scraper import credito_apify
		credito = credito_apify() or None
	except Exception:
		credito = None

	return {
		"gasto_ads_mes": round(gasto_ads_mes, 3),
		"gasto_posts_mes": round(gasto_posts_mes, 3),
		"gasto_total_mes": round(total_gasto, 3),
		"gasto_total_mes_fmt": f"${total_gasto:.2f}",
		"insights_pubs": int(insights_pubs),
		"insights_ads": int(insights_ads),
		"insights_total": int(total_insights),
		# insights por dolar — mas alto = mas eficiente
		"roi": round(total_insights / total_gasto, 1) if total_gasto > 0.001 else None,
		"coste_por_insight": round(total_gasto / total_insights, 4) if total_insights else None,
		"credito_apify": credito,   # {usado, limite, restante, renueva} o None
		"credito_pct": round(float(credito["usado"]) / float(credito["limite"]) * 100, 1)
		               if credito and float(credito.get("limite") or 0) > 0 else 0,
	}
