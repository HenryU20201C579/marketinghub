"""Página de gestión de Categorías Competencia.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`) y `categorias.css` es copia literal del CSS del
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


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/categorias"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Categorías · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)
	if context.no_access:
		return

	fd = frappe.form_dict
	context.f_q = (fd.get("q") or "").strip()
	context.f_uso = fd.get("uso") == "1"
	context.f_orden = "az" if fd.get("orden") == "az" else "pubs"
	context.hay_filtros = bool(context.f_q or context.f_uso or fd.get("orden"))

	todas = listar()
	pubs = _publicaciones_30d()
	marcas = _competidores_por_categoria()
	fechas = {c.name: c.modified for c in frappe.db.get_all(
		"Categoria Competencia", fields=["name", "modified"])}
	tope = max(list(pubs.values()) + [1])

	for c in todas:
		nombre = c.get("nombre_categoria") or c["name"]
		n = pubs.get(c["name"], 0)
		usada = bool(c.get("competidores"))
		c["titulo"] = nombre
		c["usada"] = usada
		c["ico_cls"] = "" if usada else " cat-ico--empty"
		c["pill_cls"] = "" if usada else " cat-pill--empty"
		c["pill_label"] = "Activa" if usada else "Vacía"
		c["sub"] = (f"{c['competidores']} competidor"
		            f"{'es' if c['competidores'] != 1 else ''}") if usada else "Sin usar"
		c["pubs"] = n
		c["pubs_pct"] = round(n / tope * 100) if n else 3
		c["marcas"] = marcas.get(c["name"], [])
		c["upd"] = _hace(fechas.get(c["name"]))

	visibles = [
		c for c in todas
		if (not context.f_q or context.f_q.lower() in c["titulo"].lower())
		and (not context.f_uso or c["usada"])
	]
	if context.f_orden == "az":
		visibles.sort(key=lambda c: c["titulo"].lower())
	else:
		visibles.sort(key=lambda c: (-c["pubs"], c["titulo"].lower()))

	context.categorias = visibles
	# el diálogo de edición necesita los datos en JS; `frappe.as_json` no está
	# disponible dentro del sandbox de Jinja, así que se serializa aquí
	context.categorias_json = frappe.as_json(visibles).replace("</", "<\\/")
	context.total = len(todas)
	context.mostradas = len(visibles)
	context.sin_competidores = sum(1 for c in todas if not c["usada"])
	try:
		context.csrf_token = frappe.local.session.data.csrf_token
	except Exception:
		context.csrf_token = ""


def _publicaciones_30d():
	desde = date.today() - timedelta(days=30)
	rows = frappe.db.sql("""
		SELECT comp.categoria AS categoria, COUNT(*) AS n
		FROM `tabPublicacion Competencia` p
		JOIN `tabCompetidor` comp ON comp.name = p.competidor
		WHERE p.fecha_publicacion >= %s AND comp.categoria IS NOT NULL
		GROUP BY comp.categoria
	""", (desde,), as_dict=True)
	return {r.categoria: int(r.n) for r in rows}


def _competidores_por_categoria():
	out = {}
	for c in frappe.db.get_all(
		"Competidor", filters={"categoria": ["is", "set"]},
		fields=["name", "categoria"], order_by="name asc",
	):
		out.setdefault(c.categoria, []).append(c.name)
	return out


def _hace(cuando):
	"""'Actualizada hace 13 h' / 'hace 2 d'."""
	if not cuando:
		return ""
	if isinstance(cuando, str):
		cuando = get_datetime(cuando)
	minutos = int((datetime.now() - cuando).total_seconds() // 60)
	if minutos < 60:
		return f"Actualizada hace {max(minutos, 1)} min"
	if minutos < 60 * 24:
		return f"Actualizada hace {minutos // 60} h"
	return f"Actualizada hace {minutos // (60 * 24)} d"


@frappe.whitelist()
def listar():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	cats = frappe.db.get_all(
		"Categoria Competencia",
		fields=["name", "nombre_categoria", "descripcion"],
		order_by="nombre_categoria asc",
	)
	# contar competidores por categoria
	for c in cats:
		c["competidores"] = frappe.db.count("Competidor", filters={"categoria": c["name"]})
	return cats


@frappe.whitelist()
def guardar(name=None, nombre_categoria=None, descripcion=None):
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede modificar categorías.", frappe.PermissionError)
	if not nombre_categoria:
		frappe.throw("El nombre de la categoría es obligatorio.")
	if name:
		doc = frappe.get_doc("Categoria Competencia", name)
		doc.nombre_categoria = nombre_categoria
		doc.descripcion = descripcion or ""
		doc.save(ignore_permissions=True)
	else:
		if frappe.db.exists("Categoria Competencia", nombre_categoria):
			frappe.throw(f"Ya existe una categoría llamada '{nombre_categoria}'.")
		doc = frappe.new_doc("Categoria Competencia")
		doc.nombre_categoria = nombre_categoria
		doc.descripcion = descripcion or ""
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "name": doc.name}


@frappe.whitelist()
def borrar(name=None):
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede borrar.", frappe.PermissionError)
	usos = frappe.db.count("Competidor", filters={"categoria": name})
	if usos:
		frappe.throw(
			f"No puedes borrar esta categoría: hay {usos} competidor(es) que la usan."
		)
	frappe.delete_doc("Categoria Competencia", name, ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
