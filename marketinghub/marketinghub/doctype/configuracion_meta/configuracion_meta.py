import frappe
from frappe.model.document import Document


class ConfiguracionMeta(Document):
    pass


def _get_doc():
    try:
        return frappe.get_single("Configuracion Meta")
    except Exception:
        return None


def get_meta_token():
    doc = _get_doc()
    if not doc:
        return None
    try:
        return doc.get_password("access_token", raise_exception=False) or None
    except Exception:
        return None


def get_meta_pixel_id():
    doc = _get_doc()
    return doc.pixel_id if doc and doc.pixel_id else None


def get_meta_capi_token():
    doc = _get_doc()
    if not doc:
        return None
    try:
        return doc.get_password("capi_token", raise_exception=False) or None
    except Exception:
        return None


def get_meta_ad_account_id():
    doc = _get_doc()
    return doc.ad_account_id if doc and doc.ad_account_id else None


def get_graph_api_version():
    doc = _get_doc()
    return (doc.graph_api_version if doc and doc.graph_api_version else "v22.0")


def is_enabled():
    doc = _get_doc()
    return bool(doc and doc.habilitado)


def is_capi_enabled():
    doc = _get_doc()
    return bool(doc and doc.capi_enabled)
