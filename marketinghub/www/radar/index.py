"""Dashboard /radar.

El frontend (HTML + CSS) es el diseño Retro-OS del zip, servido tal cual:
`index.html` es un documento standalone (no extiende `templates/web.html`),
así que Frappe lo entrega sin navbar, sin contenedores ni estilos del website.
Lo único que cambia respecto al zip son los datos: se resuelven en el backend
y se inyectan con Jinja, manteniendo el mismo markup y las mismas clases.
"""
import hashlib
from datetime import date, timedelta

import frappe

no_cache = 1

VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)
ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")

PALETA = [
	"#d50000", "#e67c73", "#f4511e", "#f6bf26", "#33b679", "#0b8043",
	"#039be5", "#3f51b5", "#7986cb", "#8e24aa", "#616161", "#a79b8e",
]
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def _colores_competidor():
	return {
		c.name: (c.color or PALETA[hashlib.md5(c.name.encode()).digest()[0] % 12])
		for c in frappe.db.get_all("Competidor", fields=["name", "color"])
	}


def _fmt_vistas(v):
	"""210500 -> '210.5k' · 21000 -> '21k' · 1200000 -> '1.2M'"""
	v = int(v or 0)
	for corte, sufijo in ((1_000_000, "M"), (1_000, "k")):
		if v >= corte:
			n = round(v / corte, 1)
			return f"{int(n) if n == int(n) else n}{sufijo}"
	return str(v)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar"
		raise frappe.Redirect

	context.no_cache = 1

	if not _has_role(VIEW_ROLES):
		context.no_access = True
		context.required_roles = list(VIEW_ROLES)
		return

	dias = 7 if str(frappe.form_dict.get("dias") or "") == "7" else 30

	context.no_access = False
	context.dias = dias
	context.fecha_hoy = date.today().strftime("%d/%m")
	context.counts = obtener_contadores()
	context.kpis = context.counts
	context.top = _top_para_vista(dias)
	context.comps = _competidores_para_vista(30)
	context.dow, context.nota = _dias_para_vista(90)


# ============ ARMADO DE LA VISTA ============

def _top_para_vista(dias):
	filas = []
	for p in obtener_top_virales(limite=10, dias=dias):
		tier = int(p.get("tier_orden") or 0)
		if tier and tier <= 5:
			bar = " rad-viral__bar--viral"
		elif tier in (6, 7):
			bar = " rad-viral__bar--casi"
		else:
			bar = ""
		eng = float(p.get("engagement_pct") or 0)
		fecha = p.get("fecha_publicacion") or ""
		meta = " · ".join(
			x for x in (
				p.get("competidor"),
				p.get("plataforma"),
				f"{fecha[8:10]}/{fecha[5:7]}" if len(fecha) == 10 else "",
			) if x
		)
		url = (p.get("url_publicacion") or "").strip()
		filas.append({
			"titulo": (p.get("titulo_hook") or p.get("name") or "").strip(),
			"meta": meta,
			"url_publicacion": url if url.startswith(("http://", "https://")) else "",
			"vistas_fmt": _fmt_vistas(p.get("vistas_actual")),
			"eng_fmt": f"{eng:.1f}%",
			"eng_cls": " rad-viral__eng--high" if eng >= 1.5 else "",
			"bar_cls": bar,
		})
	return filas


def _competidores_para_vista(dias):
	filas = obtener_virales_por_competidor(dias=dias)
	for c in filas:
		total = c["total"] or 1
		# Ancho proporcional al total de la fila, con un mínimo legible para que
		# quepa el número dentro de la barra.
		c["pct_viral"] = max(8, round(c["virales"] / total * 100)) if c["virales"] else 0
		c["pct_casi"] = max(8, round(c["casi_virales"] / total * 100)) if c["casi_virales"] else 0
	return filas


def _dias_para_vista(dias):
	filas = obtener_publicaciones_por_dia_semana(dias=dias)
	maximo = max((f["count"] for f in filas), default=0)
	for f in filas:
		es_top = bool(maximo) and f["count"] == maximo
		f["width"] = round(f["count"] / maximo * 100) if maximo else 0
		f["label_cls"] = " rad-day__label--top" if es_top else ("" if f["count"] else " rad-day__label--zero")
		f["fill_cls"] = " rad-day__fill--top" if es_top else ""

	total = sum(f["count"] for f in filas)
	if not total:
		return filas, ""
	top2 = filas[:2]
	pct = round(sum(f["count"] for f in top2) / total * 100)
	nombres = " y ".join(f["nombre"].lower() for f in top2 if f["count"])
	if not nombres:
		return filas, ""
	return filas, f"El {pct}% de las publicaciones de tus competidores salen {nombres}."


# ============ ENDPOINTS ============

@frappe.whitelist()
def obtener_top_virales(limite=10, dias=30):
	"""Top N publicaciones por vistas del último período."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
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
	colores = _colores_competidor()
	for r in rows:
		r["color"] = colores.get(r.competidor or "", "#94a3b8")
		if r.get("fecha_publicacion") and hasattr(r["fecha_publicacion"], "isoformat"):
			r["fecha_publicacion"] = r["fecha_publicacion"].isoformat()
	return rows


@frappe.whitelist()
def obtener_virales_por_competidor(dias=30):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	desde = date.today() - timedelta(days=int(dias))
	rows = frappe.db.sql("""
		SELECT competidor,
		       SUM(CASE WHEN tier_orden BETWEEN 1 AND 5  THEN 1 ELSE 0 END) AS virales,
		       SUM(CASE WHEN tier_orden BETWEEN 6 AND 7  THEN 1 ELSE 0 END) AS casi_virales,
		       SUM(CASE WHEN tier_orden BETWEEN 8 AND 10 THEN 1 ELSE 0 END) AS bajo
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND competidor IS NOT NULL
		GROUP BY competidor
		ORDER BY virales DESC, casi_virales DESC, bajo DESC
	""", (desde,), as_dict=True)
	colores = _colores_competidor()
	for r in rows:
		r["virales"] = int(r.virales or 0)
		r["casi_virales"] = int(r.casi_virales or 0)
		r["bajo"] = int(r.bajo or 0)
		r["total"] = r["virales"] + r["casi_virales"] + r["bajo"]
		r["color"] = colores.get(r.competidor, "#94a3b8")
	return rows


@frappe.whitelist()
def obtener_publicaciones_por_dia_semana(dias=90):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	desde = date.today() - timedelta(days=int(dias))
	rows = frappe.db.sql("""
		SELECT WEEKDAY(fecha_publicacion) AS dow, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s
		GROUP BY WEEKDAY(fecha_publicacion)
	""", (desde,), as_dict=True)
	counts = {int(r.dow): int(r.c) for r in rows}
	total = sum(counts.values()) or 1
	out = [
		{"dow": i, "nombre": DIAS_SEMANA[i], "count": counts.get(i, 0),
		 "pct": round(counts.get(i, 0) / total * 100)}
		for i in range(7)
	]
	out.sort(key=lambda x: -x["count"])
	return out


@frappe.whitelist()
def obtener_contadores():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	hoy = date.today()
	hace_24h = hoy - timedelta(days=1)
	fin_semana = hoy + timedelta(days=6)
	try:
		guiones = frappe.db.count("Guion")
	except Exception:
		guiones = 0
	try:
		ads = frappe.db.count("Anuncio Competencia", filters={"esta_activo": 1})
	except Exception:
		ads = 0
	try:
		guiones_semana = frappe.db.count("Guion", filters={
			"fecha_publicacion": ["between", [hoy, fin_semana]],
			"estado": ["!=", "Publicado"],
		})
	except Exception:
		guiones_semana = 0
	return {
		"categorias": frappe.db.count("Categoria Competencia"),
		"competidores": frappe.db.count("Competidor", filters={"activo": 1}),
		"cuentas": frappe.db.count("Cuenta Social", filters={"activo": 1}),
		"publicaciones": frappe.db.count("Publicacion Competencia"),
		"guiones": guiones,
		"ads": ads,
		"virales": frappe.db.count("Publicacion Competencia", filters={"es_viral": 1}),
		"virales_hoy": frappe.db.count("Publicacion Competencia", filters={
			"es_viral": 1, "fecha_publicacion": [">=", hace_24h],
		}),
		"nuevos": frappe.db.count("Publicacion Competencia", filters={"estado": "Nuevo"}),
		"guiones_semana": guiones_semana,
	}
