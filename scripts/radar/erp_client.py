"""Cliente HTTP para hablar con el ERP de Tiranidos via API Key/Secret."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class ERPError(RuntimeError):
	pass


class ERPClient:
	def __init__(self, base_url: str, api_key: str, api_secret: str):
		self.base = base_url.rstrip("/")
		self.auth = f"token {api_key}:{api_secret}"

	def call(self, method: str, **kwargs):
		"""Llama un endpoint whitelisted del ERP con args en form-urlencoded."""
		url = f"{self.base}/api/method/{method}"
		body = urllib.parse.urlencode(
			{k: (json.dumps(v) if isinstance(v, (list, dict)) else v)
			 for k, v in kwargs.items() if v is not None},
		).encode("utf-8")
		req = urllib.request.Request(
			url,
			data=body,
			headers={
				"Authorization": self.auth,
				"Content-Type": "application/x-www-form-urlencoded",
				"Accept": "application/json",
			},
			method="POST",
		)
		try:
			with urllib.request.urlopen(req, timeout=45) as resp:
				return json.loads(resp.read().decode("utf-8")).get("message")
		except urllib.error.HTTPError as e:
			body = e.read().decode("utf-8", errors="replace")
			raise ERPError(f"{method}: HTTP {e.code} · {body[:400]}") from e


def from_env() -> ERPClient:
	base = os.environ.get("ERP_URL", "https://erp.tiranidos.com")
	key = os.environ["ERP_API_KEY"]
	sec = os.environ["ERP_API_SECRET"]
	return ERPClient(base, key, sec)
