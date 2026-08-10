"""API endpoints para ingesta de datos scrapeados al Radar de Competencia.

Se usa desde dos lados:
  - Como scheduled job de Frappe (funcion correr_scrape) — el flujo normal.
  - Como endpoints whitelisted para debug/scripts externos.
"""
from __future__ import annotations

import json
import time
import traceback
from collections import defaultdict

import frappe
from frappe.utils import getdate, get_datetime, cint, now_datetime

from marketinghub.api import apify_actor

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
# CORRIDA COMPLETA — scheduled job y trigger manual
# ============================================================
def _map_instagram(item):
	tipo_map = {"Image": "Post", "Sidecar": "Carrusel", "Video": "Reel"}
	tipo = tipo_map.get(item.get("type"), "Post")
	if item.get("productType") == "clips":
		tipo = "Reel"
	return {
		"url_publicacion": item.get("url"),
		"id_externo": item.get("shortCode"),
		"fecha_publicacion": (item.get("timestamp") or "")[:10] or None,
		"tipo_contenido": tipo,
		"descripcion": (item.get("caption") or "").strip(),
		"hashtags": " ".join(f"#{h}" for h in (item.get("hashtags") or [])),
		"duracion_segundos": int(item.get("videoDuration") or 0),
		"vistas_actual": item.get("videoPlayCount") or item.get("videoViewCount") or 0,
		"likes_actual": item.get("likesCount") or 0,
		"comentarios_actual": item.get("commentsCount") or 0,
		"compartidos_actual": 0,
		"guardados_actual": 0,
		"_owner_username": (item.get("ownerUsername") or "").lower(),
		"_input_url": (item.get("inputUrl") or "").rstrip("/"),
	}


def _map_tiktok(item):
	author = item.get("authorMeta") or {}
	hashtags = " ".join(
		f"#{h.get('name', '')}" for h in (item.get("hashtags") or [])
		if isinstance(h, dict)
	)
	return {
		"url_publicacion": item.get("webVideoUrl"),
		"id_externo": str(item.get("id") or ""),
		"fecha_publicacion": (item.get("createTimeISO") or "")[:10] or None,
		"tipo_contenido": "Video",
		"descripcion": (item.get("text") or "").strip(),
		"hashtags": hashtags,
		"duracion_segundos": int(item.get("videoMeta", {}).get("duration") or 0),
		"vistas_actual": item.get("playCount") or 0,
		"likes_actual": item.get("diggCount") or 0,
		"comentarios_actual": item.get("commentCount") or 0,
		"compartidos_actual": item.get("shareCount") or 0,
		"guardados_actual": item.get("collectCount") or 0,
		"_owner_username": (author.get("name") or "").lower().lstrip("@"),
		"_seguidores": author.get("fans"),
	}


def correr_scrape(limit_per_profile=20):
	"""Se invoca desde el scheduled job o manualmente. NO usa HTTP — corre in-process."""
	from frappe.utils.password import get_decrypted_password

	inicio = time.time()
	stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}
	log_lines = []

	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		msg = "apify_token no configurado en Radar Settings"
		_registrar_corrida(0, stats, "error", msg)
		frappe.log_error(msg, "Radar Scraper")
		return {"ok": False, "error": msg}

	cuentas = frappe.db.get_all(
		"Cuenta Social",
		filters={"activo": 1},
		fields=["name", "competidor", "plataforma", "handle", "url_perfil"],
	)
	if not cuentas:
		_registrar_corrida(0, stats, "ok", "sin cuentas activas")
		return {"ok": True, "mensaje": "sin cuentas activas"}

	por_plataforma = defaultdict(list)
	for c in cuentas:
		por_plataforma[c["plataforma"]].append(c)

	# --- Instagram ---
	if por_plataforma["Instagram"]:
		try:
			cuentas_ig = por_plataforma["Instagram"]
			urls = [c["url_perfil"] for c in cuentas_ig if c.get("url_perfil")]
			items = apify_actor.scrape_instagram(token, urls, limit_per_profile)
			url_to_cuenta = {c["url_perfil"].rstrip("/"): c for c in cuentas_ig}
			handle_to_cuenta = {c["handle"].lower(): c for c in cuentas_ig if c.get("handle")}
			pinned_skip = 0
			for item in items:
				# Los posts anclados (pinned) son viejos con metricas acumuladas
				# y distorsionan el baseline. Se descartan.
				if item.get("isPinned"):
					pinned_skip += 1
					continue
				payload = _map_instagram(item)
				owner = payload.pop("_owner_username")
				input_url = payload.pop("_input_url")
				cuenta = url_to_cuenta.get(input_url) or handle_to_cuenta.get(owner)
				if not cuenta or not payload["url_publicacion"]:
					stats["skip"] += 1
					continue
				payload["cuenta_social"] = cuenta["name"]
				_ejecutar_upsert(payload, stats)
			log_lines.append(f"IG · {len(items)} items ({pinned_skip} anclados descartados)")
		except Exception as e:
			stats["error"] += 1
			log_lines.append(f"IG · ERROR: {e}")
			frappe.log_error(traceback.format_exc(), "Radar Scraper · IG")

	# --- TikTok ---
	if por_plataforma["TikTok"]:
		try:
			cuentas_tt = por_plataforma["TikTok"]
			handles = [c["handle"] for c in cuentas_tt if c.get("handle")]
			items = apify_actor.scrape_tiktok(token, handles, limit_per_profile)
			handle_to_cuenta = {c["handle"].lower(): c for c in cuentas_tt if c.get("handle")}
			pinned_skip = 0
			for item in items:
				if item.get("isPinned"):
					pinned_skip += 1
					continue
				payload = _map_tiktok(item)
				owner_h = payload.pop("_owner_username", "")
				payload.pop("_seguidores", None)
				cuenta = handle_to_cuenta.get(owner_h)
				if not cuenta or not payload["url_publicacion"]:
					stats["skip"] += 1
					continue
				payload["cuenta_social"] = cuenta["name"]
				_ejecutar_upsert(payload, stats)
			log_lines.append(f"TikTok · {len(items)} items ({pinned_skip} anclados descartados)")
		except Exception as e:
			stats["error"] += 1
			log_lines.append(f"TikTok · ERROR: {e}")
			frappe.log_error(traceback.format_exc(), "Radar Scraper · TikTok")

	duracion = round(time.time() - inicio, 1)
	resumen = f"insert={stats['insert']} update={stats['update']} skip={stats['skip']} error={stats['error']}"
	_registrar_corrida(duracion, stats, "ok" if stats["error"] == 0 else "warn",
	                   " · ".join(log_lines) + " · " + resumen)
	frappe.db.commit()
	return {"ok": True, "stats": stats, "duracion_s": duracion}


def _ejecutar_upsert(payload, stats):
	try:
		# upsert inline (no via HTTP)
		url_pub = payload["url_publicacion"]
		existing = frappe.db.get_value(
			"Publicacion Competencia", {"url_publicacion": url_pub}, "name"
		)
		if existing:
			doc = frappe.get_doc("Publicacion Competencia", existing)
			doc.vistas_actual = payload["vistas_actual"]
			doc.likes_actual = payload["likes_actual"]
			doc.comentarios_actual = payload["comentarios_actual"]
			doc.compartidos_actual = payload["compartidos_actual"]
			doc.guardados_actual = payload["guardados_actual"]
			accion = "update"
		else:
			doc = frappe.new_doc("Publicacion Competencia")
			for k, v in payload.items():
				setattr(doc, k, v)
			accion = "insert"
		doc.save(ignore_permissions=True)
		_agregar_snapshot(doc)
		doc.save(ignore_permissions=True)
		stats[accion] += 1
	except Exception as e:
		stats["error"] += 1
		frappe.log_error(f"upsert {payload.get('url_publicacion')}: {e}",
		                 "Radar Scraper · upsert")


def _agregar_snapshot(doc):
	from datetime import date
	hoy = date.today()
	existente = None
	for snap in doc.historico_metricas or []:
		if snap.fecha_snapshot == hoy:
			existente = snap
			break
	campos = dict(vistas=doc.vistas_actual, likes=doc.likes_actual,
	              comentarios=doc.comentarios_actual,
	              compartidos=doc.compartidos_actual,
	              guardados=doc.guardados_actual)
	if existente:
		for k, v in campos.items():
			setattr(existente, k, v)
	else:
		doc.append("historico_metricas", {"fecha_snapshot": hoy, **campos})


def _registrar_corrida(duracion_s, stats, estado, mensaje):
	"""Guarda info de la ultima corrida en Radar Settings."""
	s = frappe.get_single("Radar Settings")
	s.ultima_corrida = now_datetime()
	s.ultima_corrida_estado = estado
	s.ultima_corrida_duracion = duracion_s
	s.ultima_corrida_mensaje = (mensaje or "")[:500]
	s.ultima_corrida_stats = json.dumps(stats)
	# evitamos disparar on_update recursivo:
	s.flags.ignore_scheduler_sync = True
	s.save(ignore_permissions=True)


@frappe.whitelist()
def ejecutar_scrape_ahora(limit=20):
	"""Endpoint para el boton 'Ejecutar ahora' en /radar/settings."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado", frappe.PermissionError)
	# Encolar en background para no bloquear el request
	frappe.enqueue(
		"marketinghub.api.radar_scraper.correr_scrape",
		queue="long",
		timeout=600,
		limit_per_profile=int(limit),
	)
	return {"ok": True, "mensaje": "Scrape encolado. Verifica 'Última corrida' en unos minutos."}


@frappe.whitelist()
def obtener_estado_scheduler():
	"""Estado actual del job programado y ultima corrida."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES) | {"Marketinghub-Radar-Ver", "Marketinghub-Radar-Analista"}):
		frappe.throw("Permiso denegado", frappe.PermissionError)
	s = frappe.get_single("Radar Settings")
	job = None
	if frappe.db.exists("Scheduled Job Type",
	                    {"method": "marketinghub.api.radar_scraper.correr_scrape"}):
		j = frappe.get_doc("Scheduled Job Type",
		                   {"method": "marketinghub.api.radar_scraper.correr_scrape"})
		job = {
			"cron_format": j.cron_format,
			"stopped": bool(j.stopped),
			"last_execution": str(j.last_execution) if j.last_execution else None,
			"next_execution": str(j.get_next_execution()) if hasattr(j, "get_next_execution") else None,
		}
	return {
		"cron_scrape": s.cron_scrape,
		"preset_frecuencia": getattr(s, "preset_frecuencia", None),
		"ultima_corrida": str(s.ultima_corrida) if s.ultima_corrida else None,
		"ultima_corrida_estado": s.ultima_corrida_estado,
		"ultima_corrida_duracion": s.ultima_corrida_duracion,
		"ultima_corrida_mensaje": s.ultima_corrida_mensaje,
		"ultima_corrida_stats": json.loads(s.ultima_corrida_stats) if s.ultima_corrida_stats else None,
		"scheduled_job": job,
	}
