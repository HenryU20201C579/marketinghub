"""Página de gestión de Cuentas Sociales."""
import frappe
from marketinghub.marketinghub.doctype.cuenta_social.cuenta_social import extraer_handle

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)
PLATAFORMAS = ("Instagram", "TikTok", "Facebook", "YouTube")


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/cuentas"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Cuentas Sociales · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)


@frappe.whitelist()
def listar():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	cuentas = frappe.db.get_all(
		"Cuenta Social",
		fields=["name", "competidor", "plataforma", "handle", "url_perfil",
		        "seguidores_actual", "engagement_promedio", "activo"],
		order_by="competidor asc, plataforma asc",
	)
	return cuentas


@frappe.whitelist()
def listar_competidores():
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	return [c["name"] for c in frappe.db.get_all(
		"Competidor",
		filters={"activo": 1},
		fields=["name"],
		order_by="nombre_comercial asc",
	)]


@frappe.whitelist()
def validar_url(url=None, plataforma=None):
	"""Valida la URL y devuelve el handle que se derivaría."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	handle = extraer_handle(url or "", plataforma or "")
	return {"handle": handle, "valida": bool(handle)}


@frappe.whitelist()
def guardar(name=None, competidor=None, plataforma=None,
            url_perfil=None, activo=None):
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede modificar.", frappe.PermissionError)
	if not competidor:
		frappe.throw("El competidor es obligatorio.")
	if plataforma not in PLATAFORMAS:
		frappe.throw(f"Plataforma inválida. Usa una de: {', '.join(PLATAFORMAS)}")
	if not url_perfil:
		frappe.throw("La URL del perfil es obligatoria.")

	values = {
		"competidor": competidor,
		"plataforma": plataforma,
		"url_perfil": url_perfil,
		"activo": int(activo) if activo not in (None, "") else 1,
	}
	if name:
		doc = frappe.get_doc("Cuenta Social", name)
		for k, v in values.items():
			setattr(doc, k, v)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.new_doc("Cuenta Social")
		for k, v in values.items():
			setattr(doc, k, v)
		doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "name": doc.name, "handle": doc.handle}


@frappe.whitelist()
def borrar(name=None):
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede borrar.", frappe.PermissionError)
	usos = frappe.db.count("Publicacion Competencia", filters={"cuenta_social": name})
	if usos:
		frappe.throw(
			f"No puedes borrar: hay {usos} publicación(es) asociadas. "
			"Puedes desactivar la cuenta desmarcando 'Activo'."
		)
	frappe.delete_doc("Cuenta Social", name, ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
