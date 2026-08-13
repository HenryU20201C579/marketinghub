"""Editor detallado de un guion (?name=GUI-...)."""
import frappe

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
ANALISTA_ROLES = ("Marketinghub-Radar-Analista",) + ADMIN_ROLES
VIEW_ROLES = ("Marketinghub-Radar-Ver",) + ANALISTA_ROLES


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar"
		raise frappe.Redirect
	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Guión · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ANALISTA_ROLES)
	context.usuario = frappe.session.user


@frappe.whitelist()
def obtener(name):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	doc = frappe.get_doc("Guion", name).as_dict()
	# Traer datos de la referencia si existe
	if doc.get("referencia_publicacion"):
		ref = frappe.db.get_value(
			"Publicacion Competencia", doc.referencia_publicacion,
			[
				"name", "competidor", "plataforma", "url_publicacion",
				"fecha_publicacion", "titulo_hook", "descripcion",
				"vistas_actual", "likes_actual", "comentarios_actual",
				"compartidos_actual", "guardados_actual",
				"engagement_pct", "tier", "notas_analisis", "elementos_a_copiar",
			], as_dict=True,
		)
		doc["_ref"] = ref
	# lista de usuarios asignables (Analistas y Administradores del Radar)
	usuarios = frappe.db.sql(
		"""
		SELECT DISTINCT u.name, u.full_name
		FROM `tabUser` u
		INNER JOIN `tabHas Role` hr ON hr.parent = u.name
		WHERE u.enabled = 1
		  AND hr.role IN ('Marketinghub-Radar-Analista', 'Marketinghub-Radar-Administrar')
		ORDER BY u.full_name
		""",
		as_dict=True,
	)
	doc["_usuarios"] = usuarios
	return doc


@frappe.whitelist()
def guardar(name, cambios):
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede editar guiones.", frappe.PermissionError)
	if isinstance(cambios, str):
		import json
		cambios = json.loads(cambios)
	doc = frappe.get_doc("Guion", name)
	# whitelist de campos editables desde la UI
	editables = {
		"titulo", "estado", "fecha_publicacion", "hora_publicacion",
		"plataforma", "asignado_a", "duracion_objetivo",
		"guion_texto",
		"hook", "setup", "producto", "prueba", "cta", "notas_edicion",
		"check_guion", "check_storyboard", "check_materiales",
		"check_grabado", "check_editado", "check_publicado",
		"mi_url_publicacion", "mi_vistas", "mi_likes",
	}
	for k, v in cambios.items():
		if k in editables:
			setattr(doc, k, v)
	doc.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True, "estado": doc.estado, "ratio_vs_referente": doc.ratio_vs_referente}


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
def eliminar(name):
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede eliminar guiones.", frappe.PermissionError)
	frappe.delete_doc("Guion", name, ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
