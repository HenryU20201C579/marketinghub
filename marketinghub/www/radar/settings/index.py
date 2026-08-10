"""Página de configuración del Radar."""
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
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/settings"
		raise frappe.Redirect

	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Configuración · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)


@frappe.whitelist()
def obtener_settings():
	"""Retorna los valores actuales de Radar Settings + tabla de tiers."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	s = frappe.get_doc("Radar Settings")
	tiers = []
	for t in sorted(s.tiers_viralidad or [], key=lambda x: x.orden):
		tiers.append({
			"orden": t.orden,
			"nombre": t.nombre,
			"imagen_url": t.imagen_url,
			"vistas_min": t.vistas_min,
			"engagement_min": t.engagement_min,
			"es_viral": int(t.es_viral or 0),
			"color_hex": t.color_hex,
		})
	return {
		"dias_retencion_snapshots": s.dias_retencion_snapshots or 90,
		"canal_alerta": s.canal_alerta or "In-app ERP",
		"preset_frecuencia": s.preset_frecuencia or "Diario a las 6 AM",
		"cron_scrape": s.cron_scrape or "0 6 * * *",
		"posts_por_perfil_ig": s.posts_por_perfil_ig or 20,
		"posts_por_perfil_tiktok": s.posts_por_perfil_tiktok or 20,
		"tiers": tiers,
	}


@frappe.whitelist()
def guardar_settings(
	dias_retencion_snapshots=None,
	canal_alerta=None,
	preset_frecuencia=None,
	cron_scrape=None,
	posts_por_perfil_ig=None,
	posts_por_perfil_tiktok=None,
	tiers=None,
):
	"""Guarda los valores de Radar Settings. tiers = JSON string con la tabla."""
	import json as _json
	if not _has_role(ADMIN_ROLES):
		frappe.throw(
			"Solo un administrador puede modificar la configuración.",
			frappe.PermissionError,
		)
	s = frappe.get_single("Radar Settings")
	if dias_retencion_snapshots is not None: s.dias_retencion_snapshots = int(dias_retencion_snapshots)
	if canal_alerta is not None:          s.canal_alerta = canal_alerta
	if preset_frecuencia is not None:     s.preset_frecuencia = preset_frecuencia
	if cron_scrape is not None:           s.cron_scrape = cron_scrape.strip()
	if posts_por_perfil_ig is not None:   s.posts_por_perfil_ig = int(posts_por_perfil_ig)
	if posts_por_perfil_tiktok is not None: s.posts_por_perfil_tiktok = int(posts_por_perfil_tiktok)

	if tiers is not None:
		try:
			tiers_data = _json.loads(tiers) if isinstance(tiers, str) else tiers
		except Exception:
			frappe.throw("Los tiers deben ser un JSON válido.")
		s.tiers_viralidad = []
		for t in tiers_data:
			s.append("tiers_viralidad", {
				"orden": int(t.get("orden") or 0),
				"nombre": t.get("nombre") or "",
				"imagen_url": t.get("imagen_url") or "",
				"vistas_min": int(t.get("vistas_min") or 0),
				"engagement_min": float(t.get("engagement_min") or 0),
				"es_viral": 1 if t.get("es_viral") else 0,
				"color_hex": t.get("color_hex") or "#94a3b8",
			})

	s.save(ignore_permissions=True)
	frappe.db.commit()
	return {"ok": True}
