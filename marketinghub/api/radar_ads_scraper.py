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

	# Media principal (primer video / imagen)
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

	# Extras (para carruseles con múltiples slides)
	extras = {"videos": [], "images": []}
	# Videos adicionales (a partir del segundo)
	for v in videos[1:]:
		url = (v or {}).get("videoHdUrl") or (v or {}).get("videoSdUrl")
		if url:
			extras["videos"].append(url)
	for v in (snap.get("extraVideos") or []):
		url = (v or {}).get("videoHdUrl") or (v or {}).get("videoSdUrl") or (v if isinstance(v, str) else None)
		if url:
			extras["videos"].append(url)
	# Imágenes adicionales
	for img in images[1:]:
		url = (img or {}).get("originalImageUrl") or (img or {}).get("resizedImageUrl")
		if url:
			extras["images"].append(url)
	for img in (snap.get("extraImages") or []):
		url = (img or {}).get("originalImageUrl") or (img or {}).get("resizedImageUrl") or (img if isinstance(img, str) else None)
		if url:
			extras["images"].append(url)
	# Cards de carrusel
	for card in cards:
		url = (card or {}).get("originalImageUrl") or (card or {}).get("resizedImageUrl")
		if url:
			extras["images"].append(url)
	extras_json = json.dumps(extras, ensure_ascii=False) if (extras["videos"] or extras["images"]) else None

	# Formato
	if videos:
		formato = "Video"
	elif cards:
		formato = "Carrusel"
	elif images:
		formato = "Imagen"
	else:
		formato = None

	# Hashtags
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
		"page_like_count": int(snap.get("pageLikeCount") or 0),
		"pais": "PE",
		"fecha_inicio": _fmt_ts(item.get("startDate") or item.get("startDateFormatted")),
		"fecha_fin": _fmt_ts(item.get("endDate") or item.get("endDateFormatted")),
		"esta_activo": 1 if item.get("isActive") else 0,
		"formato": formato,
		"copy_texto": copy_texto,
		"hashtags": hashtags,
		"cta_type": snap.get("ctaType") or snap.get("cta_type"),
		"cta_text": snap.get("ctaText") or snap.get("cta_text"),
		"landing_url": snap.get("linkUrl") or snap.get("link_url"),
		"plataformas": plataformas,
		"n_variantes": int(item.get("collationCount") or 1),
		"categoria_ad": categoria_ad,
		"video_hd_url": video_hd,
		"video_sd_url": video_sd,
		"imagen_preview_url": imagen_prev,
		"extras_media_json": extras_json,
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


# =============== AJUSTES POR MARCA ===============

# Precio calibrado por ad del actor de FB Ad Library. Es un estimado inicial;
# se puede pasar a un `calibrar_coste_ads()` como en el scraper de posts cuando
# haya suficientes corridas reales que confirmen la tarifa.
COSTE_POR_AD_USD = 0.007

# Default global de ads por marca cuando limite_ads = 0.
DEFAULT_ADS_POR_MARCA = 50


def _cfg_de_marca(comp):
	"""Extrae {query, pais, limite, pausada} para una marca competidor.

	Cae al default (nombre_comercial / PE / 50 / no pausada) si el campo esta
	vacío. Sirve tanto al scraper como al estimador."""
	nombre = comp.get("nombre_comercial") or comp.get("name")
	return {
		"nombre": nombre,
		"query": (comp.get("query_ads_library") or "").strip() or nombre,
		"pais": (comp.get("pais_ads") or "PE").strip().upper()[:2] or "PE",
		"limite": int(comp.get("limite_ads") or 0) or DEFAULT_ADS_POR_MARCA,
		"pausada": int(comp.get("pausar_ads") or 0),
	}


def _marcas_para_scrape(solo_competidor=None):
	"""Competidores activos con sus ajustes de ads. Filtra pausados y opcionalmente
	limita a un solo competidor (para el ▶ por fila)."""
	filtros = {"activo": 1}
	if solo_competidor:
		filtros["name"] = solo_competidor
	campos = ["name", "nombre_comercial", "query_ads_library", "pais_ads",
	          "limite_ads", "pausar_ads"]
	crudos = frappe.db.get_all("Competidor", filters=filtros, fields=campos)
	# El pausado siempre se filtra: si el usuario le da ▶ a una marca pausada,
	# el endpoint del competidor lo rechaza; aquí solo entran las que si corren.
	return [c for c in crudos if not int(c.get("pausar_ads") or 0)]


@frappe.whitelist()
def estimar_scrape_ads(competidor=None):
	"""Coste estimado de una corrida de ads.

	`competidor` opcional para el ▶ individual: si va, devuelve solo esa marca.
	Sin él, estimado de todas las marcas activas no pausadas."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede consultar el estimado.", frappe.PermissionError)
	campos = ["name", "nombre_comercial", "query_ads_library", "pais_ads",
	          "limite_ads", "pausar_ads"]
	if competidor:
		crudos = frappe.db.get_all("Competidor", filters={"name": competidor, "activo": 1},
		                            fields=campos)
	else:
		crudos = frappe.db.get_all("Competidor", filters={"activo": 1}, fields=campos)
	por_marca = {}
	total = 0.0
	for c in crudos:
		cfg = _cfg_de_marca(c)
		if cfg["pausada"]:
			por_marca[c["name"]] = 0.0
			continue
		costo = round(cfg["limite"] * COSTE_POR_AD_USD, 4)
		por_marca[c["name"]] = costo
		total += costo
	return {
		"por_marca": por_marca,
		"total": round(total, 4),
		"precio_por_ad": COSTE_POR_AD_USD,
	}


# =============== ORQUESTADOR ===============

def correr_scrape_ads(count_per_marca=None):
	"""Se invoca desde scheduled job o manualmente. In-process.

	`count_per_marca` es un override global opcional (para pruebas). En operación
	normal cada marca usa su propio limite_ads del DocType Competidor."""
	from frappe.utils.password import get_decrypted_password

	inicio = time.time()
	stats = {"insert": 0, "update": 0, "pausados": 0, "skip": 0, "error": 0}
	log_lines = []

	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		return {"ok": False, "error": "apify_token no configurado"}

	competidores = _marcas_para_scrape()
	if not competidores:
		return {"ok": True, "mensaje": "sin competidores activos"}

	for comp in competidores:
		cfg = _cfg_de_marca(comp)
		# override manual (ej: probar con count=5) ignora el limite_ads de la marca
		limite = int(count_per_marca) if count_per_marca else cfg["limite"]
		try:
			items = apify_actor.scrape_facebook_ads(
				token, query=cfg["query"], country=cfg["pais"], count=limite,
			)
			ids_vistos = set()
			for item in items:
				payload = _map_fb_ad(item, comp["name"])
				if payload["ad_archive_id"]:
					ids_vistos.add(payload["ad_archive_id"])
					_upsert_ad(payload, stats)
			_marcar_pausados(comp["name"], ids_vistos, stats)
			log_lines.append(f"{cfg['nombre']} · {cfg['query']!r} @ {cfg['pais']} · {len(items)} ads")
		except Exception as e:
			stats["error"] += 1
			log_lines.append(f"{cfg['nombre']} · ERROR: {e}")
			frappe.log_error(traceback.format_exc(), f"Radar Ads Scraper · {cfg['nombre']}")

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
	"""Botón «Scrapear todas»: corre todas las marcas activas no pausadas."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista puede correr el scraper.", frappe.PermissionError)
	return correr_scrape_ads()


@frappe.whitelist()
def ejecutar_scrape_ads_competidor(competidor=None, count=None):
	"""Actualiza solo un competidor (botón ▶ por fila).

	`count` opcional: si viene, sobreescribe el limite_ads de la marca (uso
	puntual, por ejemplo probar con 10). Sin él usa el default de la marca."""
	if not _has_role(ANALISTA_ROLES):
		frappe.throw("Solo un analista.", frappe.PermissionError)
	if not competidor:
		frappe.throw("competidor es obligatorio")
	from frappe.utils.password import get_decrypted_password
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		frappe.throw("apify_token no configurado")
	# leemos la marca completa para usar sus ajustes (query, pais, limite)
	campos = ["name", "nombre_comercial", "query_ads_library", "pais_ads",
	          "limite_ads", "pausar_ads"]
	comp = frappe.db.get_value("Competidor", competidor, campos, as_dict=True)
	if not comp:
		frappe.throw(f"El competidor «{competidor}» no existe.")
	cfg = _cfg_de_marca(comp)
	if cfg["pausada"]:
		frappe.throw(f"«{cfg['nombre']}» tiene el scrapeo de ads pausado.")
	limite = int(count) if count else cfg["limite"]
	stats = {"insert": 0, "update": 0, "pausados": 0, "skip": 0, "error": 0}
	items = apify_actor.scrape_facebook_ads(token, query=cfg["query"], country=cfg["pais"], count=limite)
	ids_vistos = set()
	for item in items:
		payload = _map_fb_ad(item, competidor)
		if payload["ad_archive_id"]:
			ids_vistos.add(payload["ad_archive_id"])
			_upsert_ad(payload, stats)
	_marcar_pausados(competidor, ids_vistos, stats)
	frappe.db.commit()
	return {"ok": True, "stats": stats, "items": len(items),
	        "query": cfg["query"], "pais": cfg["pais"], "limite": limite}
