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
# El diseño distingue la prioridad con el color del avatar y del badge
PRIO_CLS = {
	"Directo": {"avatar": "", "badge": ""},
	"Indirecto": {"avatar": " cmp-avatar--neutral", "badge": " cmp-prio--ind"},
	"Referente": {"avatar": " cmp-avatar--top", "badge": " cmp-prio--ref"},
}


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

	fd = frappe.form_dict
	context.f_q = (fd.get("q") or "").strip()
	context.f_prioridad = fd.get("prioridad") if fd.get("prioridad") in PRIORIDADES else ""
	context.f_categoria = fd.get("categoria") or ""
	context.hay_filtros = bool(context.f_q or context.f_prioridad or context.f_categoria)

	todos = listar()
	visibles = [
		c for c in todos
		if (not context.f_q or context.f_q.lower() in (c.get("nombre_comercial") or c["name"]).lower())
		and (not context.f_prioridad or c.get("prioridad") == context.f_prioridad)
		and (not context.f_categoria or c.get("categoria") == context.f_categoria)
	]

	virales = _virales_30d()
	sync = _ultima_sync()
	tope = max(list(virales.values()) + [1])
	for c in visibles:
		nombre = c.get("nombre_comercial") or c["name"]
		prio = c.get("prioridad") if c.get("prioridad") in PRIO_CLS else "Indirecto"
		n = virales.get(c["name"], 0)
		c["titulo"] = nombre
		c["inicial"] = nombre[:1].upper()
		c["prioridad_label"] = prio
		c["avatar_cls"] = PRIO_CLS[prio]["avatar"]
		c["badge_cls"] = PRIO_CLS[prio]["badge"]
		c["virales"] = n
		c["virales_pct"] = round(n / tope * 100) if n else 3
		c["web"] = c.get("website") if (c.get("website") or "").startswith(("http://", "https://")) else ""
		c["sync"] = _hace(sync.get(c["name"]))

	context.competidores = visibles
	# el diálogo de edición necesita los datos en JS; `frappe.as_json` no está
	# disponible dentro del sandbox de Jinja, así que se serializa aquí
	context.competidores_json = frappe.as_json(visibles).replace("</", "<\\/")
	context.total = len(todos)
	context.mostrados = len(visibles)
	context.categorias = listar_categorias()
	context.prioridades = list(PRIORIDADES)
	try:
		context.csrf_token = frappe.local.session.data.csrf_token
	except Exception:
		context.csrf_token = ""


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
	"""'Sincronizado hace 13 h' / 'hace 2 d'."""
	if not cuando:
		return "Sin sincronizar"
	if isinstance(cuando, str):
		cuando = get_datetime(cuando)
	minutos = int((datetime.now() - cuando).total_seconds() // 60)
	if minutos < 60:
		return f"Sincronizado hace {max(minutos, 1)} min"
	if minutos < 60 * 24:
		return f"Sincronizado hace {minutos // 60} h"
	return f"Sincronizado hace {minutos // (60 * 24)} d"


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
