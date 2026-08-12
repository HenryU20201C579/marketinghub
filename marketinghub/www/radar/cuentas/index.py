"""Página de gestión de Cuentas Sociales.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`); `styles.css` y `app.js` son copia literal del
diseño. `get_context` solo arma los datos que pinta ese markup; el alta, la
edición, el borrado y el scrape siguen pasando por los endpoints de abajo.
"""
from datetime import datetime

from frappe.utils import get_datetime

import frappe
from marketinghub.marketinghub.doctype.cuenta_social.cuenta_social import extraer_handle

no_cache = 1

# el diseño colorea Instagram y TikTok; el resto queda en el estilo neutro
CLASE_PLATAFORMA = {"Instagram": "ig", "TikTok": "tt"}

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
	if context.no_access:
		return

	fd = frappe.form_dict
	context.f_q = (fd.get("q") or "").strip()
	context.f_plataforma = fd.get("plataforma") if fd.get("plataforma") in PLATAFORMAS else ""
	context.f_activas = fd.get("activas") == "1"

	todas = listar()
	tope = max([c["n_publicaciones"] for c in todas] + [1])
	for c in todas:
		marca = c.get("competidor") or ""
		handle = (c.get("handle") or "").strip()
		c["handle_txt"] = ("@" + handle.lstrip("@")) if handle else "—"
		c["marca"] = marca
		c["inicial"] = (marca[:2] or "··").upper()
		c["cls"] = CLASE_PLATAFORMA.get(c.get("plataforma"), "")
		c["url_txt"] = _url_corta(c.get("url_perfil"))
		c["url"] = c.get("url_perfil") if (c.get("url_perfil") or "").startswith(("http://", "https://")) else ""
		c["pct"] = round(c["n_publicaciones"] / tope * 100) if c["n_publicaciones"] else 0
		c["scrapeo"] = _hace(c.get("ultimo_scrapeo"))
		c["estado"] = "Activa" if c.get("activo") else "Inactiva"

	visibles = [
		c for c in todas
		if (not context.f_q or context.f_q.lower() in (c["handle_txt"] + " " + c["marca"]).lower())
		and (not context.f_plataforma or c.get("plataforma") == context.f_plataforma)
		and (not context.f_activas or c.get("activo"))
	]

	context.cuentas = visibles
	# el diálogo de edición necesita los datos en JS; `frappe.as_json` no está
	# disponible dentro del sandbox de Jinja, así que se serializa aquí
	context.cuentas_json = frappe.as_json(visibles).replace("</", "<\\/")
	context.total = len(todas)
	context.mostradas = len(visibles)
	context.total_pubs = sum(c["n_publicaciones"] for c in todas)
	context.total_pubs_vis = sum(c["n_publicaciones"] for c in visibles)
	context.activas = sum(1 for c in visibles if c.get("activo"))
	context.por_plataforma = " · ".join(
		f"{sum(1 for c in visibles if c.get('plataforma') == p)} {sigla}"
		for p, sigla in (("Instagram", "IG"), ("TikTok", "TT"))
		if any(c.get("plataforma") == p for c in visibles)
	)
	ultimos = [c.get("ultimo_scrapeo") for c in visibles if c.get("ultimo_scrapeo")]
	context.ultimo_global = _hace(max(ultimos)) if ultimos else "—"
	# solo las plataformas que tienen alguna cuenta, más la filtrada si acaso
	con_cuentas = [p for p in PLATAFORMAS if any(c.get("plataforma") == p for c in todas)]
	if context.f_plataforma and context.f_plataforma not in con_cuentas:
		con_cuentas.append(context.f_plataforma)
	context.plataformas = con_cuentas
	context.plataformas_alta = list(PLATAFORMAS)
	context.competidores = listar_competidores()
	try:
		context.csrf_token = frappe.local.session.data.csrf_token
	except Exception:
		context.csrf_token = ""


def _url_corta(url):
	"""https://www.instagram.com/apolusso.pe/ -> instagram.com/apolusso.pe"""
	if not url:
		return "—"
	corta = url.split("://", 1)[-1]
	if corta.startswith("www."):
		corta = corta[4:]
	return corta.rstrip("/")


def _hace(cuando):
	"""'hace 7 h' / 'hace 2 d', como en el diseño."""
	if not cuando:
		return "—"
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
	cuentas = frappe.db.get_all(
		"Cuenta Social",
		fields=["name", "competidor", "plataforma", "handle", "url_perfil", "activo"],
		order_by="competidor asc, plataforma asc",
	)
	# Agregar contador de publicaciones y último scrapeo por cuenta
	for c in cuentas:
		c["n_publicaciones"] = frappe.db.count(
			"Publicacion Competencia", {"cuenta_social": c["name"]}
		)
		ultima = frappe.db.sql(
			"SELECT MAX(fecha_ultimo_scrapeo) FROM `tabPublicacion Competencia` "
			"WHERE cuenta_social = %s",
			(c["name"],),
		)
		c["ultimo_scrapeo"] = str(ultima[0][0]) if ultima and ultima[0][0] else None
	return cuentas


@frappe.whitelist()
def scrapear_ahora(cuenta_social=None):
	"""Dispara un scrape solo de esta cuenta (background job).

	Reusa la lógica del scraper principal pero filtrando a UNA cuenta.
	Se implementa via correr_scrape con filtro (por ahora corre todas)."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & {"Marketinghub-Radar-Administrar",
	                 "Marketinghub-Radar-Analista", "System Manager"}):
		frappe.throw("Permiso denegado", frappe.PermissionError)
	if not cuenta_social:
		frappe.throw("cuenta_social requerido")
	if not frappe.db.exists("Cuenta Social", cuenta_social):
		frappe.throw(f"Cuenta {cuenta_social!r} no existe")
	# encolar
	frappe.enqueue(
		"marketinghub.api.radar_scraper.correr_scrape",
		queue="long", timeout=600,
	)
	return {"ok": True, "mensaje": f"Scrape encolado. Verifica en unos minutos."}


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
