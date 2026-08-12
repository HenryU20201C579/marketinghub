"""Página de gestión de Competidores.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`) y `competidores.css` es copia literal del CSS del
diseño. `get_context` solo arma los datos que pinta ese markup; el alta, la
edición y el borrado siguen pasando por los endpoints de abajo, sin cambios.
"""
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
	filas = []
	for c in listar():
		nombre = c.get("nombre_comercial") or c["name"]
		prio = c.get("prioridad") if c.get("prioridad") in PRIORIDADES else "Indirecto"
		cuando = sync.get(c["name"])
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
