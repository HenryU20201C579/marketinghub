"""Scraper de Meta Ad Library para el Radar.

Corre in-process desde un scheduled job o manualmente. Por cada competidor
activo hace una búsqueda por keyword en Ad Library (país configurable) y
upserta los anuncios en el DocType `Anuncio Competencia`. Marca como
pausados los ads que existían y ya no aparecen en el scrape.
"""
from __future__ import annotations

import json
import time
import traceback
from datetime import datetime, timezone

import frappe
from frappe.utils import now_datetime, today

from marketinghub.api import apify_actor

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
ANALISTA_ROLES = ("Marketinghub-Radar-Analista",) + ADMIN_ROLES


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


# =============== MAPPING Apify → DocType ===============

def _fmt_ts(ts):
	"""Timestamp unix o iso → 'YYYY-MM-DD'."""
	if not ts:
		return None
	if isinstance(ts, (int, float)):
		return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
	if isinstance(ts, str):
		return ts[:10]
	return None


def _map_fb_ad(item, competidor):
	"""Convierte un ad de Apify en payload para DocType Anuncio Competencia."""
	snap = item.get("snapshot") or {}
	body = snap.get("body") or {}
	copy_texto = body.get("text") if isinstance(body, dict) else str(body or "")

	# Media
	videos = snap.get("videos") or []
	images = snap.get("images") or []
	cards = snap.get("cards") or []
	video_hd = video_sd = imagen_prev = None
	if videos:
		v0 = videos[0] or {}
		video_hd = v0.get("videoHdUrl") or v0.get("video_hd_url")
		video_sd = v0.get("videoSdUrl") or v0.get("video_sd_url")
		imagen_prev = v0.get("videoPreviewImageUrl") or v0.get("video_preview_image_url")
	if not imagen_prev and images:
		imagen_prev = (images[0] or {}).get("originalImageUrl") or (images[0] or {}).get("original_image_url")

	# Formato
	if videos:
		formato = "Video"
	elif cards:
		formato = "Carrusel"
	elif images:
		formato = "Imagen"
	else:
		formato = None

	# Hashtags (extraer de copy)
	hashtags = None
	if copy_texto:
		tags = [w for w in copy_texto.split() if w.startswith("#")]
		if tags:
			hashtags = " ".join(tags[:15])

	# Plataformas → CSV
	plats = item.get("publisherPlatform") or []
	plataformas = ",".join(plats) if plats else None

	# Categorías
	cats = item.get("categories") or []
	categoria_ad = ",".join(cats) if cats else None

	return {
		"ad_archive_id": str(item.get("adArchiveID") or item.get("adArchiveId") or ""),
		"competidor": competidor,
		"page_id": str(item.get("pageId") or ""),
		"page_name": item.get("pageName") or (snap.get("pageName") or ""),
		"pais": "PE",
		"fecha_inicio": _fmt_ts(item.get("startDate") or item.get("startDateFormatted")),
		"esta_activo": 1 if item.get("isActive") else 0,
		"formato": formato,
		"copy_texto": copy_texto,
		"hashtags": hashtags,
		"cta_type": snap.get("ctaType") or snap.get("cta_type"),
		"landing_url": snap.get("linkUrl") or snap.get("link_url"),
		"plataformas": plataformas,
		"n_variantes": int(item.get("collationCount") or 1),
		"categoria_ad": categoria_ad,
		"video_hd_url": video_hd,
		"video_sd_url": video_sd,
		"imagen_preview_url": imagen_prev,
		"snapshot_json": json.dumps(item, ensure_ascii=False)[:60000],
	}


# =============== UPSERT ===============

def _upsert_ad(payload, stats):
	name = payload["ad_archive_id"]
	if not name:
		stats["skip"] += 1
		return
	existing = frappe.db.exists("Anuncio Competencia", name)
	try:
		if existing:
			doc = frappe.get_doc("Anuncio Competencia", name)
			# Preservamos fecha_inicio original si ya existía
			payload.pop("fecha_inicio", None) if doc.fecha_inicio else None
			for k, v in payload.items():
				if v is not None:
					setattr(doc, k, v)
			# refresh datos volatiles
			doc.esta_activo = payload.get("esta_activo", doc.esta_activo)
			doc.fecha_ultimo_visto = now_datetime()
			# si estaba pausado y volvió, limpiar la fecha
			if doc.esta_activo:
				doc.fecha_pausado = None
			doc.save(ignore_permissions=True)
			stats["update"] += 1
		else:
			payload["fecha_ultimo_visto"] = now_datetime()
			doc = frappe.get_doc({"doctype": "Anuncio Competencia", **payload})
			doc.insert(ignore_permissions=True)
			stats["insert"] += 1
	except Exception as e:
		stats["error"] += 1
		frappe.log_error(traceback.format_exc(), f"Ads upsert · {name}")


def _marcar_pausados(competidor, ids_vistos, stats):
	"""Los ads del competidor que existían activos y NO vinieron en el scrape → pausados."""
	if not competidor:
		return
	activos = frappe.db.get_all(
		"Anuncio Competencia",
		filters={"competidor": competidor, "esta_activo": 1},
		fields=["name"],
	)
	hoy = today()
	for a in activos:
		if a.name not in ids_vistos:
			try:
				frappe.db.set_value("Anuncio Competencia", a.name, {
					"esta_activo": 0,
					"fecha_pausado": hoy,
				})
				# recalcular etiqueta
				doc = frappe.get_doc("Anuncio Competencia", a.name)
				doc.save(ignore_permissions=True)
				stats["pausados"] += 1
			except Exception:
				pass


# =============== ORQUESTADOR ===============

def correr_scrape_ads(country="PE", count_per_marca=50):
	"""Se invoca desde scheduled job o manualmente. In-process."""
	from frappe.utils.password import get_decrypted_password

	inicio = time.time()
	stats = {"insert": 0, "update": 0, "pausados": 0, "skip": 0, "error": 0}
	log_lines = []

	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		return {"ok": False, "error": "apify_token no configurado"}

	competidores = frappe.db.get_all(
		"Competidor", filters={"activo": 1},
		fields=["name", "nombre_comercial"],
	)
	if not competidores:
		return {"ok": True, "mensaje": "sin competidores activos"}

	for comp in competidores:
		nombre = comp.get("nombre_comercial") or comp.get("name")
		try:
			items = apify_actor.scrape_facebook_ads(
				token, query=nombre, country=country, count=int(count_per_marca),
			)
			ids_vistos = set()
			for item in items:
				payload = _map_fb_ad(item, comp["name"])
				if payload["ad_archive_id"]:
					ids_vistos.add(payload["ad_archive_id"])
					_upsert_ad(payload, stats)
			_marcar_pausados(comp["name"], ids_vistos, stats)
			log_lines.append(f"{nombre} · {len(items)} ads")
		except Exception as e:
			stats["error"] += 1
			log_lines.append(f"{nombre} · ERROR: {e}")
			frappe.log_error(traceback.format_exc(), f"Radar Ads Scraper · {nombre}")

	duracion = round(time.time() - inicio, 1)
	frappe.db.commit()
	return {
		"ok": stats["error"] == 0,
		"stats": stats,
		"duracion_s": duracion,
		"log": log_lines,
	}


@frappe.whitelist()
def ejecutar_scrape_ads_ahora():
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede correr el scraper.", frappe.PermissionError)
	return correr_scrape_ads()


@frappe.whitelist()
def ejecutar_scrape_ads_competidor(competidor=None, count=30):
	"""Actualiza solo un competidor (para el botón por fila)."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista.", frappe.PermissionError)
	if not competidor:
		frappe.throw("competidor es obligatorio")
	from frappe.utils.password import get_decrypted_password
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		frappe.throw("apify_token no configurado")
	nombre = frappe.db.get_value("Competidor", competidor, "nombre_comercial") or competidor
	stats = {"insert": 0, "update": 0, "pausados": 0, "skip": 0, "error": 0}
	items = apify_actor.scrape_facebook_ads(token, query=nombre, country="PE", count=int(count))
	ids_vistos = set()
	for item in items:
		payload = _map_fb_ad(item, competidor)
		if payload["ad_archive_id"]:
			ids_vistos.add(payload["ad_archive_id"])
			_upsert_ad(payload, stats)
	_marcar_pausados(competidor, ids_vistos, stats)
	frappe.db.commit()
	return {"ok": True, "stats": stats, "items": len(items)}
