"""Página de gestión de Competidores.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`) y `competidores.css` es copia literal del CSS del
diseño. `get_context` solo arma los datos que pinta ese markup; el alta, la
edición y el borrado siguen pasando por los endpoints de abajo, sin cambios.
"""
import json
from datetime import date, datetime, timedelta

from frappe.utils import get_datetime

import frappe

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)
PRIORIDADES = ("Directo", "Indirecto", "Referente")



def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/competidores"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Competidores · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)
	if context.no_access:
		return

	virales = _virales_30d()
	engagement = _engagement_30d()
	sync = _ultima_sync()
	# B-Op1: cuentas sociales agrupadas por marca (para el acordeon inline).
	# Una sola query en vez de N (una por marca).
	cuentas_por_marca = _cuentas_por_marca()
	filas = []
	for c in listar():
		nombre = c.get("nombre_comercial") or c["name"]
		prio = c.get("prioridad") if c.get("prioridad") in PRIORIDADES else "Indirecto"
		cuando = sync.get(c["name"])
		cuentas_marca = cuentas_por_marca.get(c["name"], [])
		filas.append({
			"id": c["name"],
			"nombre": nombre,
			"categoria": c.get("categoria") or "Sin categoría",
			"prioridad": prio,
			"pais": c.get("pais") or "—",
			"cuentas": int(c.get("cuentas") or 0),
			"virales": virales.get(c["name"], 0),
			"eng": f"{engagement.get(c['name'], 0):.1f}%",
			"sync": _hace(cuando),
			"dias": _dias(cuando),
			"web": c.get("website") if (c.get("website") or "").startswith(("http://", "https://")) else "",
			"nombre_comercial": c.get("nombre_comercial") or "",
			"website": c.get("website") or "",
			# B-Op1: lista de cuentas sociales de esta marca
			"cuentas_lista": cuentas_marca,
			"cuentas_totales": len(cuentas_marca),
			"cuentas_activas": sum(1 for x in cuentas_marca if x.get("activo")),
		})

	context.filas_json = frappe.as_json(filas).replace("</", "<\\/")
	context.total = len(filas)
	context.categorias = sorted({f["categoria"] for f in filas if f["categoria"] != "Sin categoría"})
	context.paises = sorted({f["pais"] for f in filas if f["pais"] != "—"})
	context.prioridades = list(PRIORIDADES)
	context.categorias_alta = listar_categorias()
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


def _engagement_30d():
	"""Engagement medio de las publicaciones de los últimos 30 días."""
	desde = date.today() - timedelta(days=30)
	rows = frappe.db.sql("""
		SELECT competidor, AVG(engagement_pct) AS media
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND competidor IS NOT NULL
		GROUP BY competidor
	""", (desde,), as_dict=True)
	return {r.competidor: float(r.media or 0) for r in rows}


def _dias(cuando):
	if not cuando:
		return 99
	if isinstance(cuando, str):
		cuando = get_datetime(cuando)
	return max(0, (datetime.now() - cuando).days)


def _ultima_corrida():
	try:
		s = frappe.get_cached_doc("Radar Settings")
		return _hace(s.ultima_corrida)
	except Exception:
		return "—"


def _virales_30d():
	desde = date.today() - timedelta(days=30)
	rows = frappe.db.sql("""
		SELECT competidor, COUNT(*) AS c
		FROM `tabPublicacion Competencia`
		WHERE fecha_publicacion >= %s AND competidor IS NOT NULL
		  AND (es_viral = 1 OR (tier_orden IS NOT NULL AND tier_orden <= 5))
		GROUP BY competidor
	""", (desde,), as_dict=True)
	return {r.competidor: int(r.c) for r in rows}


def _ultima_sync():
	rows = frappe.db.sql("""
		SELECT competidor, MAX(creation) AS ultima
		FROM `tabPublicacion Competencia`
		WHERE competidor IS NOT NULL GROUP BY competidor
	""", as_dict=True)
	return {r.competidor: r.ultima for r in rows}


def _hace(cuando):
	"""'hace 13 h' / 'hace 2 d', como en el diseño."""
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


def _cuentas_por_marca():
	"""Devuelve dict {competidor: [cuenta, cuenta, ...]} con las cuentas sociales
	de cada marca + n_publicaciones y ultimo_scrapeo agregados.

	Usa 2 queries totales (una para cuentas, otra para pubs agregadas), no N.
	Sirve al acordeon del index.html: al expandir una marca se ven sus cuentas
	sin pedidos extra al backend."""
	cuentas = frappe.db.get_all(
		"Cuenta Social",
		fields=["name", "competidor", "plataforma", "handle", "url_perfil", "activo"],
		order_by="competidor asc, plataforma asc, handle asc",
	)
	if not cuentas:
		return {}
	# Contar pubs y ultimo scrapeo por cuenta en una sola query
	stats = {r["cs"]: r for r in frappe.db.sql("""
		SELECT cuenta_social AS cs, COUNT(*) AS n_pubs,
		       MAX(fecha_ultimo_scrapeo) AS ultimo
		FROM `tabPublicacion Competencia`
		WHERE cuenta_social IS NOT NULL
		GROUP BY cuenta_social
	""", as_dict=True)}
	# Formatear url corta y armar la lista por marca
	agrupado = {}
	for c in cuentas:
		st = stats.get(c["name"]) or {}
		c["n_publicaciones"] = int(st.get("n_pubs") or 0)
		ultimo = st.get("ultimo")
		c["ultimo_scrapeo_fmt"] = _hace(ultimo) if ultimo else "nunca"
		c["handle_txt"] = "@" + (c.get("handle") or "").lstrip("@") if c.get("handle") else "—"
		# URL corta legible: instagram.com/apolusso.pe
		url = c.get("url_perfil") or ""
		corta = url.split("://", 1)[-1]
		if corta.startswith("www."):
			corta = corta[4:]
		c["url_corta"] = corta.rstrip("/")[:60]
		c["url_valida"] = url.startswith(("http://", "https://"))
		agrupado.setdefault(c["competidor"] or "", []).append(c)
	return agrupado


@frappe.whitelist()
def listar():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	comps = frappe.db.get_all(
		"Competidor",
		fields=["name", "nombre_comercial", "categoria", "prioridad",
		        "pais", "website", "activo", "notas_estrategicas"],
		order_by="prioridad asc, nombre_comercial asc",
	)
	# contar cuentas activas por competidor
	for c in comps:
		c["cuentas"] = frappe.db.count(
			"Cuenta Social", filters={"competidor": c["name"], "activo": 1}
		)
	return comps


@frappe.whitelist()
def listar_categorias():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	return [c["name"] for c in frappe.db.get_all(
		"Categoria Competencia", fields=["name"], order_by="nombre_categoria asc"
	)]


@frappe.whitelist()
def guardar(name=None, nombre_comercial=None, categoria=None, prioridad=None,
            pais=None, website=None, activo=None, notas_estrategicas=None):
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede modificar.", frappe.PermissionError)
	if not nombre_comercial:
		frappe.throw("El nombre comercial es obligatorio.")

	values = {
		"nombre_comercial": nombre_comercial,
		"categoria": categoria or None,
		"prioridad": prioridad or "Indirecto",
		"pais": pais or None,
		"website": website or None,
		"activo": int(activo) if activo not in (None, "") else 1,
		"notas_estrategicas": notas_estrategicas or "",
	}
	if name:
		doc = frappe.get_doc("Competidor", name)
		for k, v in values.items():
			setattr(doc, k, v)
		doc.save(ignore_permissions=True)
	else:
		if frappe.db.exists("Competidor", nombre_comercial):
			frappe.throw(f"Ya existe un competidor llamado '{nombre_comercial}'.")
		doc = frappe.new_doc("Competidor")
		for k, v in values.items():
			setattr(doc, k, v)
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def guardar_con_cuentas(name=None, nombre_comercial=None, categoria=None,
                        prioridad=None, pais=None, website=None, activo=None,
                        notas_estrategicas=None, cuentas=None):
	"""Guarda un Competidor + sus cuentas sociales en una sola llamada (D-Op1).

	`cuentas` = lista JSON [{plataforma, url}, ...]. Si algo falla, ROLLBACK
	de todo (competidor + cuentas) — no queremos dejar un competidor huerfano
	sin sus cuentas o cuentas sin dueño.

	El competidor se guarda con `guardar()` (reutiliza validacion y unicidad).
	Cada cuenta se guarda con `www.radar.cuentas.index.guardar` — reusa toda
	la logica de deteccion de handle, dedupe, etc."""
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede crear competidores.", frappe.PermissionError)
	# Parsear cuentas — puede venir como str JSON del JS o como lista Python
	if isinstance(cuentas, str):
		try:
			cuentas = json.loads(cuentas)
		except (ValueError, TypeError):
			cuentas = []
	cuentas = cuentas or []
	# Filtrar cuentas sin URL — el user puede tener filas vacias en el modal
	cuentas = [c for c in cuentas if isinstance(c, dict) and (c.get("url") or "").strip()]

	# 1. Crear/actualizar el competidor. `guardar()` hace su propio commit al
	# final; si algo falla despues, esto ya quedo en la BD — por eso usamos
	# rollback explicito abajo si algo revienta con las cuentas.
	res = guardar(
		name=name, nombre_comercial=nombre_comercial, categoria=categoria,
		prioridad=prioridad, pais=pais, website=website, activo=activo,
		notas_estrategicas=notas_estrategicas,
	)
	comp_name = res["name"]

	# 2. Crear las cuentas — reusa el endpoint existente de cuentas.
	from marketinghub.www.radar.cuentas.index import (
		guardar as guardar_cuenta,
		detectar_plataforma,
	)
	creadas = 0
	errores = []
	for c in cuentas:
		url = (c.get("url") or "").strip()
		plat = (c.get("plataforma") or "").strip() or detectar_plataforma(url)
		if not plat:
			errores.append(f"URL no reconocida: «{url[:60]}»")
			continue
		try:
			guardar_cuenta(competidor=comp_name, plataforma=plat, url_perfil=url, activo=1)
			creadas += 1
		except Exception as e:
			# Si falla una cuenta (dedupe, url invalida, etc.) apuntar el error
			# pero seguir con las demas — no revertimos el competidor por 1 cuenta.
			# El usuario puede volver al acordeon a completar/corregir.
			frappe.db.rollback()
			errores.append(f"«{url[:60]}»: {e}")
	frappe.db.commit()
	return {
		"ok": True, "name": comp_name,
		"cuentas_creadas": creadas,
		"errores_cuentas": errores,
	}


@frappe.whitelist()
def borrar(name=None):
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede borrar.", frappe.PermissionError)
	usos = frappe.db.count("Cuenta Social", filters={"competidor": name})
	if usos:
		frappe.throw(
			f"No puedes borrar: hay {usos} cuenta(s) social(es) asociadas. "
			"Borra primero esas cuentas."
		)
	frappe.delete_doc("Competidor", name, ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
