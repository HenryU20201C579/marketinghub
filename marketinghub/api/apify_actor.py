"""Cliente ligero para Apify actors (usado desde el propio ERP)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

APIFY_BASE = "https://api.apify.com/v2/acts"
INSTAGRAM_ACTOR = "apify~instagram-scraper"
TIKTOK_ACTOR = "clockworks~tiktok-scraper"
FB_ADS_ACTOR = "apify~facebook-ads-scraper"


class ApifyError(RuntimeError):
	pass


def _post_run_sync(actor_id: str, token: str, payload: dict, timeout_s: int = 300):
	url = (f"{APIFY_BASE}/{actor_id}/run-sync-get-dataset-items"
	       f"?token={token}&timeout={timeout_s}")
	req = urllib.request.Request(
		url,
		data=json.dumps(payload).encode("utf-8"),
		headers={"Content-Type": "application/json"},
		method="POST",
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout_s + 15) as resp:
			body = resp.read().decode("utf-8")
	except urllib.error.HTTPError as e:
		body = e.read().decode("utf-8", errors="replace")
		raise ApifyError(f"HTTP {e.code} · {body[:300]}") from e
	try:
		return json.loads(body)
	except json.JSONDecodeError as e:
		raise ApifyError(f"Respuesta no JSON: {body[:200]}") from e


def resolver_act_id(token: str, slug: str):
	"""ID interno del actor a partir de su slug (apify~instagram-scraper -> shu8hv…)."""
	url = f"https://api.apify.com/v2/acts/{slug}?token={token}"
	try:
		with urllib.request.urlopen(url, timeout=30) as resp:
			return json.loads(resp.read().decode("utf-8"))["data"]["id"]
	except Exception:
		return None


def listar_runs(token: str, limite: int = 100, act_ids=None):
	"""Runs recientes de la cuenta: [{act_id, inicio_epoch, fin_epoch, usd, estado}].

	Apify no devuelve el coste en `run-sync-get-dataset-items`, así que el gasto real
	se obtiene después del histórico de runs. `act_ids` filtra por actor (para no
	sumar, p.ej., los runs del scraper de anuncios). Devuelve None si falla."""
	from datetime import datetime, timezone

	def _epoch(valor):
		if not valor:
			return None
		for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
			try:
				return datetime.strptime(valor, fmt).replace(tzinfo=timezone.utc).timestamp()
			except ValueError:
				continue
		return None

	url = f"https://api.apify.com/v2/actor-runs?token={token}&desc=1&limit={int(limite)}"
	try:
		with urllib.request.urlopen(url, timeout=45) as resp:
			data = json.loads(resp.read().decode("utf-8"))["data"]
	except Exception:
		return None

	runs = []
	for run in data.get("items") or []:
		if act_ids and run.get("actId") not in act_ids:
			continue
		inicio = _epoch(run.get("startedAt"))
		if inicio is None:
			continue
		runs.append({
			"act_id": run.get("actId"),
			"inicio_epoch": inicio,
			"fin_epoch": _epoch(run.get("finishedAt")) or inicio,
			"usd": float(run.get("usageTotalUsd") or 0),
			"estado": run.get("status"),
		})
	return runs


def coste_desde(token: str, desde_epoch: float, limite: int = 100, act_ids=None):
	"""Suma el coste de los runs arrancados desde `desde_epoch`.

	Devuelve (usd, n_runs); (None, 0) si no se pudo consultar."""
	runs = listar_runs(token, limite, act_ids)
	if runs is None:
		return None, 0
	elegidos = [r for r in runs if r["inicio_epoch"] >= desde_epoch]
	return round(sum(r["usd"] for r in elegidos), 4), len(elegidos)


def scrape_instagram(token: str, urls: list, results_per_profile: int = 20):
	payload = {
		"directUrls": urls,
		"resultsType": "posts",
		"resultsLimit": results_per_profile,
		"addParentData": False,
	}
	return _post_run_sync(INSTAGRAM_ACTOR, token, payload)


def scrape_tiktok(token: str, handles: list, results_per_profile: int = 20):
	payload = {
		"profiles": [h.lstrip("@") for h in handles],
		"resultsPerPage": results_per_profile,
		"shouldDownloadVideos": False,
		"shouldDownloadCovers": False,
		"shouldDownloadSubtitles": False,
	}
	return _post_run_sync(TIKTOK_ACTOR, token, payload, timeout_s=360)


def scrape_facebook_ads(token: str, query: str, country: str = "PE", count: int = 50):
	"""Trae ads de Meta Ad Library filtrando por keyword + país.

	`query` es el nombre de marca (ej: 'apolusso'). El actor busca coincidencias
	en Ad Library. `count` limita cuántos ads devolver."""
	if not query:
		return []
	# URL de Ad Library con search por keyword. active_status=all trae activos + pausados.
	ads_url = (
		"https://www.facebook.com/ads/library/"
		f"?active_status=all&ad_type=all&country={country}"
		f"&q={query}&search_type=keyword_unordered"
	)
	payload = {
		"startUrls": [{"url": ads_url}],
		"count": int(count),
	}
	return _post_run_sync(FB_ADS_ACTOR, token, payload, timeout_s=300)
