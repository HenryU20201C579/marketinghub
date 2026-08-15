"""Página de gestión de Cuentas Sociales.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`); `styles.css` y `app.js` son copia literal del
diseño. `get_context` solo arma los datos que pinta ese markup; el alta, la
edición, el borrado y el scrape siguen pasando por los endpoints de abajo.
"""
import re
from datetime import datetime

from frappe.utils import get_datetime

import frappe
from marketinghub.marketinghub.doctype.cuenta_social.cuenta_social import extraer_handle

no_cache = 1

# el diseño colorea Instagram y TikTok; el resto queda en el estilo neutro
CLASE_PLATAFORMA = {"Instagram": "ig", "TikTok": "tt"}
# siglas para la cabecera de marca, donde no cabe el nombre completo
SIGLA = {"Instagram": "IG", "TikTok": "TT", "Facebook": "FB", "YouTube": "YT"}

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)
PLATAFORMAS = ("Instagram", "TikTok", "Facebook", "YouTube")

# Dominio -> plataforma, para deducir la red al pegar una URL en el alta rápida.
DOMINIOS = (
	("instagram.com", "Instagram"),
	("tiktok.com", "TikTok"),
	("facebook.com", "Facebook"),
	("fb.com", "Facebook"),
	("youtube.com", "YouTube"),
	("youtu.be", "YouTube"),
)


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
	context.grupos = _agrupar_por_marca(visibles)
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


def _agrupar_por_marca(cuentas):
	"""Una entrada por marca con sus perfiles dentro y los totales de la fila
	cabecera. `cuentas` ya viene ordenada por competidor (ver `listar`).

	Nada de llamar `grupo.cuentas` «items» ni «values»: en Jinja esas claves
	las tapa el método homónimo del dict y la fila saldría vacía."""
	grupos = []
	for c in cuentas:
		if not grupos or grupos[-1]["marca"] != c["marca"]:
			grupos.append({"marca": c["marca"], "inicial": c["inicial"], "cuentas": []})
		grupos[-1]["cuentas"].append(c)

	tope = max([sum(x["n_publicaciones"] for x in g["cuentas"]) for g in grupos] + [1])
	for g in grupos:
		perfiles = g["cuentas"]
		g["n_perfiles"] = len(perfiles)
		g["n_pubs"] = sum(x["n_publicaciones"] for x in perfiles)
		g["pct"] = round(g["n_pubs"] / tope * 100) if g["n_pubs"] else 0
		g["activas"] = sum(1 for x in perfiles if x.get("activo"))
		g["redes"] = [
			{"plataforma": p, "cls": CLASE_PLATAFORMA.get(p, ""), "sigla": SIGLA[p],
			 "n": sum(1 for x in perfiles if x.get("plataforma") == p)}
			for p in PLATAFORMAS if any(x.get("plataforma") == p for x in perfiles)
		]
		ultimos = [x.get("ultimo_scrapeo") for x in perfiles if x.get("ultimo_scrapeo")]
		g["scrapeo"] = _hace(max(ultimos)) if ultimos else "—"
	return grupos


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


def detectar_plataforma(url):
	"""Deduce la red social a partir del dominio. None si no la reconoce."""
	u = (url or "").strip().lower()
	for dominio, plataforma in DOMINIOS:
		if dominio in u:
			return plataforma
	return None


def _normalizar_url(cruda):
	"""Limpia lo que se pega desde el móvil: comillas, scheme ausente, tracking.

	El `?igsh=…` de los enlaces compartidos se descarta, salvo en los perfiles
	de Facebook tipo `profile.php?id=…`, donde el query ES el identificador."""
	url = (cruda or "").strip().strip('"\'<>')
	if not url:
		return ""
	if not url.lower().startswith(("http://", "https://")):
		url = "https://" + url.lstrip("/")
	if "?" in url and "profile.php" not in url.lower():
		url = url.split("?", 1)[0]
	return url


def _partir_urls(urls):
	"""Acepta el textarea completo: una URL por línea, o separadas por coma."""
	if isinstance(urls, (list, tuple)):
		crudas = urls
	else:
		crudas = re.split(r"[\s,]+", urls or "")
	vistas, limpias = set(), []
	for c in crudas:
		c = (c or "").strip()
		if c and c.lower() not in vistas:
			vistas.add(c.lower())
			limpias.append(c)
	return limpias


def _asegurar_competidor(nombre):
	"""Devuelve el name del Competidor, creándolo si aún no existe."""
	nombre = (nombre or "").strip()
	if not nombre:
		frappe.throw("El nombre de la marca no puede estar vacío.")
	# la colación de MariaDB no distingue mayúsculas: «boboluv» reusa «Boboluv»
	existente = frappe.db.get_value("Competidor", {"name": nombre}, "name")
	if existente:
		return existente
	doc = frappe.new_doc("Competidor")
	doc.nombre_comercial = nombre
	doc.activo = 1
	doc.insert(ignore_permissions=True)
	return doc.name


@frappe.whitelist()
def guardar_lote(competidor=None, nueva_marca=None, urls=None, activo=1):
	"""Alta rápida: una marca + N URLs de perfil, la red se deduce del dominio.

	Cada URL se inserta dentro de su propio savepoint, así una que falle no
	tumba a las demás. Devuelve el detalle para que el diálogo deje en el
	textarea solo las que quedaron pendientes."""
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede modificar.", frappe.PermissionError)

	nueva_marca = (nueva_marca or "").strip()
	competidor = (competidor or "").strip()
	marca_creada = False
	if nueva_marca:
		marca_creada = not frappe.db.get_value("Competidor", {"name": nueva_marca}, "name")
		competidor = _asegurar_competidor(nueva_marca)
	if not competidor:
		frappe.throw("Elige una marca o escribe el nombre de una nueva.")
	if not frappe.db.exists("Competidor", competidor):
		frappe.throw(f"La marca {competidor!r} no existe.")

	pendientes = _partir_urls(urls)
	if not pendientes:
		frappe.throw("Pega al menos una URL de perfil.")

	activo = int(activo) if activo not in (None, "") else 1
	creadas, omitidas, errores = [], [], []

	for i, cruda in enumerate(pendientes):
		url = _normalizar_url(cruda)
		plataforma = detectar_plataforma(url)
		if not plataforma:
			errores.append({"url": cruda, "motivo": "No reconozco la red social de esa URL."})
			continue
		handle = extraer_handle(url, plataforma)
		if not handle:
			errores.append({"url": cruda,
			                "motivo": f"No pude extraer el handle de esa URL de {plataforma}."})
			continue

		# Un handle es único dentro de su red, así que el perfil no puede estar
		# en dos marcas. Se busca por (plataforma, handle) y NO por el name:
		# las cuentas creadas antes del patch de autoname tienen name tipo hash
		# y un lookup por name las pasaría por alto, duplicando el perfil.
		ya = frappe.db.get_value(
			"Cuenta Social",
			{"plataforma": plataforma, "handle": handle},
			["name", "competidor"],
			as_dict=True,
		)
		if ya:
			if ya.competidor == competidor:
				omitidas.append({"url": cruda, "plataforma": plataforma, "handle": handle})
			else:
				errores.append({"url": cruda,
				                "motivo": f"Ese perfil ya está registrado en la marca «{ya.competidor}»."})
			continue

		punto = f"alta_cuenta_{i}"
		frappe.db.savepoint(punto)
		try:
			doc = frappe.new_doc("Cuenta Social")
			doc.competidor = competidor
			doc.plataforma = plataforma
			doc.url_perfil = url
			doc.activo = activo
			doc.insert(ignore_permissions=True)
			creadas.append({"name": doc.name, "plataforma": plataforma, "handle": doc.handle})
		except Exception as e:
			frappe.db.rollback(save_point=punto)
			errores.append({"url": cruda,
			                "motivo": frappe.utils.strip_html(str(e)) or "No se pudo crear."})

	frappe.db.commit()
	return {
		"competidor": competidor,
		"marca_creada": marca_creada,
		"creadas": creadas,
		"omitidas": omitidas,
		"errores": errores,
	}


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
