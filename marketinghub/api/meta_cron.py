"""Endpoints para triggers externos (n8n u otros) de sincronizacion Meta.

Diseno:
- Un solo endpoint publico protegido con un secret compartido guardado en
  `site_config.json` como `ventahub_cron_secret`.
- Cada sitio (erp/barra/ginbak/etc.) tiene su propio secret y su propia
  `Configuracion Meta`.
- n8n hace 1 POST por sitio. Si un sitio falla, n8n dispara la notificacion
  (usa el codigo HTTP != 2xx).
- Si `Configuracion Meta.habilitado != 1`, el endpoint retorna 200 con
  `{"skipped": true}` para que n8n NO trate ese sitio como error.
"""

import hmac
import frappe


def _authenticate(secret):
    """Valida el secret contra site_config. Constant-time compare."""
    expected = (frappe.get_site_config().get("ventahub_cron_secret") or "").strip()
    if not expected:
        frappe.local.response.http_status_code = 500
        return False, "Sitio sin `ventahub_cron_secret` en site_config.json"
    provided = str(secret or "").strip()
    if not provided:
        frappe.local.response.http_status_code = 401
        return False, "Falta secret"
    if not hmac.compare_digest(expected, provided):
        frappe.local.response.http_status_code = 403
        return False, "Secret invalido"
    return True, None


def _load_config():
    """Retorna (habilitado, account_id, error_msg)."""
    try:
        conf = frappe.get_single("Configuracion Meta")
    except Exception as e:
        return False, None, f"No hay Configuracion Meta: {e}"

    habilitado = bool(int(getattr(conf, "habilitado", 0) or 0))
    account_id = (getattr(conf, "ad_account_id", "") or "").strip()
    return habilitado, account_id, None


@frappe.whitelist(allow_guest=True)
def sync_meta(secret=None):
    """Sync Meta triggereado desde n8n u otro cron externo.

    Uso desde n8n:
        POST https://<sitio>/api/method/ventahub.api.meta_cron.sync_meta
        Content-Type: application/x-www-form-urlencoded
        Body: secret=<VENTAHUB_CRON_SECRET>

    Respuestas:
        200 OK  → sync ejecutado o skippeado (habilitado=0). Payload con detalles.
        400 BAD → falta configuracion (ad_account_id vacio).
        401/403 → secret invalido o ausente.
        500     → site_config sin `ventahub_cron_secret`, o exception del sync.
    """
    ok, err = _authenticate(secret)
    if not ok:
        return {"ok": False, "error": err, "site": frappe.local.site}

    habilitado, account_id, cfg_err = _load_config()
    if cfg_err:
        frappe.local.response.http_status_code = 400
        return {"ok": False, "error": cfg_err, "site": frappe.local.site}

    if not habilitado:
        return {
            "ok": True,
            "skipped": True,
            "reason": "Configuracion Meta.habilitado = 0",
            "site": frappe.local.site,
        }

    if not account_id:
        frappe.local.response.http_status_code = 400
        return {
            "ok": False,
            "error": "Configuracion Meta.ad_account_id vacio",
            "site": frappe.local.site,
        }

    # Ejecutamos el sync usando el usuario Administrator para saltarnos el
    # _require_admin() del endpoint original. El secret ya autentico.
    frappe.set_user("Administrator")

    try:
        from marketinghub.api.meta_ads import sincronizar_campanas
        stats = sincronizar_campanas(account_id) or {}
        return {
            "ok": True,
            "site": frappe.local.site,
            "account_id": account_id,
            "stats": stats,
        }
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "meta_cron sync_meta")
        frappe.local.response.http_status_code = 500
        return {
            "ok": False,
            "error": str(e)[:400],
            "site": frappe.local.site,
        }


@frappe.whitelist(allow_guest=True)
def ping(secret=None):
    """Healthcheck simple para n8n. Solo valida el secret."""
    ok, err = _authenticate(secret)
    if not ok:
        return {"ok": False, "error": err, "site": frappe.local.site}

    habilitado, account_id, cfg_err = _load_config()
    return {
        "ok": True,
        "site": frappe.local.site,
        "meta_habilitado": habilitado,
        "meta_ad_account_id_configurado": bool(account_id),
    }
