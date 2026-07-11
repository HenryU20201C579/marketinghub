import frappe


ADMIN_ROLES = ("Ventahub-Integraciones-Administrar",)


def _is_admin():
    roles = frappe.get_roles()
    return "System Manager" in roles or any(r in roles for r in ADMIN_ROLES)


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/integraciones/meta"
        raise frappe.Redirect

    if not _is_admin():
        context.no_access = True
        context.required_roles = list(ADMIN_ROLES)
        return

    context.no_access = False

    try:
        conf = frappe.get_single("Configuracion Meta")
        context.config = {
            "habilitado": int(conf.habilitado or 0),
            "access_token": conf.get_password("access_token", raise_exception=False) or "",
            "ad_account_id": conf.ad_account_id or "",
            "business_account_id": conf.business_account_id or "",
            "graph_api_version": conf.graph_api_version or "v22.0",
            "capi_enabled": int(conf.capi_enabled or 0),
            "pixel_id": conf.pixel_id or "",
            "capi_token": conf.get_password("capi_token", raise_exception=False) or "",
            "capi_test_event_code": conf.capi_test_event_code or "",
        }
    except Exception:
        context.config = {
            "habilitado": 0, "access_token": "", "ad_account_id": "",
            "business_account_id": "", "graph_api_version": "v22.0",
            "capi_enabled": 0, "pixel_id": "", "capi_token": "",
            "capi_test_event_code": "",
        }


_EDITABLE = {
    "habilitado", "ad_account_id", "business_account_id",
    "graph_api_version", "capi_enabled", "pixel_id", "capi_test_event_code",
}
_PASSWORDS = {"access_token", "capi_token"}


@frappe.whitelist()
def save_config(updates):
    if not _is_admin():
        frappe.throw(
            "No tienes permisos para configurar Meta.",
            frappe.PermissionError,
        )

    import json
    if isinstance(updates, str):
        updates = json.loads(updates)
    updates = updates or {}

    doc = frappe.get_single("Configuracion Meta")
    for k, v in updates.items():
        if k in _EDITABLE:
            doc.set(k, v)
    for k in _PASSWORDS:
        if k in updates:
            doc.set(k, updates.get(k) or "")

    doc.flags.ignore_permissions = True
    doc.save()
    frappe.db.commit()
    return {"status": "success", "message": "Configuracion Meta guardada."}


@frappe.whitelist()
def test_connection():
    if not _is_admin():
        frappe.throw("Sin permisos.", frappe.PermissionError)
    import requests
    from marketinghub.marketinghub.doctype.configuracion_meta.configuracion_meta import (
        get_meta_token, get_meta_ad_account_id, get_graph_api_version,
    )
    token = get_meta_token()
    if not token:
        return {"ok": False, "msg": "Sin Access Token configurado."}
    account_id = get_meta_ad_account_id()
    version = get_graph_api_version()
    if not account_id:
        try:
            r = requests.get(
                f"https://graph.facebook.com/{version}/me",
                params={"access_token": token, "fields": "id,name"},
                timeout=10,
            )
            data = r.json()
            if "error" in data:
                return {"ok": False, "msg": data["error"].get("message", "Error Meta")}
            return {"ok": True, "msg": f"Token valido (user: {data.get('name', '?')}). Configura Ad Account ID para insights."}
        except Exception as e:
            return {"ok": False, "msg": str(e)}
    try:
        r = requests.get(
            f"https://graph.facebook.com/{version}/act_{account_id}",
            params={"access_token": token, "fields": "name,account_status"},
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"ok": False, "msg": data["error"].get("message", "Error Meta")}
        return {"ok": True, "msg": f"Cuenta '{data.get('name')}' status={data.get('account_status')}"}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


@frappe.whitelist()
def list_ad_accounts(access_token=None):
    """Retorna las Ad Accounts accesibles con el token dado.

    Si no se pasa `access_token`, usa el que este guardado en
    Configuracion Meta. Util para poblar el dropdown de seleccion
    cuando el user pega un token nuevo antes de guardarlo.
    """
    if not _is_admin():
        frappe.throw("Sin permisos.", frappe.PermissionError)

    import requests
    from marketinghub.marketinghub.doctype.configuracion_meta.configuracion_meta import (
        get_meta_token, get_graph_api_version,
    )

    token = (access_token or "").strip() or get_meta_token()
    if not token:
        return {"ok": False, "msg": "Falta Access Token", "accounts": []}

    version = get_graph_api_version() or "v22.0"

    try:
        r = requests.get(
            f"https://graph.facebook.com/{version}/me/adaccounts",
            params={
                "access_token": token,
                "fields": "id,name,account_id,account_status,currency",
                "limit": 200,
            },
            timeout=15,
        )
        data = r.json() or {}
        if "error" in data:
            return {
                "ok": False,
                "msg": data["error"].get("message", "Error Meta"),
                "accounts": [],
            }

        accounts = []
        status_map = {1: "activa", 2: "deshabilitada", 3: "pendiente_cierre", 7: "pendiente_revision", 8: "en_pago", 9: "en_grace", 100: "pending_closure", 101: "cerrada"}
        for a in data.get("data", []):
            aid = str(a.get("account_id") or "").strip()
            if not aid:
                continue
            accounts.append({
                "account_id": aid,
                "name": a.get("name") or f"Cuenta {aid}",
                "currency": a.get("currency") or "",
                "status_code": a.get("account_status"),
                "status": status_map.get(a.get("account_status"), "desconocido"),
            })

        return {"ok": True, "accounts": accounts, "total": len(accounts)}
    except requests.exceptions.Timeout:
        return {"ok": False, "msg": "Timeout consultando Meta.", "accounts": []}
    except Exception as e:
        return {"ok": False, "msg": str(e)[:200], "accounts": []}
