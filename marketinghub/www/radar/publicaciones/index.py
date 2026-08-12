"""Página del feed de Publicaciones Competencia.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`) y `publicaciones.css` es copia literal del CSS
del diseño. `get_context` solo prepara las filas que pinta la tabla; el análisis
y el alta de guiones siguen pasando por los endpoints existentes.
"""
import re
from datetime import date, datetime, timedelta

from frappe.utils import get_datetime

import frappe

no_cache = 1

# El diseño abrevia la red en dos letras
REDES = {"Instagram": "IG", "TikTok": "TT", "Facebook": "FB", "YouTube": "YT"}
# ...y colorea el estado con estas clases
ESTADO_CLASE = {"Nuevo": "", "Analizado": "ok", "Guardado": "guion", "Descartado": "prog"}

RE_EMOJI = re.compile(
	"[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
	"⬀-⯿←-⇿️‍]+"
)

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
ANALISTA_ROLES = ("Marketinghub-Radar-Analista",) + ADMIN_ROLES
VIEW_ROLES = ("Marketinghub-Radar-Ver",) + ANALISTA_ROLES

ESTADOS = ("Nuevo", "Analizado", "Guardado", "Descartado")
FORMATOS = (
	"Unboxing", "Testimonio", "Tutorial", "Oferta", "UGC",
	"Antes/Después", "Reto/Challenge", "Trend/Sonido viral",
	"Producto en uso", "Otro",
)


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/publicaciones"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Publicaciones · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ANALISTA_ROLES)
	context.estados = list(ESTADOS)
	context.formatos = list(FORMATOS)
	if context.no_access:
		return

	filas = [_fila(p) for p in listar(limite=1000)]
	_marcar_destacados(filas)
	context.filas_json = frappe.as_json(filas).replace("</", "<\\/")
	context.total = len(filas)
	opciones = opciones_filtros()
	context.tiers = [t["nombre"] for t in opciones["tiers"]]
	context.competidores = opciones["competidores"]
	# solo las redes presentes, con la sigla que usa el diseño
	context.redes = [
		{"sigla": REDES.get(p, p[:2].upper()), "nombre": p}
		for p in opciones["plataformas"]
		if any(f["plat_nombre"] == p for f in filas)
	]
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


def _fila(p):
	f = p.get("fecha_publicacion")
	iso = f.isoformat() if hasattr(f, "isoformat") else str(f or "")
	sync = p.get("fecha_ultimo_scrapeo")
	dias = _dias_desde(sync)
	plataforma = p.get("plataforma") or ""
	return {
		"id": p["name"],
		"tier": p.get("tier") or "Sin tier",
		"orden": int(p.get("tier_orden") or 99),
		"top": False,  # lo decide _marcar_destacados con el conjunto completo
		"plat": REDES.get(plataforma, (plataforma or "--")[:2].upper()),
		"plat_nombre": plataforma,
		"comp": p.get("competidor") or "",
		"fecha": f"{iso[8:10]}/{iso[5:7]}/{iso[2:4]}" if len(iso) == 10 else "—",
		"iso": iso,
		"titulo": _limpiar(p.get("titulo_hook")) or p["name"],
		"url": (p.get("url_publicacion") or "") if (p.get("url_publicacion") or "").startswith(("http://", "https://")) else "",
		"v": int(p.get("vistas_actual") or 0),
		"l": int(p.get("likes_actual") or 0),
		"c": int(p.get("comentarios_actual") or 0),
		"s": int(p.get("compartidos_actual") or 0),
		"g": int(p.get("guardados_actual") or 0),
		"e": float(p.get("engagement_pct") or 0),
		"sync": _hace(sync),
		"dias": dias,
		"estado": p.get("estado") or "Nuevo",
		"cls": ESTADO_CLASE.get(p.get("estado") or "Nuevo", ""),
	}


def _marcar_destacados(filas):
	"""El diseño resalta en dorado los dos mejores tiers presentes."""
	ordenes = sorted({f["orden"] for f in filas if f["orden"] < 99})[:2]
	for f in filas:
		f["top"] = f["orden"] in ordenes


def _limpiar(texto):
	return re.sub(r"\s{2,}", " ", RE_EMOJI.sub(" ", texto or "")).strip(" ·-—")


def _dias_desde(cuando):
	if not cuando:
		return 99
	if isinstance(cuando, str):
		cuando = get_datetime(cuando)
	return max(0, (datetime.now() - cuando).days)


def _hace(cuando):
	if not cuando:
		return "sin datos"
	if isinstance(cuando, str):
		cuando = get_datetime(cuando)
	minutos = int((datetime.now() - cuando).total_seconds() // 60)
	if minutos < 60:
		return f"hace {max(minutos, 1)} min"
	if minutos < 60 * 24:
		return f"hace {minutos // 60} h"
	return f"hace {minutos // (60 * 24)} d"


def _ultima_corrida():
	try:
		s = frappe.get_cached_doc("Radar Settings")
		return _hace(s.ultima_corrida)
	except Exception:
		return "—"


@frappe.whitelist()
def listar(competidor=None, plataforma=None, estado=None,
           fecha_desde=None, fecha_hasta=None, limite=None):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	filters = {}
	if competidor:
		filters["competidor"] = competidor
	if plataforma:
		filters["plataforma"] = plataforma
	if estado:
		filters["estado"] = estado
	if fecha_desde and fecha_hasta:
		filters["fecha_publicacion"] = ["between", [fecha_desde, fecha_hasta]]
	elif fecha_desde:
		filters["fecha_publicacion"] = [">=", fecha_desde]
	elif fecha_hasta:
		filters["fecha_publicacion"] = ["<=", fecha_hasta]

	limite = int(limite or 500)
	pubs = frappe.db.get_all(
		"Publicacion Competencia",
		filters=filters,
		fields=[
			"name", "cuenta_social", "competidor", "plataforma",
			"url_publicacion", "fecha_publicacion", "tipo_contenido",
			"titulo_hook", "descripcion",
			"vistas_actual", "likes_actual", "comentarios_actual",
			"compartidos_actual", "guardados_actual",
			"engagement_pct", "es_viral", "tier", "tier_orden",
			"formato", "estado", "fecha_ultimo_scrapeo",
			"notas_analisis", "elementos_a_copiar",
		],
		order_by="tier_orden asc, fecha_publicacion desc",
		limit=limite,
	)
	return pubs


@frappe.whitelist()
def opciones_filtros():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	competidores = [c["name"] for c in frappe.db.get_all(
		"Competidor", fields=["name"], order_by="nombre_comercial asc",
	)]
	# Tiers con su config visual
	s = frappe.get_cached_doc("Radar Settings")
	tiers = []
	for t in sorted(s.tiers_viralidad or [], key=lambda x: x.orden):
		tiers.append({
			"orden": t.orden,
			"nombre": t.nombre,
			"imagen_url": t.imagen_url,
			"color_hex": t.color_hex,
			"es_viral": bool(t.es_viral),
		})
	return {
		"competidores": competidores,
		"plataformas": ["Instagram", "TikTok", "Facebook", "YouTube"],
		"estados": list(ESTADOS),
		"tiers": tiers,
	}


@frappe.whitelist()
def actualizar_analisis(name=None, formato=None, estado=None,
                        notas_analisis=None, elementos_a_copiar=None):
	if not _has_role(ANALISTA_ROLES):
		frappe.throw(
			"Solo un analista puede modificar el análisis.",
			frappe.PermissionError,
		)
	doc = frappe.get_doc("Publicacion Competencia", name)
	if formato is not None:
		doc.formato = formato or None
	if estado is not None:
		if estado not in ESTADOS:
			frappe.throw(f"Estado inválido. Usa uno de: {', '.join(ESTADOS)}")
		doc.estado = estado
	if notas_analisis is not None:
		doc.notas_analisis = notas_analisis
	if elementos_a_copiar is not None:
		doc.elementos_a_copiar = elementos_a_copiar
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
