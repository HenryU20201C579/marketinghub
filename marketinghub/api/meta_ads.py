import frappe
import requests

# Helper centralizado: token Meta proviene de Configuracion Meta (Single per-site).
from marketinghub.marketinghub.doctype.configuracion_meta.configuracion_meta import (
    get_meta_token as _conf_get_meta_token,
    get_meta_ad_account_id as _conf_get_meta_ad_account_id,
)
import json

ADMIN_ROLES = ("Ventahub-Marketing-Administrar",)
VIEW_ROLES = ("Ventahub-Marketing-Ver", "Ventahub-Marketing-Administrar")


def _is_admin():
    roles = set(frappe.get_roles(frappe.session.user))
    return bool(roles.intersection(ADMIN_ROLES))


def _can_view():
    roles = set(frappe.get_roles(frappe.session.user))
    return bool(roles.intersection(VIEW_ROLES))


def _require_view():
    if not _can_view():
        frappe.throw(
            "Acceso denegado. Requiere uno de los roles: "
            + ", ".join(VIEW_ROLES),
            frappe.PermissionError,
        )


def _require_admin():
    if not _is_admin():
        frappe.throw(
            "Acceso denegado. Requiere el rol: "
            + ", ".join(ADMIN_ROLES),
            frappe.PermissionError,
        )


# Subquery que unifica etiquetas de Lead (globales) y Conversacion Chatwoot (per-conversation).
# Retorna (lead_name, etiqueta) para todas las etiquetas de un lead sin importar origen.
# El fieldname del child en tiranidos es `etiqueta` (no `nombre` como Lizaraso).
ALL_TAGS_SUBQUERY = """(
    SELECT E.parent AS lead_name, E.etiqueta AS etiqueta
    FROM `tabEtiqueta Lead Asociado` E
    WHERE E.parenttype = 'Lead'

    UNION

    SELECT CC.lead AS lead_name, E.etiqueta AS etiqueta
    FROM `tabEtiqueta Lead Asociado` E
    JOIN `tabConversacion Chatwoot` CC ON CC.name = E.parent
    WHERE E.parenttype = 'Conversacion Chatwoot'
)"""


# Subquery que deriva Conversacion Chatwoot para un Sales Invoice via el
# telefono del Customer. En tiranidos no existe SI.custom_conversacion_chatwoot,
# asi que la relacion se resuelve via Customer.custom_numero/mobile_no → Lead
# con match de telefono → Conversacion Chatwoot mas reciente.
# Uso: reemplazar cualquier `JOIN tabConversacion Chatwoot CC ON CC.name = SI.custom_conversacion_chatwoot`
# por el JOIN correspondiente a esta subconsulta.
SI_CONV_JOIN = """
    LEFT JOIN `tabCustomer` C ON C.name = SI.customer
    LEFT JOIN `tabLead` L ON (L.mobile_no = C.custom_numero OR L.mobile_no = C.mobile_no)
    LEFT JOIN `tabConversacion Chatwoot` CC ON CC.lead = L.name
"""
# Predicado que reemplaza `SI.custom_conversacion_chatwoot IS NOT NULL`:
SI_HAS_CONV = "CC.name IS NOT NULL"
SI_NO_CONV = "CC.name IS NULL"

@frappe.whitelist()
def get_meta_token():
    _require_view()
    # NO usamos frappe.throw aca: aunque el except lo atrape, Frappe igual
    # acumula el mensaje en frappe.local.message_log y el cliente lo muestra
    # como modal "Mensaje". Los callers ya manejan el caso `if not token:`.
    try:
        return _conf_get_meta_token() or None
    except Exception as e:
        frappe.log_error(f"Error fetching Meta Token: {str(e)}", "Meta Ads API")
        return None

@frappe.whitelist()
def get_ad_accounts():
    _require_view()
    token = get_meta_token()
    if not token:
        return []
    
    url = f"https://graph.facebook.com/v22.0/me/adaccounts"
    params = {
        "access_token": token,
        "fields": "id,name,account_id"
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        frappe.log_error(f"Meta API Error (Accounts): {response.text}", "Meta Ads API")
        return []
    
    return response.json().get("data", [])


@frappe.whitelist()
def get_leads_por_anuncio_meta(ad_meta_id):
    """
    Retorna los leads cuya etiqueta coincide con la etiqueta del Anuncio
    identificado por su meta_id.
    """
    _require_view()
    anuncio = frappe.db.get_value(
        "Anuncio", {"meta_id": ad_meta_id},
        ["name", "nombre", "etiqueta"], as_dict=True
    )
    if not anuncio or not anuncio.etiqueta:
        return {
            "etiqueta": None,
            "anuncio_nombre": anuncio.nombre if anuncio else "",
            "leads": [],
            "total": 0
        }

    leads = frappe.db.sql("""
        SELECT L.name, L.lead_name, L.mobile_no, L.creation,
               L.lead_owner, L.custom_notas, L.status,
               GROUP_CONCAT(DISTINCT AT2.nombre ORDER BY AT2.nombre SEPARATOR ', ') AS etiquetas
        FROM `tabLead` L
        INNER JOIN {all_tags} AT1 ON AT1.lead_name = L.name
        LEFT JOIN {all_tags} AT2 ON AT2.lead_name = L.name
        WHERE AT1.nombre = %(etiqueta)s
        GROUP BY L.name
        ORDER BY L.creation DESC
        LIMIT 500
    """.format(all_tags=ALL_TAGS_SUBQUERY), {"etiqueta": anuncio.etiqueta}, as_dict=True)

    return {
        "etiqueta": anuncio.etiqueta,
        "anuncio_nombre": anuncio.nombre,
        "leads": [dict(l) for l in leads],
        "total": len(leads)
    }

@frappe.whitelist()
def get_lead_counts_por_etiquetas(etiquetas_json, date_from=None, date_to=None):
    """Retorna { etiqueta: count } con el total de leads por etiqueta.
    Filtra por fecha de creación del lead si se proporcionan date_from/date_to.
    """
    _require_view()
    etiquetas = json.loads(etiquetas_json)
    if not etiquetas:
        return {}
    params = {"etiquetas": etiquetas}
    date_filter = ""
    if date_from:
        date_filter += " AND L.creation >= %(date_from)s"
        params["date_from"] = date_from
    if date_to:
        date_filter += " AND L.creation <= %(date_to_end)s"
        params["date_to_end"] = date_to + " 23:59:59"
    rows = frappe.db.sql("""
        SELECT AT.etiqueta AS etiqueta, COUNT(DISTINCT AT.lead_name) AS total
        FROM {all_tags} AT
        JOIN `tabLead` L ON L.name = AT.lead_name
        WHERE AT.etiqueta IN %(etiquetas)s
        {date_filter}
        GROUP BY AT.etiqueta
    """.format(all_tags=ALL_TAGS_SUBQUERY, date_filter=date_filter), params, as_dict=True)
    return {r.etiqueta: r.total for r in rows}

@frappe.whitelist()
def get_filtered_lead_counts(etiquetas_json, mode, row_etiquetas_json, date_from=None, date_to=None):
    """
    Retorna { row_id: count } para cada fila (ad/adset/camp).
    Cuenta leads con al menos 1 factura en el periodo (consistente con Leads Cliente).
    Filtra facturas por posting_date, NO leads por creation date.
    Si mode='OR', leads con AL MENOS UNA de las etiquetas seleccionadas.
    Si mode='AND', leads con TODAS las etiquetas seleccionadas.
    """
    _require_view()
    etiquetas = json.loads(etiquetas_json)
    row_etiquetas = json.loads(row_etiquetas_json)
    if not etiquetas:
        return {rid: 0 for rid in row_etiquetas}

    params = {"etiquetas": etiquetas}

    # Filtra facturas por fecha (posting_date), NO leads por creation
    inv_date_cond = "AND SI.docstatus = 1"
    if date_from:
        inv_date_cond += " AND SI.posting_date >= %(date_from)s"
        params["date_from"] = date_from
    if date_to:
        inv_date_cond += " AND SI.posting_date <= %(date_to)s"
        params["date_to"] = date_to

    # Atribucion por conversacion: buscar leads que tienen facturas
    # vinculadas a conversaciones con las etiquetas correctas
    # O facturas legacy (sin conversacion) del lead con esas etiquetas
    attributed_leads_sql = """
        SELECT DISTINCT lead_name FROM (
            SELECT CC.lead AS lead_name
            FROM `tabSales Invoice` SI
            JOIN `tabCustomer` C ON C.name = SI.customer
                JOIN `tabLead` L ON L.custom_cliente = C.name
            JOIN `tabConversacion Chatwoot` CC ON CC.lead = L.name
            JOIN `tabEtiqueta Lead Asociado` E ON E.parent = CC.name AND E.parenttype = 'Conversacion Chatwoot'
            WHERE SI.docstatus = 1
              AND E.etiqueta IN %(filter_ets)s
              {inv_date_cond}

            UNION

            SELECT L.name AS lead_name
            FROM `tabSales Invoice` SI
            JOIN `tabCustomer` C ON C.name = SI.customer
                JOIN `tabLead` L ON L.custom_cliente = C.name
            JOIN `tabSales Invoice Item` SII ON SII.parent = SI.name
            JOIN `tabEtiqueta Lead Asociado` E ON E.parent = SII.sales_order AND E.parenttype = 'Sales Order'
            WHERE SI.docstatus = 1
              AND EXISTS (SELECT 1 FROM `tabConversacion Chatwoot` CC2 WHERE CC2.lead = L.name)
              AND SII.sales_order IS NOT NULL AND SII.sales_order != ''
              AND E.etiqueta IN %(filter_ets)s
              {inv_date_cond}

            UNION

            SELECT AT.lead_name
            FROM `tabSales Invoice` SI
            JOIN `tabCustomer` C ON C.name = SI.customer
                JOIN `tabLead` L ON L.custom_cliente = C.name
            JOIN {all_tags} AT ON AT.lead_name = L.name
            WHERE SI.docstatus = 1
              AND NOT EXISTS (SELECT 1 FROM `tabConversacion Chatwoot` CC2 WHERE CC2.lead = L.name)
              AND AT.etiqueta IN %(filter_ets)s
              {inv_date_cond}
        ) attr
    """.format(all_tags=ALL_TAGS_SUBQUERY, inv_date_cond=inv_date_cond)

    if mode == 'OR':
        lead_rows = frappe.db.sql(
            attributed_leads_sql.replace("%(filter_ets)s", "%(etiquetas)s"),
            params, as_dict=True)
        lead_names = set(r.lead_name for r in lead_rows)
    else:
        # AND mode: lead must appear for ALL etiquetas
        lead_counts = {}
        for et in etiquetas:
            et_params = {"filter_ets": [et]}
            if date_from:
                et_params["date_from"] = date_from
            if date_to:
                et_params["date_to"] = date_to
            rows = frappe.db.sql(attributed_leads_sql, et_params, as_dict=True)
            for r in rows:
                lead_counts[r.lead_name] = lead_counts.get(r.lead_name, 0) + 1
        lead_names = {ln for ln, cnt in lead_counts.items() if cnt >= len(etiquetas)}

    # Para cada fila, contar cuántos de esos leads-cliente están asociados a sus etiquetas
    result = {}
    for row_id, row_ets in row_etiquetas.items():
        if not row_ets:
            result[row_id] = 0
            continue
        row_params = {"filter_ets": row_ets}
        if date_from:
            row_params["date_from"] = date_from
        if date_to:
            row_params["date_to"] = date_to
        matching_leads = frappe.db.sql(attributed_leads_sql, row_params, as_dict=True)
        count = sum(1 for r in matching_leads if r.lead_name in lead_names)
        result[row_id] = count

    return result

@frappe.whitelist()
def get_sales_data_por_etiquetas(etiquetas_json, date_from=None, date_to=None):
    """
    Retorna { etiqueta: { ventas: N, ingresos: float } } para cada etiqueta.
    ventas  = leads que tienen al menos 1 factura (via Customer vinculado).
    ingresos = SUM(grand_total) de Sales Invoice del Customer vinculado al lead.
    Si date_from/date_to se proporcionan, solo cuenta facturas en ese rango.

    Atribucion por conversacion: si la factura tiene custom_conversacion_chatwoot,
    solo matchea etiquetas de esa conversacion (+ globales). Si no, usa todas.
    """
    _require_view()
    etiquetas = json.loads(etiquetas_json)
    if not etiquetas:
        return {}

    params = {"etiquetas": etiquetas}

    inv_date_filter = "AND SI.docstatus = 1"
    if date_from:
        inv_date_filter += " AND SI.posting_date >= %(date_from)s"
        params["date_from"] = date_from
    if date_to:
        inv_date_filter += " AND SI.posting_date <= %(date_to)s"
        params["date_to"] = date_to

    # Atribucion por conversacion:
    # - Factura CON custom_conversacion_chatwoot → solo cuenta para etiquetas de ESA conversacion
    # - Factura SIN custom_conversacion_chatwoot (legacy) → cuenta para todas las etiquetas del lead
    rows = frappe.db.sql("""
        SELECT etiqueta,
               COUNT(DISTINCT lead_name) AS ventas,
               COALESCE(SUM(total), 0) AS ingresos
        FROM (
            SELECT tag_nombre AS etiqueta, lead_name,
                   SUM(grand_total) AS total
            FROM (
                SELECT DISTINCT SI.name AS si_name, E.etiqueta AS tag_nombre,
                       CC.lead AS lead_name, SI.grand_total
                FROM `tabSales Invoice` SI
                JOIN `tabCustomer` C ON C.name = SI.customer
                JOIN `tabLead` L ON L.custom_cliente = C.name
                JOIN `tabConversacion Chatwoot` CC ON CC.lead = L.name
                JOIN `tabEtiqueta Lead Asociado` E ON E.parent = CC.name AND E.parenttype = 'Conversacion Chatwoot'
                WHERE SI.docstatus = 1
                  AND E.etiqueta IN %(etiquetas)s
                  {inv_date_filter}

                UNION

                SELECT DISTINCT SI.name AS si_name, E.etiqueta AS tag_nombre,
                       L.name AS lead_name, SI.grand_total
                FROM `tabSales Invoice` SI
                JOIN `tabCustomer` C ON C.name = SI.customer
                JOIN `tabLead` L ON L.custom_cliente = C.name
                JOIN `tabSales Invoice Item` SII ON SII.parent = SI.name
                JOIN `tabEtiqueta Lead Asociado` E ON E.parent = SII.sales_order AND E.parenttype = 'Sales Order'
                WHERE SI.docstatus = 1
                  AND EXISTS (SELECT 1 FROM `tabConversacion Chatwoot` CC2 WHERE CC2.lead = L.name)
                  AND SII.sales_order IS NOT NULL AND SII.sales_order != ''
                  AND E.etiqueta IN %(etiquetas)s
                  {inv_date_filter}

                UNION

                SELECT DISTINCT SI.name AS si_name, AT.etiqueta AS tag_nombre,
                       AT.lead_name, SI.grand_total
                FROM `tabSales Invoice` SI
                JOIN `tabCustomer` C ON C.name = SI.customer
                JOIN `tabLead` L ON L.custom_cliente = C.name
                JOIN {all_tags} AT ON AT.lead_name = L.name
                WHERE SI.docstatus = 1
                  AND NOT EXISTS (SELECT 1 FROM `tabConversacion Chatwoot` CC2 WHERE CC2.lead = L.name)
                  AND AT.etiqueta IN %(etiquetas)s
                  {inv_date_filter}
            ) deduplicated
            GROUP BY tag_nombre, lead_name
        ) attribution
        GROUP BY etiqueta
    """.format(all_tags=ALL_TAGS_SUBQUERY, inv_date_filter=inv_date_filter), params, as_dict=True)
    return {r.etiqueta: {"ventas": int(r.ventas), "ingresos": float(r.ingresos)} for r in rows}

@frappe.whitelist()
def get_all_lead_etiquetas():
    """Retorna lista de todas las etiquetas únicas que tienen leads asignados."""
    _require_view()
    rows = frappe.db.sql("""
        SELECT DISTINCT E.etiqueta
        FROM `tabEtiqueta Lead Asociado` E
        WHERE E.etiqueta IS NOT NULL AND E.etiqueta != ''
        ORDER BY E.etiqueta
    """, as_dict=True)
    return [r.etiqueta for r in rows]

@frappe.whitelist()
def sincronizar_campanas(account_id):
    """
    Sincroniza campañas, conjuntos de anuncios y anuncios desde Meta API
    al ERP usando meta_id como clave de upsert.
    Retorna { creadas, actualizadas, omitidas, errores }
    """
    _require_admin()
    token = get_meta_token()
    if not token:
        frappe.throw("No se encontró el token de Meta")

    stats = {"creadas": 0, "actualizadas": 0, "omitidas": 0, "errores": []}

    # ─── 1. Upsert Cuenta Publicitaria ───
    cuenta_name = _upsert_cuenta(account_id, token)

    # ─── 2. Obtener campañas con paginación ───
    campaigns = _fetch_all(
        f"https://graph.facebook.com/v22.0/act_{account_id}/campaigns",
        {"fields": "id,name,effective_status", "limit": 500},
        token
    )

    # ─── 3. Obtener conjuntos con paginación ───
    adsets = _fetch_all(
        f"https://graph.facebook.com/v22.0/act_{account_id}/adsets",
        {"fields": "id,name,campaign_id,effective_status,daily_budget,lifetime_budget", "limit": 500},
        token
    )

    # ─── 4. Obtener anuncios con paginación ───
    ads = _fetch_all(
        f"https://graph.facebook.com/v22.0/act_{account_id}/ads",
        {"fields": "id,name,adset_id,effective_status", "limit": 500},
        token
    )

    # Índices por ID
    adsets_by_campaign = {}
    for adset in adsets:
        adsets_by_campaign.setdefault(adset["campaign_id"], []).append(adset)

    ads_by_adset = {}
    for ad in ads:
        ads_by_adset.setdefault(ad["adset_id"], []).append(ad)

    # ─── 5. Upsert de cada campaña ───
    for camp in campaigns:
        try:
            campana_name = _upsert_campana(camp, cuenta_name, adsets_by_campaign, ads_by_adset, stats)
        except Exception as e:
            stats["errores"].append(f"Campaña '{camp.get('name')}': {str(e)}")

    frappe.db.commit()
    return stats


def _fetch_all(url, params, token):
    """Llama a la URL con paginación y retorna todos los items."""
    import requests
    items = []
    params = dict(params, access_token=token)
    while url:
        res = requests.get(url, params=params)
        data = res.json()
        if data.get("error"):
            frappe.throw(f"Meta API error: {data['error'].get('message')}")
        items.extend(data.get("data", []))
        url = data.get("paging", {}).get("next")
        params = {}  # el cursor 'next' ya incluye todos los params
    return items


def _upsert_cuenta(account_id, token):
    """Crea o actualiza una Cuenta Publicitaria. Retorna el name del doc."""
    import requests
    existing = frappe.db.get_value("Cuenta Publicitaria", {"meta_id": account_id}, "name")
    if existing:
        return existing

    # Obtener nombre de la cuenta desde Meta
    res = requests.get(
        f"https://graph.facebook.com/v22.0/act_{account_id}",
        params={"fields": "name", "access_token": token}
    )
    account_name = res.json().get("name", f"Cuenta {account_id}")

    # Si ya existe por nombre, actualizar meta_id
    by_nombre = frappe.db.get_value("Cuenta Publicitaria", {"nombre": account_name}, "name")
    if by_nombre:
        frappe.db.set_value("Cuenta Publicitaria", by_nombre, "meta_id", account_id)
        return by_nombre

    doc = frappe.new_doc("Cuenta Publicitaria")
    doc.nombre = account_name
    doc.meta_id = account_id
    doc.insert(ignore_permissions=True)
    return doc.name


_ESTADO_CAMPANA  = {"ACTIVE", "PAUSED", "DELETED", "ARCHIVED", "IN_PROCESS", "WITH_ISSUES", "DISAPPROVED"}
_ESTADO_CONJUNTO = {"ACTIVE", "PAUSED", "CAMPAIGN_PAUSED", "DELETED", "ARCHIVED", "IN_PROCESS", "WITH_ISSUES", "DISAPPROVED"}
_ESTADO_ANUNCIO  = {"ACTIVE", "PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED", "DELETED", "ARCHIVED", "IN_PROCESS", "WITH_ISSUES", "DISAPPROVED"}

def _safe_estado(valor, validos):
    """Devuelve el estado si es válido, vacío si no lo reconoce."""
    return valor if valor in validos else ""


def _upsert_campana(camp, cuenta_name, adsets_by_campaign, ads_by_adset, stats):
    """Upsert de Campana Meta y sus hijos. Retorna el name del doc."""
    camp_meta_id = camp["id"]
    camp_nombre = camp["name"]
    camp_estado = _safe_estado(camp.get("effective_status", ""), _ESTADO_CAMPANA)

    # 1. Buscar por meta_id (ya vinculado)
    existing_name = frappe.db.get_value("Campana Meta", {"meta_id": camp_meta_id}, "name")

    if not existing_name:
        # 2. Buscar por campo nombre (creado manualmente, aún sin meta_id)
        by_nombre = frappe.db.get_value(
            "Campana Meta",
            {"nombre": camp_nombre},
            ["name", "meta_id"],
            as_dict=True
        )
        if by_nombre:
            if by_nombre.meta_id and by_nombre.meta_id != camp_meta_id:
                # Ya vinculado a otro ID de Meta — genuinamente distinto, omitir
                stats["omitidas"] += 1
                stats["errores"].append(
                    f"Campaña '{camp_nombre}': ya vinculada a meta_id '{by_nombre.meta_id}' — omitida"
                )
                return by_nombre.name
            # Sin meta_id → vincular el registro existente
            existing_name = by_nombre.name

    if existing_name:
        doc = frappe.get_doc("Campana Meta", existing_name)
        # Si el nombre cambió y el doc usa naming viejo (name == nombre), renombrar
        if doc.nombre != camp_nombre and doc.name == doc.nombre:
            frappe.rename_doc("Campana Meta", existing_name, camp_nombre, merge=False)
            doc = frappe.get_doc("Campana Meta", camp_nombre)
            existing_name = camp_nombre
        doc.nombre = camp_nombre
        doc.meta_id = camp_meta_id
        doc.estado = camp_estado
        doc.cuenta_publicitaria = cuenta_name
        doc.conjunto_anuncios_asociados = []
        stats["actualizadas"] += 1
    else:
        doc = frappe.new_doc("Campana Meta")
        doc.nombre = camp_nombre
        doc.meta_id = camp_meta_id
        doc.estado = camp_estado
        doc.cuenta_publicitaria = cuenta_name
        stats["creadas"] += 1

    for adset in adsets_by_campaign.get(camp_meta_id, []):
        conj_name = _upsert_conjunto(adset, ads_by_adset, stats)
        doc.append("conjunto_anuncios_asociados", {"conjunto_anuncios": conj_name})

    if existing_name:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    return doc.name


def _upsert_conjunto(adset, ads_by_adset, stats):
    """Upsert de Conjunto Anuncios y sus anuncios hijos. Retorna el name del doc."""
    adset_meta_id = adset["id"]
    adset_nombre = adset["name"]
    adset_estado = _safe_estado(adset.get("effective_status", ""), _ESTADO_CONJUNTO)
    budget = adset.get("daily_budget") or adset.get("lifetime_budget") or 0
    try:
        budget = float(budget) / 100
    except Exception:
        budget = 0

    # 1. Buscar por meta_id
    existing_name = frappe.db.get_value("Conjunto Anuncios", {"meta_id": adset_meta_id}, "name")

    if not existing_name:
        # 2. Buscar por nombre sin meta_id (creado manualmente)
        unlinked = frappe.db.get_value(
            "Conjunto Anuncios",
            [["nombre", "=", adset_nombre], ["meta_id", "in", ["", None]]],
            "name"
        )
        if unlinked:
            existing_name = unlinked

    if existing_name:
        doc = frappe.get_doc("Conjunto Anuncios", existing_name)
        doc.nombre = adset_nombre
        doc.meta_id = adset_meta_id
        doc.estado = adset_estado
        doc.valor = budget
        doc.anuncios_asociados = []
    else:
        doc = frappe.new_doc("Conjunto Anuncios")
        doc.nombre = adset_nombre
        doc.meta_id = adset_meta_id
        doc.estado = adset_estado
        doc.valor = budget

    for ad in ads_by_adset.get(adset_meta_id, []):
        an_name = _upsert_anuncio(ad)
        doc.append("anuncios_asociados", {"anuncios": an_name})

    if existing_name:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    return doc.name


def _upsert_anuncio(ad):
    """Upsert de Anuncio (sin tocar etiqueta). Retorna el name del doc."""
    ad_meta_id = ad["id"]
    ad_nombre = ad["name"]
    ad_estado = _safe_estado(ad.get("effective_status", ""), _ESTADO_ANUNCIO)

    # 1. Buscar por meta_id
    existing_name = frappe.db.get_value("Anuncio", {"meta_id": ad_meta_id}, "name")

    if not existing_name:
        # 2. Buscar por nombre sin meta_id
        unlinked = frappe.db.get_value(
            "Anuncio",
            [["nombre", "=", ad_nombre], ["meta_id", "in", ["", None]]],
            "name"
        )
        if unlinked:
            existing_name = unlinked

    if existing_name:
        frappe.db.set_value("Anuncio", existing_name, {
            "nombre": ad_nombre,
            "meta_id": ad_meta_id,
            "estado": ad_estado
        })
        return existing_name

    doc = frappe.new_doc("Anuncio")
    doc.nombre = ad_nombre
    doc.meta_id = ad_meta_id
    doc.estado = ad_estado
    # etiqueta NO se toca — asignación manual interna
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def get_row_detail(etiquetas_json, date_from=None, date_to=None, filter_lead_creation=0):
    """
    Retorna detalle completo de leads/clientes/facturas para las etiquetas de una fila.
    filter_lead_creation=1: filtra leads por fecha de creación (para coherencia con columna Leads ERP).
    Las fechas también se usan para filtrar facturas por posting_date.
    """
    _require_view()
    etiquetas = json.loads(etiquetas_json)
    if not etiquetas:
        return []

    filter_lead_creation = int(filter_lead_creation)
    params = {"etiquetas": etiquetas}

    # 1. Obtener leads con esas etiquetas
    lead_date_filter = ""
    if filter_lead_creation and date_from:
        lead_date_filter += " AND L.creation >= %(date_from)s"
        params["date_from"] = date_from
    if filter_lead_creation and date_to:
        lead_date_filter += " AND L.creation <= %(date_to_end)s"
        params["date_to_end"] = date_to + " 23:59:59"

    leads = frappe.db.sql("""
        SELECT
            L.name, L.lead_name, L.mobile_no, L.creation,
            L.lead_owner, L.custom_notas, L.status, L.custom_estado,
            GROUP_CONCAT(DISTINCT AT2.etiqueta ORDER BY AT2.etiqueta SEPARATOR ', ') AS etiquetas
        FROM `tabLead` L
        INNER JOIN {all_tags} AT1 ON AT1.lead_name = L.name
        LEFT JOIN {all_tags} AT2 ON AT2.lead_name = L.name
        WHERE AT1.etiqueta IN %(etiquetas)s
        {lead_date_filter}
        GROUP BY L.name
        ORDER BY L.creation DESC
    """.format(all_tags=ALL_TAGS_SUBQUERY, lead_date_filter=lead_date_filter), params, as_dict=True)

    # 2. Para leads que son clientes, obtener TODOS los customers vinculados.
    # En Tiranidos el vinculo es Lead.custom_cliente → Customer.name (invertido vs Lizaraso).
    lead_names = [l.name for l in leads]
    customer_map = {}  # lead_name -> [list of customers]
    if lead_names:
        customers = frappe.db.sql("""
            SELECT C.name AS customer_name, C.customer_name AS customer_label,
                   L.name AS lead_name
            FROM `tabLead` L
            JOIN `tabCustomer` C ON C.name = L.custom_cliente
            WHERE L.name IN %(lead_names)s
        """, {"lead_names": lead_names}, as_dict=True)
        for c in customers:
            customer_map.setdefault(c.lead_name, []).append(c)

    # 3. Obtener facturas atribuidas a estas etiquetas (coherente con get_sales_data_por_etiquetas)
    # - Facturas CON conversacion: solo si la conversacion tiene alguna de las etiquetas
    # - Facturas SIN conversacion (legacy): siempre incluidas
    customer_names = [c.customer_name for custs in customer_map.values() for c in custs]
    invoice_map = {}
    if customer_names:
        inv_date_filter = ""
        inv_params = {"customers": customer_names, "etiquetas": etiquetas}
        if date_from:
            inv_date_filter += " AND SI.posting_date >= %(date_from)s"
            inv_params["date_from"] = date_from
        if date_to:
            inv_date_filter += " AND SI.posting_date <= %(date_to)s"
            inv_params["date_to"] = date_to

        invoices = frappe.db.sql("""
            SELECT SI.name, SI.customer, SI.customer_name, SI.posting_date,
                   SI.grand_total, SI.outstanding_amount, SI.status, SI.docstatus
            FROM `tabSales Invoice` SI
            LEFT JOIN `tabLead` L ON L.custom_cliente = SI.customer
            WHERE SI.customer IN %(customers)s
              AND SI.docstatus = 1
              AND (
                  L.name IS NULL
                  OR EXISTS (
                      SELECT 1 FROM `tabEtiqueta Lead Asociado` E
                      JOIN `tabConversacion Chatwoot` CC ON CC.name = E.parent
                      WHERE CC.lead = L.name
                        AND E.parenttype = 'Conversacion Chatwoot'
                        AND E.etiqueta IN %(etiquetas)s
                  )
                  OR EXISTS (
                      SELECT 1 FROM `tabEtiqueta Lead Asociado` E
                      WHERE E.parent = L.name AND E.parenttype = 'Lead'
                        AND E.etiqueta IN %(etiquetas)s
                  )
                  OR EXISTS (
                      SELECT 1 FROM `tabSales Invoice Item` SII
                      JOIN `tabEtiqueta Lead Asociado` E ON E.parent = SII.sales_order
                        AND E.parenttype = 'Sales Order'
                      WHERE SII.parent = SI.name
                        AND SII.sales_order IS NOT NULL AND SII.sales_order != ''
                        AND E.etiqueta IN %(etiquetas)s
                  )
              )
              {inv_date_filter}
            ORDER BY SI.posting_date DESC
        """.format(inv_date_filter=inv_date_filter), inv_params, as_dict=True)

        # Obtener items de cada factura
        inv_names = [inv.name for inv in invoices]
        items_map = {}
        if inv_names:
            items = frappe.db.sql("""
                SELECT parent, item_name, qty, rate, amount
                FROM `tabSales Invoice Item`
                WHERE parent IN %(inv_names)s
                ORDER BY idx
            """, {"inv_names": inv_names}, as_dict=True)
            for item in items:
                items_map.setdefault(item.parent, []).append({
                    "item_name": item.item_name,
                    "qty": float(item.qty),
                    "rate": float(item.rate),
                    "amount": float(item.amount)
                })

        for inv in invoices:
            grand_total = float(inv.grand_total or 0)
            outstanding = float(inv.outstanding_amount or 0)
            if outstanding <= 0:
                pago_estado = "Pagado"
            elif outstanding < grand_total:
                pago_estado = "Parcial"
            else:
                pago_estado = "Pendiente"

            inv_data = {
                "name": inv.name,
                "cliente": inv.customer_name or inv.customer,
                "fecha": str(inv.posting_date),
                "total": grand_total,
                "pendiente": outstanding,
                "pago_estado": pago_estado,
                "status": inv.status,
                "items": items_map.get(inv.name, [])
            }
            invoice_map.setdefault(inv.customer, []).append(inv_data)

    # 4. Armar respuesta final
    result = []
    for lead in leads:
        custs = customer_map.get(lead.name, [])
        # Agregar facturas de TODOS los customers vinculados al lead (maneja duplicados)
        all_facturas = []
        customer_label = None
        for c in custs:
            if not customer_label:
                customer_label = c.customer_label
            all_facturas.extend(invoice_map.get(c.customer_name, []))
        es_cliente = len(all_facturas) > 0
        entry = {
            "lead_name": lead.name,
            "nombre": lead.lead_name,
            "telefono": lead.mobile_no,
            "creacion": str(lead.creation),
            "responsable": lead.lead_owner,
            "notas": lead.custom_notas,
            "status": lead.status,
            "estado_erp": lead.custom_estado,
            "etiquetas": lead.etiquetas or "",
            "chatwoot_id": "",
            "es_cliente": es_cliente,
            "customer_name": customer_label,
            "facturas": all_facturas
        }
        result.append(entry)

    # Resolver chatwoot_id para cada lead
    from ventahub.lizaraso.doctype.conversacion_chatwoot.conversacion_chatwoot import get_active_conversation_id
    for entry in result:
        conv_id = get_active_conversation_id(entry["lead_name"])
        entry["chatwoot_id"] = str(conv_id) if conv_id else ""

    return result


@frappe.whitelist()
def get_page_posts(page_id=None):
    """
    Reads statistics for page posts (organic and boosted)
    """
    _require_view()
    token = get_meta_token()
    if not token:
        return []
    
    # If no page_id provided, try to find one from accounts or use 'me/accounts'
    if not page_id:
        res = requests.get(f"https://graph.facebook.com/v22.0/me/accounts", params={"access_token": token})
        pages = res.json().get("data", [])
        if pages:
            page_id = pages[0]["id"]
            # Page tokens are often needed for insights, but if the user provided a System User token with appropriate scopes, it might work.
            # Using the main token for now.
        else:
            frappe.throw("No se encontraron páginas asociadas a este token.")

    url = f"https://graph.facebook.com/v22.0/{page_id}/posts"
    params = {
        "access_token": token,
        "fields": "id,message,created_time,shares,comments.summary(true),likes.summary(true),insights.metric(post_impressions,post_engagements,post_clicks_by_type_unique)"
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        frappe.log_error(f"Meta API Error (Posts): {response.text}", "Meta Ads API")
        return []

    return response.json().get("data", [])


# ─── Chat Reconstruction (delegates to lead_button) ───

@frappe.whitelist()
def get_conversation(lead_name):
    """Obtiene todos los comentarios de WhatsApp de un Lead."""
    _require_view()
    from marketinghub.api.lead.lead_button import obtener_conversacion
    return obtener_conversacion(lead_name)


# ─── CTWA: helper para enriquecer Anuncio desde Graph API ─────────────


def resolver_post_id_de_ad(ad_meta_id, token=None):
    """Consulta Graph API para obtener nombre + estado + post_id de un ad por meta_id.

    Se usa cuando recibimos un ad_id desde Click-to-WhatsApp (referral) y el
    Anuncio aun no fue sincronizado. Retorna None si falla o no hay token.
    """
    if not ad_meta_id:
        return None
    if not token:
        try:
            token = _conf_get_meta_token()
        except Exception:
            token = None
    if not token:
        return None
    try:
        res = requests.get(
            f"https://graph.facebook.com/v22.0/{ad_meta_id}",
            params={
                "fields": "name,effective_status,creative{effective_object_story_id}",
                "access_token": token,
            },
            timeout=10,
        )
        if res.status_code != 200:
            return None
        data = res.json()
        creative = data.get("creative") or {}
        return {
            "name": data.get("name"),
            "estado": data.get("effective_status"),
            "post_id": creative.get("effective_object_story_id"),
        }
    except Exception as e:
        frappe.log_error(
            f"resolver_post_id_de_ad {ad_meta_id}: {e}", "Meta Ads API"
        )
        return None
