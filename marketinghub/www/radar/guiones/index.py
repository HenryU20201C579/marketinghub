"""Página lista de Guiones — estilo Google Tasks."""
import frappe
from frappe.utils import getdate, today, add_days

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
ANALISTA_ROLES = ("Marketinghub-Radar-Analista",) + ADMIN_ROLES
VIEW_ROLES = ("Marketinghub-Radar-Ver",) + ANALISTA_ROLES

ESTADOS = ("Idea", "Guión", "Grabar", "Editar", "Publicado")


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/guiones"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Guiones · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ANALISTA_ROLES)
	context.usuario = frappe.session.user
	context.estados = list(ESTADOS)


@frappe.whitelist()
def listar(estado=None, competidor=None, plataforma=None, asignado_a=None):
	"""Trae todos los guiones agrupados en el frontend."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	filters = {}
	if estado:
		filters["estado"] = estado
	if competidor:
		filters["competidor_ref"] = competidor
	if plataforma:
		filters["plataforma"] = plataforma
	if asignado_a:
		filters["asignado_a"] = asignado_a

	guiones = frappe.db.get_all(
		"Guion",
		filters=filters,
		fields=[
			"name", "titulo", "estado", "fecha_publicacion", "hora_publicacion",
			"plataforma", "asignado_a", "referencia_publicacion", "competidor_ref",
			"check_guion", "check_storyboard", "check_materiales",
			"check_grabado", "check_editado", "check_publicado",
			"mi_vistas", "ratio_vs_referente", "modified",
		],
		order_by="fecha_publicacion asc, modified desc",
		limit=500,
	)
	# Enriquecer con datos del referente (para pill "Ref: Apolusso 207k")
	refs = {}
	ref_names = list({g.referencia_publicacion for g in guiones if g.referencia_publicacion})
	if ref_names:
		for r in frappe.db.get_all(
			"Publicacion Competencia",
			filters={"name": ["in", ref_names]},
			fields=["name", "competidor", "vistas_actual", "titulo_hook", "tier"],
		):
			refs[r.name] = r
	# Color por competidor
	colores = {}
	if guiones:
		comps = list({g.competidor_ref for g in guiones if g.competidor_ref})
		if comps:
			for c in frappe.db.get_all(
				"Competidor", filters={"name": ["in", comps]},
				fields=["name", "color"],
			):
				colores[c.name] = c.color or "#94a3b8"

	for g in guiones:
		r = refs.get(g.referencia_publicacion) if g.referencia_publicacion else None
		if r:
			g["ref_competidor"] = r.competidor
			g["ref_vistas"] = r.vistas_actual
			g["ref_titulo"] = r.titulo_hook
			g["ref_tier"] = r.tier
		g["color_competidor"] = colores.get(g.competidor_ref, "#94a3b8")

	return guiones


@frappe.whitelist()
def contadores():
	"""Contadores para el sidebar de filtros."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	total = frappe.db.count("Guion")
	esta_semana = frappe.db.count(
		"Guion",
		filters={
			"fecha_publicacion": ["between", [today(), add_days(today(), 6)]],
		},
	)
	mios = frappe.db.count("Guion", filters={"asignado_a": frappe.session.user})
	por_estado = {}
	for e in ESTADOS:
		por_estado[e] = frappe.db.count("Guion", filters={"estado": e})
	return {
		"total": total,
		"esta_semana": esta_semana,
		"mios": mios,
		"por_estado": por_estado,
	}


@frappe.whitelist()
def crear_desde_publicacion(publicacion_name):
	"""Crea un guion nuevo prellenado con la referencia."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede crear guiones.", frappe.PermissionError)
	pub = frappe.db.get_value(
		"Publicacion Competencia", publicacion_name,
		["competidor", "titulo_hook", "plataforma"], as_dict=True,
	)
	if not pub:
		frappe.throw("Publicación no encontrada.")
	titulo = f"Adaptación: {pub.titulo_hook or publicacion_name}"[:140]
	doc = frappe.get_doc({
		"doctype": "Guion",
		"titulo": titulo,
		"estado": "Idea",
		"referencia_publicacion": publicacion_name,
		"competidor_ref": pub.competidor,
		"plataforma": pub.plataforma if pub.plataforma in (
			"Instagram", "TikTok", "Facebook", "YouTube",
		) else None,
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()
	return {"name": doc.name, "url": f"/radar/guion?name={doc.name}"}


@frappe.whitelist()
def toggle_check(name, campo, valor):
	"""Marca/desmarca un check del checklist. Devuelve el estado actualizado."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede editar guiones.", frappe.PermissionError)
	campos_validos = {
		"check_guion", "check_storyboard", "check_materiales",
		"check_grabado", "check_editado", "check_publicado",
	}
	if campo not in campos_validos:
		frappe.throw("Campo inválido.")
	doc = frappe.get_doc("Guion", name)
	setattr(doc, campo, 1 if str(valor) in ("1", "true", "True") else 0)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "estado": doc.estado}


@frappe.whitelist()
def eliminar(name):
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede eliminar guiones.", frappe.PermissionError)
	frappe.delete_doc("Guion", name, ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
