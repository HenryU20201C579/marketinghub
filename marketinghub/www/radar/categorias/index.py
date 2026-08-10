"""Página de gestión de Categorías Competencia."""
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
