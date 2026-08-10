"""Orquestador diario del Radar de Competencia.

Flujo:
  1. Lee las Cuentas Sociales activas del ERP.
  2. Agrupa por plataforma (Instagram, TikTok).
  3. Dispara el actor Apify correspondiente para cada grupo.
  4. Mapea la respuesta al formato del ERP.
  5. Hace upsert de cada publicacion + registra snapshot de seguidores.

Uso:
  Requiere variables de entorno:
    ERP_URL         (default: https://erp.tiranidos.com)
    ERP_API_KEY
    ERP_API_SECRET

  El token de Apify se lee del propio ERP (Radar Settings.apify_token).

  ejecucion:
    python3 monitor.py                # scrape completo
    python3 monitor.py --dry-run      # simula sin escribir al ERP
    python3 monitor.py --limit 5      # solo N posts por cuenta (default 20)
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections import defaultdict

import apify_client
from erp_client import from_env, ERPError


# ============================================================
# MAPPERS: Apify JSON → dict para upsert_publicacion
# ============================================================
def _map_instagram(item: dict) -> dict:
	"""Un item del actor apify/instagram-scraper → payload de upsert."""
	tipo_map = {"Image": "Post", "Sidecar": "Carrusel", "Video": "Reel"}
	tipo = tipo_map.get(item.get("type"), "Post")
	# clips = Reel, incluso si el 'type' viene como Video
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
		# IG no expone shares/saves publicamente:
		"compartidos_actual": 0,
		"guardados_actual": 0,
		# metadatos para agrupar por cuenta:
		"_owner_username": item.get("ownerUsername") or "",
		"_input_url": item.get("inputUrl") or "",
	}


def _map_tiktok(item: dict) -> dict:
	"""Un item del actor clockworks/tiktok-scraper → payload de upsert."""
	author = item.get("authorMeta") or {}
	return {
		"url_publicacion": item.get("webVideoUrl"),
		"id_externo": str(item.get("id") or ""),
		"fecha_publicacion": (item.get("createTimeISO") or "")[:10] or None,
		"tipo_contenido": "Video",
		"descripcion": (item.get("text") or "").strip(),
		"hashtags": " ".join(
			f"#{h.get('name', '')}" for h in (item.get("hashtags") or [])
			if isinstance(h, dict)
		),
		"duracion_segundos": int(item.get("videoMeta", {}).get("duration") or 0),
		"vistas_actual": item.get("playCount") or 0,
		"likes_actual": item.get("diggCount") or 0,
		"comentarios_actual": item.get("commentCount") or 0,
		"compartidos_actual": item.get("shareCount") or 0,
		"guardados_actual": item.get("collectCount") or 0,
		"_owner_username": author.get("name") or "",
		"_input_url": "",
	}


# ============================================================
# CORE
# ============================================================
def run(limit_per_profile: int = 20, dry_run: bool = False):
	client = from_env()
	print(f"→ Conectando a {client.base}")

	# 1. Token Apify (desde el ERP)
	apify_token = client.call("marketinghub.api.radar_scraper.obtener_apify_token")
	if not apify_token:
		print("ERROR: apify_token no configurado en Radar Settings.")
		return 1

	# 2. Cuentas activas
	cuentas = client.call("marketinghub.api.radar_scraper.listar_cuentas_activas") or []
	if not cuentas:
		print("No hay cuentas activas para scrapear.")
		return 0
	print(f"→ {len(cuentas)} cuenta(s) activa(s)")

	# 3. Agrupar por plataforma
	por_plataforma = defaultdict(list)
	for c in cuentas:
		por_plataforma[c["plataforma"]].append(c)

	total_stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}

	# 4. Instagram
	if por_plataforma["Instagram"]:
		total_stats = _procesar_instagram(
			client, apify_token, por_plataforma["Instagram"],
			limit_per_profile, dry_run, total_stats,
		)

	# 5. TikTok
	if por_plataforma["TikTok"]:
		total_stats = _procesar_tiktok(
			client, apify_token, por_plataforma["TikTok"],
			limit_per_profile, dry_run, total_stats,
		)

	# 6. Resumen
	print("\n" + "="*60)
	print("RESUMEN")
	print("="*60)
	for k, v in total_stats.items():
		print(f"  {k:8}: {v}")
	return 0


def _procesar_instagram(client, token, cuentas, limit, dry_run, stats):
	print(f"\n=== INSTAGRAM ({len(cuentas)} cuentas) ===")
	urls = [c["url_perfil"] for c in cuentas if c.get("url_perfil")]
	if not urls:
		return stats
	try:
		print(f"→ Apify: scrapeando {len(urls)} perfil(es), {limit} posts c/u...")
		items = apify_client.scrape_instagram(token, urls, limit)
		print(f"→ recibidos {len(items)} items")
	except Exception as e:
		print(f"ERROR Apify IG: {e}")
		stats["error"] += 1
		return stats

	# Mapear inputUrl → cuenta
	url_to_cuenta = {c["url_perfil"].rstrip("/"): c for c in cuentas}
	handle_to_cuenta = {c["handle"].lower(): c for c in cuentas if c.get("handle")}

	for item in items:
		payload = _map_instagram(item)
		# Buscar la cuenta: primero por inputUrl, si no por owner username
		input_url = (payload.pop("_input_url") or "").rstrip("/")
		owner = payload.pop("_owner_username").lower()
		cuenta = url_to_cuenta.get(input_url) or handle_to_cuenta.get(owner)
		if not cuenta:
			stats["skip"] += 1
			continue
		payload["cuenta_social"] = cuenta["name"]
		if not payload["url_publicacion"]:
			stats["skip"] += 1
			continue
		stats = _upsert(client, payload, dry_run, stats)

	# Registrar seguidores por cuenta (owner encontrado en items)
	_registrar_seguidores_ig(client, cuentas, items, dry_run)
	return stats


def _procesar_tiktok(client, token, cuentas, limit, dry_run, stats):
	print(f"\n=== TIKTOK ({len(cuentas)} cuentas) ===")
	handles = [c["handle"] for c in cuentas if c.get("handle")]
	if not handles:
		return stats
	try:
		print(f"→ Apify: scrapeando {len(handles)} perfil(es), {limit} videos c/u...")
		items = apify_client.scrape_tiktok(token, handles, limit)
		print(f"→ recibidos {len(items)} items")
	except Exception as e:
		print(f"ERROR Apify TikTok: {e}")
		stats["error"] += 1
		return stats

	handle_to_cuenta = {c["handle"].lower(): c for c in cuentas if c.get("handle")}
	for item in items:
		payload = _map_tiktok(item)
		owner = (payload.pop("_owner_username") or "").lower().lstrip("@")
		payload.pop("_input_url", None)
		cuenta = handle_to_cuenta.get(owner)
		if not cuenta:
			stats["skip"] += 1
			continue
		payload["cuenta_social"] = cuenta["name"]
		if not payload["url_publicacion"]:
			stats["skip"] += 1
			continue
		stats = _upsert(client, payload, dry_run, stats)

	_registrar_seguidores_tiktok(client, cuentas, items, dry_run)
	return stats


def _upsert(client, payload, dry_run, stats):
	if dry_run:
		print(f"  DRY {payload['tipo_contenido']:<8} {payload['url_publicacion']}"
		      f"  v={payload['vistas_actual']} l={payload['likes_actual']}")
		stats["insert"] += 1
		return stats
	try:
		r = client.call("marketinghub.api.radar_scraper.upsert_publicacion", **payload)
		accion = r.get("accion") if isinstance(r, dict) else "?"
		stats[accion] = stats.get(accion, 0) + 1
		marca = "🔥" if r.get("es_viral") else "  "
		print(f"  {marca} {accion:6} {payload['tipo_contenido']:<8} "
		      f"v={payload['vistas_actual']:<8} l={payload['likes_actual']:<6} "
		      f"eng={r.get('engagement_pct', 0):.2f}%  {payload['url_publicacion']}")
	except ERPError as e:
		print(f"  ✗ ERR: {e}")
		stats["error"] += 1
	return stats


def _registrar_seguidores_ig(client, cuentas, items, dry_run):
	"""IG Apify a veces trae followersCount por perfil (en resultsType=details).
	Con resultsType=posts NO viene. Skipeamos por ahora."""
	pass


def _registrar_seguidores_tiktok(client, cuentas, items, dry_run):
	"""TikTok Apify pone fans en authorMeta de cada item."""
	handle_to_cuenta = {c["handle"].lower(): c for c in cuentas if c.get("handle")}
	seen = {}
	for item in items:
		author = item.get("authorMeta") or {}
		handle = (author.get("name") or "").lower().lstrip("@")
		seguidores = author.get("fans")
		if handle and seguidores and handle not in seen:
			seen[handle] = seguidores
	for handle, seg in seen.items():
		cuenta = handle_to_cuenta.get(handle)
		if not cuenta:
			continue
		if dry_run:
			print(f"  DRY seguidores {handle}: {seg}")
			continue
		try:
			r = client.call(
				"marketinghub.api.radar_scraper.registrar_seguidores",
				cuenta_social=cuenta["name"], seguidores=seg,
			)
			print(f"  ✓ seguidores {handle}: {seg} (actual: {r.get('seguidores_actual')})")
		except ERPError as e:
			print(f"  ✗ ERR seguidores {handle}: {e}")


# ============================================================
# CLI
# ============================================================
def main():
	ap = argparse.ArgumentParser(description="Radar de Competencia - orquestador diario")
	ap.add_argument("--limit", type=int, default=20,
	                help="Posts por perfil (default 20)")
	ap.add_argument("--dry-run", action="store_true",
	                help="No escribir al ERP, solo mostrar")
	args = ap.parse_args()
	try:
		return run(limit_per_profile=args.limit, dry_run=args.dry_run)
	except Exception:
		traceback.print_exc()
		return 1


if __name__ == "__main__":
	sys.exit(main())
