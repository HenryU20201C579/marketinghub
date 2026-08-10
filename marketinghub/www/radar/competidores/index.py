"""Página de gestión de Competidores."""
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
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/competidores"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Competidores · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)


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
