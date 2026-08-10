"""API endpoints para ingesta de datos scrapeados al Radar de Competencia.

Estos endpoints son consumidos por el orquestador `scripts/radar/monitor.py`,
que corre en un cron y usa Apify como fuente de scrapping.
"""
from __future__ import annotations

import frappe
from frappe.utils import getdate, get_datetime, cint, flt

# Roles permitidos para hacer ingest
INGEST_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")


def _require_ingest_perm():
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado para ingestar datos del scraper.",
		             frappe.PermissionError)


# ============================================================
# CUENTAS activas (lo consulta el orquestador para saber que scrapear)
# ============================================================
@frappe.whitelist()
def listar_cuentas_activas():
	"""Devuelve las Cuenta Social con activo=1 para que el scraper las procese."""
	_require_ingest_perm()
	return frappe.db.get_all(
		"Cuenta Social",
		filters={"activo": 1},
		fields=["name", "competidor", "plataforma", "handle", "url_perfil"],
	)


@frappe.whitelist()
def obtener_apify_token():
	"""Devuelve el token de Apify guardado en Radar Settings (decrypted)."""
	_require_ingest_perm()
	from frappe.utils.password import get_decrypted_password
	return get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")


# ============================================================
# UPSERT de publicaciones (evita duplicados por url_publicacion)
# ============================================================
@frappe.whitelist()
def upsert_publicacion(
	cuenta_social=None,
	url_publicacion=None,
	id_externo=None,
	fecha_publicacion=None,
	tipo_contenido=None,
	descripcion=None,
	hashtags=None,
	duracion_segundos=None,
	vistas_actual=None,
	likes_actual=None,
	comentarios_actual=None,
	compartidos_actual=None,
	guardados_actual=None,
):
	"""Inserta o actualiza una publicacion. Devuelve dict con name y accion.

	Estrategia:
	  - Buscar por url_publicacion (unique).
	  - Si existe: actualizar solo las metricas (no descripcion/fecha/etc).
	  - Si no existe: crear.
	Los hooks del DocType calculan engagement_pct, score_viralidad, es_viral.
	"""
	_require_ingest_perm()

	if not url_publicacion or not cuenta_social:
		frappe.throw("cuenta_social y url_publicacion son obligatorios.")

	existing_name = frappe.db.get_value(
		"Publicacion Competencia", {"url_publicacion": url_publicacion}, "name"
	)
	if existing_name:
		doc = frappe.get_doc("Publicacion Competencia", existing_name)
		accion = "update"
		# Solo actualizar metricas (los campos "vivos")
		if vistas_actual is not None:      doc.vistas_actual = cint(vistas_actual)
		if likes_actual is not None:       doc.likes_actual = cint(likes_actual)
		if comentarios_actual is not None: doc.comentarios_actual = cint(comentarios_actual)
		if compartidos_actual is not None: doc.compartidos_actual = cint(compartidos_actual)
		if guardados_actual is not None:   doc.guardados_actual = cint(guardados_actual)
	else:
		doc = frappe.new_doc("Publicacion Competencia")
		doc.cuenta_social = cuenta_social
		doc.url_publicacion = url_publicacion
		doc.id_externo = id_externo
		doc.fecha_publicacion = getdate(fecha_publicacion) if fecha_publicacion else None
		doc.tipo_contenido = tipo_contenido
		doc.descripcion = descripcion or ""
		doc.hashtags = hashtags or ""
		doc.duracion_segundos = cint(duracion_segundos) if duracion_segundos else 0
		doc.vistas_actual = cint(vistas_actual or 0)
		doc.likes_actual = cint(likes_actual or 0)
		doc.comentarios_actual = cint(comentarios_actual or 0)
		doc.compartidos_actual = cint(compartidos_actual or 0)
		doc.guardados_actual = cint(guardados_actual or 0)
		accion = "insert"

	doc.save(ignore_permissions=True)

	# Registrar snapshot diario (aunque sea update)
	_registrar_snapshot(doc)

	frappe.db.commit()
	return {"ok": True, "name": doc.name, "accion": accion,
	        "es_viral": bool(doc.es_viral), "engagement_pct": doc.engagement_pct}


def _registrar_snapshot(doc):
	"""Agrega o actualiza el snapshot de metricas de HOY para esta publicacion."""
	from datetime import date
	hoy = date.today()
	# ver si ya existe snapshot de hoy en historico_metricas
	existente = None
	for snap in doc.historico_metricas or []:
		if snap.fecha_snapshot == hoy:
			existente = snap
			break
	if existente:
		existente.vistas = doc.vistas_actual
		existente.likes = doc.likes_actual
		existente.comentarios = doc.comentarios_actual
		existente.compartidos = doc.compartidos_actual
		existente.guardados = doc.guardados_actual
	else:
		doc.append("historico_metricas", {
			"fecha_snapshot": hoy,
			"vistas": doc.vistas_actual,
			"likes": doc.likes_actual,
			"comentarios": doc.comentarios_actual,
			"compartidos": doc.compartidos_actual,
			"guardados": doc.guardados_actual,
		})
	doc.save(ignore_permissions=True)


# ============================================================
# SNAPSHOT DE SEGUIDORES por cuenta
# ============================================================
@frappe.whitelist()
def registrar_seguidores(cuenta_social=None, seguidores=None):
	"""Agrega o actualiza el snapshot de seguidores de HOY para la cuenta."""
	_require_ingest_perm()
	if not cuenta_social or seguidores is None:
		frappe.throw("cuenta_social y seguidores son obligatorios.")

	from datetime import date
	hoy = date.today()
	cuenta = frappe.get_doc("Cuenta Social", cuenta_social)

	existente = None
	for snap in cuenta.historico_seguidores or []:
		if snap.fecha == hoy:
			existente = snap
			break
	seguidores = cint(seguidores)
	if existente:
		existente.seguidores = seguidores
	else:
		cuenta.append("historico_seguidores", {
			"fecha": hoy,
			"seguidores": seguidores,
		})
	cuenta.save(ignore_permissions=True)
	# Refrescar metricas calculadas de la cuenta
	cuenta.refrescar_metricas()
	frappe.db.commit()
	return {"ok": True, "seguidores_actual": cuenta.seguidores_actual}
