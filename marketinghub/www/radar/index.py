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
def obtener_top_virales(limite=10, dias=30):
	"""Top N virales del último período (default 30 días)."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	from datetime import date, timedelta
	desde = date.today() - timedelta(days=int(dias))
	rows = frappe.db.get_all(
		"Publicacion Competencia",
		filters={"fecha_publicacion": [">=", desde]},
		fields=[
			"name", "competidor", "plataforma", "url_publicacion",
			"fecha_publicacion", "titulo_hook", "vistas_actual",
			"likes_actual", "engagement_pct", "tier", "tier_orden", "es_viral",
		],
		order_by="vistas_actual desc, engagement_pct desc",
		limit=int(limite),
	)
	# color del competidor (para chip)
	import hashlib
	PALETA = [
		"#d50000","#e67c73","#f4511e","#f6bf26","#33b679","#0b8043",
		"#039be5","#3f51b5","#7986cb","#8e24aa","#616161","#a79b8e",
	]
	comp_colors = {c.name: (c.color or PALETA[hashlib.md5(c.name.encode()).digest()[0] % 12])
	               for c in frappe.db.get_all("Competidor", fields=["name", "color"])}
	for r in rows:
		r["color"] = comp_colors.get(r.competidor or "", "#94a3b8")
		if r.get("fecha_publicacion") and hasattr(r["fecha_publicacion"], "isoformat"):
			r["fecha_publicacion"] = r["fecha_publicacion"].isoformat()
	return rows


@frappe.whitelist()
def obtener_timeline_virales(semanas=12, tier_orden_max=5):
	"""Cantidad de virales por semana por competidor (últimas N semanas)."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	from datetime import date, timedelta
	hoy = date.today()
	# Alinear al lunes de la semana actual
	lunes_actual = hoy - timedelta(days=hoy.weekday())
	semanas = int(semanas)
	desde = lunes_actual - timedelta(weeks=semanas - 1)

	rows = frappe.db.sql("""
		SELECT competidor,
		       YEARWEEK(fecha_publicacion, 3) AS yw,
		       COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		  AND tier_orden IS NOT NULL AND tier_orden <= %s
		  AND competidor IS NOT NULL
		GROUP BY competidor, yw
		ORDER BY competidor, yw
	""", (desde, int(tier_orden_max)), as_dict=True)

	# Etiquetas de semana en formato "DD/MM"
	labels = []
	yw_index = {}
	for i in range(semanas):
		monday = desde + timedelta(weeks=i)
		iso_year, iso_week, _ = monday.isocalendar()
		yw = iso_year * 100 + iso_week
		yw_index[yw] = i
		labels.append(monday.strftime("%d/%m"))

	# Series por competidor
	series = {}
	for r in rows:
		if r.competidor not in series:
			series[r.competidor] = [0] * semanas
		i = yw_index.get(int(r.yw))
		if i is not None:
			series[r.competidor][i] = int(r.c)

	# Colores por competidor
	import hashlib
	PALETA = [
		"#d50000","#e67c73","#f4511e","#f6bf26","#33b679","#0b8043",
		"#039be5","#3f51b5","#7986cb","#8e24aa","#616161","#a79b8e",
	]
	comp_colors = {c.name: (c.color or PALETA[hashlib.md5(c.name.encode()).digest()[0] % 12])
	               for c in frappe.db.get_all("Competidor", fields=["name", "color"])}

	datasets = [
		{
			"label": comp,
			"data": data,
			"borderColor": comp_colors.get(comp, "#94a3b8"),
			"backgroundColor": comp_colors.get(comp, "#94a3b8") + "33",
			"tension": 0.3,
			"fill": False,
		}
		for comp, data in sorted(series.items())
	]
	return {"labels": labels, "datasets": datasets, "tier_orden_max": int(tier_orden_max)}


@frappe.whitelist()
def obtener_heatmap_semana(semanas=12):
	"""Matriz día_semana (7) × semana (N): cuántos posts en cada cruce."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	from datetime import date, timedelta
	hoy = date.today()
	lunes_actual = hoy - timedelta(days=hoy.weekday())
	semanas = int(semanas)
	desde = lunes_actual - timedelta(weeks=semanas - 1)

	rows = frappe.db.sql("""
		SELECT fecha_publicacion, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY fecha_publicacion
	""", (desde,), as_dict=True)

	# matriz 7 filas (Lun-Dom) × N columnas (semanas)
	matriz = [[0] * semanas for _ in range(7)]
	labels_semana = []
	for i in range(semanas):
		monday = desde + timedelta(weeks=i)
		labels_semana.append(monday.strftime("%d/%m"))

	for r in rows:
		fp = r.fecha_publicacion
		if not fp:
			continue
		# semana index
		delta_weeks = (fp - desde).days // 7
		if 0 <= delta_weeks < semanas:
			dow = fp.weekday()  # 0=Lun ... 6=Dom
			matriz[dow][delta_weeks] += int(r.c)

	# max para color intensity
	max_val = max((max(fila) for fila in matriz), default=0)

	return {
		"matriz": matriz,
		"labels_semana": labels_semana,
		"labels_dia": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"],
		"max": max_val,
	}


@frappe.whitelist()
def obtener_virales_por_competidor(dias=30):
	"""Por competidor: cuantos virales (tier 1-3) + casi virales (tier 4-5).
	Ordenado por total desc."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	from datetime import date, timedelta
	desde = date.today() - timedelta(days=int(dias))
	rows = frappe.db.sql("""
		SELECT competidor,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 3 THEN 1 ELSE 0 END) AS virales,
		       SUM(CASE WHEN tier_orden BETWEEN 4 AND 5 THEN 1 ELSE 0 END) AS casi_virales
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		  AND competidor IS NOT NULL
		  AND tier_orden IS NOT NULL
		GROUP BY competidor
		HAVING (virales + casi_virales) > 0
		ORDER BY virales DESC, casi_virales DESC
	""", (desde,), as_dict=True)
	# Colores personalizados
	import hashlib
	PALETA = [
		"#d50000","#e67c73","#f4511e","#f6bf26","#33b679","#0b8043",
		"#039be5","#3f51b5","#7986cb","#8e24aa","#616161","#a79b8e",
	]
	comp_colors = {c.name: (c.color or PALETA[hashlib.md5(c.name.encode()).digest()[0] % 12])
	               for c in frappe.db.get_all("Competidor", fields=["name", "color"])}
	for r in rows:
		r["virales"] = int(r.virales or 0)
		r["casi_virales"] = int(r.casi_virales or 0)
		r["total"] = r["virales"] + r["casi_virales"]
		r["color"] = comp_colors.get(r.competidor, "#94a3b8")
	return rows


@frappe.whitelist()
def obtener_publicaciones_por_dia_semana(dias=90):
	"""Cuenta de posts por dia de la semana en los ultimos N dias.
	Ordenado mayor a menor. Devuelve [{dow_idx, dow_nombre, count}]."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	from datetime import date, timedelta
	desde = date.today() - timedelta(days=int(dias))
	rows = frappe.db.sql("""
		SELECT WEEKDAY(fecha_publicacion) AS dow, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY WEEKDAY(fecha_publicacion)
	""", (desde,), as_dict=True)
	# WEEKDAY: 0=Lun ... 6=Dom
	NOMBRES = ["Lunes","Martes","Miércoles","Jueves","Viernes","Sábado","Domingo"]
	counts = {int(r.dow): int(r.c) for r in rows}
	total = sum(counts.values()) or 1
	out = []
	for i in range(7):
		c = counts.get(i, 0)
		out.append({
			"dow": i,
			"nombre": NOMBRES[i],
			"count": c,
			"pct": round(c / total * 100),
		})
	# Ordenar mayor a menor
	out.sort(key=lambda x: -x["count"])
	return out


@frappe.whitelist()
def obtener_contadores():
	"""Retorna contadores para el dashboard."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)

	from datetime import date, timedelta
	hoy = date.today()
	hace_24h = hoy - timedelta(days=1)
	fin_semana = hoy + timedelta(days=6)

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
		"guiones_semana": frappe.db.count("Guion", filters={
			"fecha_publicacion": ["between", [hoy, fin_semana]],
			"estado": ["!=", "Publicado"],
		}),
	}
