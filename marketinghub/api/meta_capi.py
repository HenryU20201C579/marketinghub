"""Meta Conversions API helpers (multi-tenant).

Credenciales se leen del DocType Single `Meta CAPI Settings` del sitio
actual, NO de un DocType compartido entre sitios. Esto permite que cada
cliente del SaaS use su propio Pixel ID + Access Token.

Si el sitio no tiene Sales Invoice o no quiere usar el hook on_submit,
no es necesario hacer nada: el monitor seguirá funcionando y mostrará
"No hay eventos registrados aún".
"""

import frappe
import hashlib
import json

from marketinghub.marketinghub.doctype.configuracion_meta.configuracion_meta import (
    get_meta_pixel_id as _conf_get_meta_pixel_id,
    get_meta_capi_token as _conf_get_meta_capi_token,
    is_capi_enabled as _conf_is_capi_enabled,
)

import time

import requests

GRAPH_API_VERSION = "v19.0"
GRAPH_API_URL = "https://graph.facebook.com"


def _get_credentials():
	"""Retorna (pixel_id, access_token, test_event_code) del Single."""
	try:
		settings = frappe.get_cached_doc("Meta CAPI Settings")
	except Exception:
		return None, None, None
	pixel_id = (settings.pixel_id or "").strip() or None
	token = settings.get_password("access_token", raise_exception=False) if settings.access_token else None
	test_code = (settings.test_event_code or "").strip() or None
	return pixel_id, token, test_code


def _hash_sha256(value):
	if not value:
		return None
	return hashlib.sha256(str(value).strip().lower().encode("utf-8")).hexdigest()


def _log_capi_event(invoice_name, customer, amount, status, detail=""):
	"""Registra un evento CAPI como Comment vinculado a Sales Invoice."""
	log_data = json.dumps({
		"invoice": invoice_name,
		"customer": customer,
		"amount": float(amount) if amount else 0,
		"status": status,
		"detail": detail,
		"timestamp": frappe.utils.now(),
	})
	frappe.get_doc({
		"doctype": "Comment",
		"comment_type": "Comment",
		"reference_doctype": "Sales Invoice",
		"reference_name": invoice_name,
		"content": f'<div data-meta-capi="true">{log_data}</div>',
	}).insert(ignore_permissions=True)


# ─── API Endpoints para Dashboard ───

@frappe.whitelist()
def check_status():
	"""Verifica el estado de la conexión Meta CAPI y devuelve métricas."""
	pixel_id, token, _ = _get_credentials()

	result = {
		"has_pixel_id": bool(pixel_id),
		"has_token": bool(token),
		"pixel_id": (pixel_id[:6] + "...") if pixel_id else None,
	}

	total = frappe.db.count("Comment", {
		"comment_type": "Comment",
		"content": ["like", "%data-meta-capi%"],
	})
	success_row = frappe.db.sql("""
		SELECT COUNT(*) FROM `tabComment`
		WHERE comment_type = 'Comment'
		  AND content LIKE %(pat)s
		  AND content LIKE %(ok)s
	""", {"pat": "%data-meta-capi%", "ok": '%"success"%'})
	success = success_row[0][0] if success_row else 0

	result["total_events"] = total
	result["success_events"] = success
	result["error_events"] = total - success
	return result


@frappe.whitelist()
def get_capi_logs(limit=20):
	"""Devuelve los últimos eventos CAPI registrados como Comments."""
	try:
		limit = int(limit)
	except (TypeError, ValueError):
		limit = 20
	limit = max(1, min(limit, 200))

	rows = frappe.db.sql("""
		SELECT reference_name AS invoice, content, creation
		FROM `tabComment`
		WHERE comment_type = 'Comment'
		  AND content LIKE %(pat)s
		ORDER BY creation DESC
		LIMIT %(lim)s
	""", {"pat": "%data-meta-capi%", "lim": limit}, as_dict=True)

	logs = []
	for c in rows:
		try:
			raw = c.content.split('data-meta-capi="true">')[1].split("</div>")[0]
			data = json.loads(raw)
			data["creation"] = str(c.creation)
			logs.append(data)
		except Exception:
			logs.append({"invoice": c.invoice, "status": "unknown", "creation": str(c.creation)})
	return logs


@frappe.whitelist()
def send_test_event():
	"""Envía un evento de prueba a Meta CAPI y devuelve el resultado."""
	pixel_id, token, test_code = _get_credentials()
	if not pixel_id or not token:
		return {
			"success": False,
			"error": "Faltan credenciales. Configura 'Meta CAPI Settings' (Pixel ID + Access Token).",
		}

	phone_hash = _hash_sha256("+51999999999")
	email_hash = _hash_sha256("test@example.com")
	test_event_code = test_code or ("TEST" + str(int(time.time()))[-6:])

	event_data = {
		"data": [{
			"event_name": "Purchase",
			"event_time": int(time.time()),
			"action_source": "system_generated",
			"user_data": {"ph": [phone_hash], "em": [email_hash]},
			"custom_data": {
				"value": 1.00,
				"currency": "PEN",
				"order_id": "TEST-" + frappe.utils.now_datetime().strftime("%Y%m%d%H%M%S"),
			},
		}],
		"test_event_code": test_event_code,
	}

	url = f"{GRAPH_API_URL}/{GRAPH_API_VERSION}/{pixel_id}/events"
	try:
		response = requests.post(url, params={"access_token": token}, json=event_data, timeout=10)
		result = response.json()

		if response.status_code in (200, 201) and result.get("events_received", 0) > 0:
			return {
				"success": True,
				"events_received": result["events_received"],
				"fbtrace_id": result.get("fbtrace_id", ""),
				"test_code": event_data["test_event_code"],
				"response_code": response.status_code,
			}
		return {
			"success": False,
			"error": (result.get("error") or {}).get("message") or response.text[:300],
			"response_code": response.status_code,
		}
	except Exception as e:
		return {"success": False, "error": str(e)}
