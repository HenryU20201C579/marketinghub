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
