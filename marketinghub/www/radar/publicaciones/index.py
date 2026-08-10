"""Página del feed de Publicaciones Competencia."""
import frappe

no_cache = 1

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


@frappe.whitelist()
def listar(competidor=None, plataforma=None, estado=None, solo_virales=None, limite=None):
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	filters = {}
	if competidor:
		filters["competidor"] = competidor
	if plataforma:
		filters["plataforma"] = plataforma
	if estado:
		filters["estado"] = estado
	if solo_virales and str(solo_virales) in ("1", "true", "True"):
		filters["es_viral"] = 1

	limite = int(limite or 50)
	pubs = frappe.db.get_all(
		"Publicacion Competencia",
		filters=filters,
		fields=[
			"name", "cuenta_social", "competidor", "plataforma",
			"url_publicacion", "fecha_publicacion", "tipo_contenido",
			"titulo_hook", "descripcion",
			"vistas_actual", "likes_actual", "comentarios_actual",
			"compartidos_actual", "guardados_actual",
			"engagement_pct", "score_viralidad", "es_viral",
			"motivo_viralidad", "formato", "estado",
			"notas_analisis", "elementos_a_copiar",
		],
		order_by="fecha_publicacion desc, modified desc",
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
	return {
		"competidores": competidores,
		"plataformas": ["Instagram", "TikTok", "Facebook", "YouTube"],
		"estados": list(ESTADOS),
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
