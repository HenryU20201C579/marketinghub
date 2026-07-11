"""Conector WhatsApp Cloud API → Chatwoot Inboxes.

Flujo:
1. Con el `access_token` de Configuracion Meta, se descubren via Graph API:
   Business Portfolios → WABAs → Phone Numbers.
2. En paralelo se listan los Inboxes actuales de Chatwoot filtrando los
   que son whatsapp_cloud, y se cruzan por `phone_number_id` para saber
   cuales estan conectados.
3. Al Conectar, se crea el Inbox en Chatwoot via su API y se subscribe la
   app a los webhooks del WABA en Meta.
4. Al Desconectar, se elimina el Inbox y se remueve la suscripcion.
"""

import frappe
import requests
import secrets


ADMIN_ROLES = ("Ventahub-Integraciones-Administrar",)
_GRAPH = "https://graph.facebook.com"


def _is_admin():
    roles = frappe.get_roles()
    return "System Manager" in roles or any(r in roles for r in ADMIN_ROLES)


def _require_admin():
    if not _is_admin():
        frappe.throw(
            "Sin permisos. Se requiere Ventahub-Integraciones-Administrar.",
            frappe.PermissionError,
        )


def get_context(context):
    context.no_cache = 1

    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/integraciones/whatsapp"
        raise frappe.Redirect

    if not _is_admin():
        context.no_access = True
        context.required_roles = list(ADMIN_ROLES)
        return

    context.no_access = False


# ─── Helpers ─────────────────────────────────────────────────────────────

def _get_meta_config():
    """Devuelve (token, version, business_id, ad_account_id)."""
    try:
        conf = frappe.get_single("Configuracion Meta")
    except Exception:
        return None, None, None, None
    token = (conf.get_password("access_token", raise_exception=False) or "").strip()
    version = (getattr(conf, "graph_api_version", "") or "v22.0").strip() or "v22.0"
    business_id = (getattr(conf, "business_account_id", "") or "").strip()
    ad_account_id = (getattr(conf, "ad_account_id", "") or "").strip()
    return token, version, business_id, ad_account_id


def _resolve_business_id(token, version, business_id, ad_account_id):
    """Si business_id esta vacio, intenta descubrirlo via el ad_account_id.

    Retorna business_id o None. Nunca levanta excepcion.
    """
    if business_id:
        return business_id
    if not ad_account_id:
        return None
    try:
        data = _graph_get(
            f"{_GRAPH}/{version}/act_{ad_account_id}",
            {"access_token": token, "fields": "business"},
        )
        biz = data.get("business") or {}
        return biz.get("id") or None
    except Exception:
        return None


def _get_chatwoot_config():
    """Devuelve (url, account_id, api_token) desde site_config o SaaS Settings."""
    cfg = frappe.get_site_config()
    url = (cfg.get("chatwoot_url") or "").rstrip("/")
    account_id = str(cfg.get("chatwoot_account_id") or "").strip()
    api_token = (cfg.get("chatwoot_api_token") or "").strip()

    # Fallback a SaaS Settings si existe.
    if not (url and account_id and api_token):
        try:
            saas = frappe.get_cached_doc("SaaS Settings")
            url = url or (getattr(saas, "chatwoot_url", "") or "").rstrip("/")
            account_id = account_id or str(getattr(saas, "chatwoot_account_id", "") or "")
            api_token = api_token or (saas.get_password("chatwoot_api_token", raise_exception=False) or "")
        except Exception:
            pass

    return url, account_id, api_token


def _graph_get(url, params, timeout=15):
    """Wrapper de requests.get contra Graph API con manejo de error uniforme."""
    r = requests.get(url, params=params, timeout=timeout)
    data = r.json() or {}
    if "error" in data:
        raise Exception(data["error"].get("message", "Error Meta"))
    return data


# ─── Endpoints publicos ──────────────────────────────────────────────────

@frappe.whitelist()
def detectar_numeros():
    """Devuelve la lista de numeros WhatsApp accesibles con el token guardado.

    Estructura:
        {
            ok: bool,
            numeros: [
                {phone_number_id, display_phone_number, verified_name,
                 quality_rating, waba_id, waba_name, business_id, business_name}
            ],
            error?: str
        }
    """
    _require_admin()

    token, version, business_id_override, ad_account_id = _get_meta_config()
    if not token:
        return {"ok": False, "error": "Falta Access Token en Configuracion Meta.", "numeros": []}

    # Auto-descubrir business si no esta configurado explicitamente.
    biz_id = _resolve_business_id(token, version, business_id_override, ad_account_id)

    numeros = []
    permisos_error = False

    try:
        # 1. Business Portfolios accesibles. Prioridad: business autodescubierto.
        businesses = []
        if biz_id:
            businesses.append({"id": biz_id, "name": ""})
        else:
            # Fallback: /me/businesses (funciona para user tokens, no system users).
            try:
                data = _graph_get(
                    f"{_GRAPH}/{version}/me/businesses",
                    {"access_token": token, "fields": "id,name", "limit": 100},
                )
                businesses = data.get("data", []) or []
            except Exception:
                pass

        if not businesses:
            return {
                "ok": False,
                "error": (
                    "No se pudo descubrir el Business Portfolio. "
                    "Configura `business_account_id` en /integraciones/meta > Opciones avanzadas, "
                    "o asegurate de que el `ad_account_id` este cargado."
                ),
                "numeros": [],
            }

        for biz in businesses:
            biz_id = biz.get("id")
            biz_name = biz.get("name") or biz_id

            # 2. WABAs del business. Probamos owned + client. Si ambos fallan
            # con 403, marcamos permisos_error para dar un mensaje explicito.
            wabas_data = None
            errores_de_permisos = 0
            for endpoint in ("owned_whatsapp_business_accounts", "client_whatsapp_business_accounts"):
                try:
                    wabas_data = _graph_get(
                        f"{_GRAPH}/{version}/{biz_id}/{endpoint}",
                        {"access_token": token, "fields": "id,name", "limit": 100},
                    )
                    break
                except Exception as e:
                    if "permission" in str(e).lower() or "(#200)" in str(e):
                        errores_de_permisos += 1

            if wabas_data is None:
                if errores_de_permisos >= 2:
                    permisos_error = True
                continue

            for waba in wabas_data.get("data", []) or []:
                waba_id = waba.get("id")
                waba_name = waba.get("name") or waba_id

                # 3. Numeros del WABA.
                try:
                    nums_data = _graph_get(
                        f"{_GRAPH}/{version}/{waba_id}/phone_numbers",
                        {
                            "access_token": token,
                            "fields": "id,display_phone_number,verified_name,quality_rating,code_verification_status",
                            "limit": 100,
                        },
                    )
                except Exception:
                    continue

                for num in nums_data.get("data", []) or []:
                    numeros.append({
                        "phone_number_id": num.get("id"),
                        "display_phone_number": num.get("display_phone_number") or "",
                        "verified_name": num.get("verified_name") or "",
                        "quality_rating": num.get("quality_rating") or "",
                        "code_verification_status": num.get("code_verification_status") or "",
                        "waba_id": waba_id,
                        "waba_name": waba_name,
                        "business_id": biz_id,
                        "business_name": biz_name,
                    })

        # Si no se detectaron numeros y hubo 403s, es problema de permisos.
        if not numeros and permisos_error:
            return {
                "ok": False,
                "error": (
                    "El token de Meta no tiene permisos de WhatsApp. Regenera el token "
                    "en Meta agregando estos scopes: `whatsapp_business_management` y "
                    "`whatsapp_business_messaging` (ademas de los de Ads que ya tienes). "
                    "Luego actualizalo en /integraciones/meta."
                ),
                "numeros": [],
            }

        return {"ok": True, "numeros": numeros}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "whatsapp.detectar_numeros")
        return {"ok": False, "error": str(e)[:400], "numeros": []}


@frappe.whitelist()
def listar_inboxes():
    """Retorna los Inboxes de Chatwoot que son WhatsApp Cloud API.

    Devuelve un dict {phone_number_id: {id, name, phone_number, ...}} para
    facilitar el matching en el frontend.
    """
    _require_admin()

    url, account_id, api_token = _get_chatwoot_config()
    if not (url and account_id and api_token):
        return {"ok": False, "error": "Chatwoot no configurado en el sitio.", "inboxes": {}}

    try:
        r = requests.get(
            f"{url}/api/v1/accounts/{account_id}/inboxes",
            headers={"api_access_token": api_token},
            timeout=10,
        )
        if not r.ok:
            return {"ok": False, "error": f"Chatwoot HTTP {r.status_code}", "inboxes": {}}
        payload = r.json() or {}
        inboxes = payload.get("payload", []) or []
        by_pnid = {}
        for ib in inboxes:
            ch_type = (ib.get("channel_type") or "").lower()
            provider = (ib.get("provider") or "").lower()
            if "whatsapp" not in ch_type:
                continue
            pnid = str(ib.get("phone_number_id") or "").strip()
            if pnid:
                by_pnid[pnid] = {
                    "id": ib.get("id"),
                    "name": ib.get("name"),
                    "phone_number": ib.get("phone_number"),
                    "provider": provider,
                }
        return {"ok": True, "inboxes": by_pnid}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "whatsapp.listar_inboxes")
        return {"ok": False, "error": str(e)[:400], "inboxes": {}}


@frappe.whitelist()
def conectar_inbox(phone_number_id, waba_id, phone_number, nombre_inbox=None, verified_name=None):
    """Crea un Inbox de WhatsApp Cloud en Chatwoot y subscribe el WABA."""
    _require_admin()

    if not (phone_number_id and waba_id and phone_number):
        frappe.throw("phone_number_id, waba_id y phone_number son requeridos.")

    token, version, _bid, _adid = _get_meta_config()
    if not token:
        return {"ok": False, "error": "Falta Access Token en Configuracion Meta."}

    url, account_id, api_token = _get_chatwoot_config()
    if not (url and account_id and api_token):
        return {"ok": False, "error": "Chatwoot no configurado en el sitio."}

    nombre = (nombre_inbox or "").strip() or (verified_name or f"WhatsApp {phone_number[-4:]}")
    verify_token = secrets.token_urlsafe(24)

    # 1. Crear Inbox en Chatwoot.
    payload = {
        "name": nombre,
        "channel": {
            "type": "api",  # Chatwoot exige "api" para casos custom; para
            # WhatsApp Cloud oficial el schema es distinto:
            # se enviamos como whatsapp con provider whatsapp_cloud.
        },
    }
    # Schema real segun docs de Chatwoot para WhatsApp Cloud:
    payload = {
        "name": nombre,
        "channel": {
            "type": "whatsapp",
            "phone_number": phone_number,
            "provider": "whatsapp_cloud",
            "provider_config": {
                "api_key": token,
                "phone_number_id": phone_number_id,
                "business_account_id": waba_id,
                "webhook_verify_token": verify_token,
            },
        },
    }

    try:
        r = requests.post(
            f"{url}/api/v1/accounts/{account_id}/inboxes",
            headers={
                "api_access_token": api_token,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=20,
        )
        if not r.ok:
            return {"ok": False, "error": f"Chatwoot HTTP {r.status_code}: {r.text[:300]}"}
        inbox = r.json() or {}
        inbox_id = inbox.get("id")
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "whatsapp.conectar_inbox chatwoot")
        return {"ok": False, "error": f"Error creando Inbox en Chatwoot: {str(e)[:200]}"}

    # 2. Subscribir la app al WABA en Meta para recibir webhooks.
    try:
        rs = requests.post(
            f"{_GRAPH}/{version}/{waba_id}/subscribed_apps",
            params={"access_token": token},
            timeout=15,
        )
        subscribe_data = rs.json() or {}
        subscribe_ok = bool(subscribe_data.get("success"))
    except Exception:
        subscribe_ok = False

    return {
        "ok": True,
        "inbox_id": inbox_id,
        "nombre": nombre,
        "webhook_subscribed": subscribe_ok,
    }


@frappe.whitelist()
def desconectar_inbox(inbox_id):
    """Elimina el Inbox de Chatwoot."""
    _require_admin()

    if not inbox_id:
        frappe.throw("inbox_id requerido.")

    url, account_id, api_token = _get_chatwoot_config()
    if not (url and account_id and api_token):
        return {"ok": False, "error": "Chatwoot no configurado en el sitio."}

    try:
        r = requests.delete(
            f"{url}/api/v1/accounts/{account_id}/inboxes/{inbox_id}",
            headers={"api_access_token": api_token},
            timeout=15,
        )
        if r.status_code not in (200, 204):
            return {"ok": False, "error": f"Chatwoot HTTP {r.status_code}: {r.text[:300]}"}
        return {"ok": True}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "whatsapp.desconectar_inbox")
        return {"ok": False, "error": str(e)[:200]}
