import frappe
from marketinghub.marketinghub.doctype.configuracion_meta.configuracion_meta import (
    get_meta_token as _conf_get_meta_token,
    get_meta_ad_account_id as _conf_get_meta_ad_account_id,
)
from frappe import _

ADMIN_ROLES = ("Ventahub-Marketing-Ver", "Ventahub-Marketing-Administrar")
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


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/campanas_meta"
        raise frappe.Redirect

    context.no_cache = 1
    context.title = "Gestión de Campañas Meta"
    context.no_access = not _can_view()
    context.required_roles = list(VIEW_ROLES)
    context.can_edit = _is_admin()


def check_edit_permission():
    _require_admin()


@frappe.whitelist()
def obtener_campanas():
    """Retorna todas las Campanas Meta con sus conjuntos y anuncios anidados"""
    _require_view()
    campanas = frappe.get_all("Campana Meta", fields=["name", "nombre"])
    resultado = []
    for campana in campanas:
        doc = frappe.get_doc("Campana Meta", campana.name)
        conjuntos = []
        for row in doc.conjunto_anuncios_asociados or []:
            conj_doc = frappe.get_doc("Conjunto Anuncios", row.conjunto_anuncios)
            anuncios = []
            for a_row in conj_doc.anuncios_asociados or []:
                anuncio = frappe.get_doc("Anuncio", a_row.anuncios)
                anuncios.append({
                    "name": anuncio.name,
                    "nombre": anuncio.nombre,
                    "etiqueta": anuncio.etiqueta,
                    "meta_id": anuncio.meta_id or ""
                })
            conjuntos.append({
                "name": conj_doc.name,
                "nombre": conj_doc.nombre,
                "valor": conj_doc.valor,
                "meta_id": conj_doc.meta_id or "",
                "anuncios": anuncios
            })
        resultado.append({
            "name": doc.name,
            "nombre": doc.nombre,
            "objetivo": doc.objetivo or "",
            "meta_id": doc.meta_id or "",
            "estado": doc.estado or "",
            "cuenta_publicitaria": doc.cuenta_publicitaria or "",
            "conjuntos": conjuntos
        })
    return resultado


@frappe.whitelist()
def guardar_campana(nombre, conjuntos_json, objetivo="", nombre_original=""):
    """Crea o edita una Campana Meta con sus conjuntos asociados"""
    check_edit_permission()
    import json
    conjuntos = json.loads(conjuntos_json)
    log = []  # log detallado de operaciones
    cambios = {"campana": False, "conjuntos": set(), "anuncios": set()}  # tracking de cambios

    # nombre_original es el `name` (ID) del doc existente en modo edición
    doc_id = nombre_original.strip() if nombre_original and nombre_original.strip() else ""

    if doc_id and frappe.db.exists("Campana Meta", doc_id):
        doc = frappe.get_doc("Campana Meta", doc_id)
        if doc.nombre != nombre:
            log.append({"tipo": "ok", "msg": f"Campaña renombrada: '{doc.nombre}' → '{nombre}'"})
            cambios["campana"] = True
        else:
            log.append({"tipo": "ok", "msg": f"Campaña sin cambios de nombre"})
        doc.nombre = nombre
        doc.conjunto_anuncios_asociados = []
    else:
        doc = frappe.new_doc("Campana Meta")
        doc.nombre = nombre
        log.append({"tipo": "ok", "msg": f"Campaña creada: '{nombre}'"})
        cambios["campana"] = True

    doc.objetivo = objetivo or ""

    for conj in conjuntos:
        conj_nombre = conj.get("nombre", "")
        try:
            if conj.get("name") and frappe.db.exists("Conjunto Anuncios", conj["name"]):
                conj_doc = frappe.get_doc("Conjunto Anuncios", conj["name"])
                nombre_anterior = conj_doc.nombre
                conj_doc.nombre = conj_nombre
                conj_doc.valor = conj.get("valor", 0)
                conj_doc.anuncios_asociados = []
                if nombre_anterior != conj_nombre:
                    log.append({"tipo": "ok", "msg": f"Conjunto renombrado: '{nombre_anterior}' → '{conj_nombre}'"})
                    cambios["conjuntos"].add(conj["name"])
            else:
                conj_doc = frappe.new_doc("Conjunto Anuncios")
                conj_doc.nombre = conj_nombre
                conj_doc.valor = conj.get("valor", 0)
                log.append({"tipo": "ok", "msg": f"Conjunto creado: '{conj_nombre}'"})
        except Exception as e:
            log.append({"tipo": "error", "msg": f"Error en conjunto '{conj_nombre}': {str(e)}"})
            continue

        for anuncio in conj.get("anuncios", []):
            an_nombre = anuncio.get("nombre", "")
            try:
                if anuncio.get("name") and frappe.db.exists("Anuncio", anuncio["name"]):
                    an_doc = frappe.get_doc("Anuncio", anuncio["name"])
                    nombre_anterior = an_doc.nombre
                    an_doc.nombre = an_nombre
                    an_doc.etiqueta = anuncio.get("etiqueta", "") or None
                    an_doc.save(ignore_permissions=True)
                    if nombre_anterior != an_nombre:
                        log.append({"tipo": "ok", "msg": f"Anuncio renombrado: '{nombre_anterior}' → '{an_nombre}'"})
                        cambios["anuncios"].add(anuncio["name"])
                else:
                    an_doc = frappe.new_doc("Anuncio")
                    an_doc.nombre = an_nombre
                    an_doc.etiqueta = anuncio.get("etiqueta", "") or None
                    an_doc.insert(ignore_permissions=True)
                    log.append({"tipo": "ok", "msg": f"Anuncio creado: '{an_nombre}'"})
            except Exception as e:
                log.append({"tipo": "error", "msg": f"Error en anuncio '{an_nombre}': {str(e)}"})
                continue

            conj_doc.append("anuncios_asociados", {"anuncios": an_doc.name})

        try:
            if conj.get("name") and frappe.db.exists("Conjunto Anuncios", conj["name"]):
                conj_doc.save(ignore_permissions=True)
            else:
                conj_doc.insert(ignore_permissions=True)
        except Exception as e:
            log.append({"tipo": "error", "msg": f"Error al guardar conjunto '{conj_nombre}': {str(e)}"})
            continue

        doc.append("conjunto_anuncios_asociados", {"conjunto_anuncios": conj_doc.name})

    try:
        if doc.name and frappe.db.exists("Campana Meta", doc.name):
            doc.save(ignore_permissions=True)
        else:
            doc.insert(ignore_permissions=True)
        frappe.db.commit()
    except Exception as e:
        log.append({"tipo": "error", "msg": f"Error al guardar campaña: {str(e)}"})
        return {"status": "error", "log": log}

    # Solo sincronizar con Meta lo que realmente cambió de nombre
    if cambios["campana"] or cambios["conjuntos"] or cambios["anuncios"]:
        meta_log = _sync_nombres_meta(doc, conjuntos, cambios)
        log.extend(meta_log)
    else:
        log.append({"tipo": "ok", "msg": "Sin cambios de nombre — no se envió nada a Meta"})

    return {"status": "ok", "name": doc.name, "log": log}


def _sync_nombres_meta(campana_doc, conjuntos, cambios):
    """Propaga cambios de nombre al ERP → Meta API. Solo envía lo que cambió. Retorna lista de logs [{tipo, msg}]."""
    import requests
    log = []
    try:
        token = _conf_get_meta_token()
        if not token:
            log.append({"tipo": "warn", "msg": "Meta: sin token configurado, no se sincronizó con Meta"})
            return log

        # Obtener account_id para URLs de Meta Ads Manager
        account_id = ""
        if campana_doc.cuenta_publicitaria:
            account_id = frappe.db.get_value("Cuenta Publicitaria", campana_doc.cuenta_publicitaria, "meta_id") or ""

        def _post_nombre(meta_id, nombre, etiqueta, es_anuncio=False):
            try:
                if es_anuncio:
                    # Verificar estado del Ad antes de intentar renombrar
                    get_res = requests.get(
                        f"https://graph.facebook.com/v22.0/{meta_id}",
                        params={"fields": "name,effective_status", "access_token": token},
                        timeout=10
                    ).json()
                    if "error" in get_res:
                        error_msg = get_res['error'].get('message', 'Error')
                        error_code = get_res['error'].get('code', '')
                        log.append({"tipo": "error", "msg": f"Meta {etiqueta}: [{error_code}] {error_msg}"})
                        return
                    status = get_res.get("effective_status", "")
                    if status in ("DELETED", "ARCHIVED"):
                        log.append({"tipo": "warn", "msg": f"Meta {etiqueta}: estado '{status}', no se puede renombrar"})
                        return

                res = requests.post(
                    f"https://graph.facebook.com/v22.0/{meta_id}",
                    data={"name": nombre, "access_token": token},
                    timeout=10
                ).json()
                if "error" in res:
                    error_msg = res['error'].get('message', 'Error')
                    error_code = res['error'].get('code', '')
                    error_sub = res['error'].get('error_subcode', '')
                    detail = f"[{error_code}] {error_msg}"
                    if error_sub:
                        detail += f" (subcode:{error_sub})"
                    if es_anuncio and str(error_code) == "100":
                        ads_url = f"https://adsmanager.facebook.com/adsmanager/manage/ads/edit?act={account_id}&selected_ad_ids={meta_id}" if account_id else ""
                        error_user = res['error'].get('error_user_title', '')
                        motivo = f" ({error_user})" if error_user else ""
                        log.append({"tipo": "warn", "msg": f"Meta {etiqueta}: no permite renombrar{motivo} — guardado solo en ERP", "url": ads_url})
                    else:
                        log.append({"tipo": "error", "msg": f"Meta {etiqueta}: {detail}"})
                else:
                    log.append({"tipo": "ok", "msg": f"Meta {etiqueta}: nombre sincronizado"})
            except requests.exceptions.Timeout:
                log.append({"tipo": "error", "msg": f"Meta {etiqueta}: timeout al conectar con Meta"})
            except Exception as ex:
                log.append({"tipo": "error", "msg": f"Meta {etiqueta}: {str(ex)}"})

        # Solo sincronizar campaña si cambió de nombre
        if cambios["campana"]:
            if campana_doc.meta_id:
                _post_nombre(campana_doc.meta_id, campana_doc.nombre, f"Campaña '{campana_doc.nombre}'")
            else:
                log.append({"tipo": "warn", "msg": f"Meta Campaña '{campana_doc.nombre}': sin meta_id, no se sincronizó"})

        for conj in conjuntos:
            # Solo sincronizar conjunto si cambió de nombre
            if conj.get("name") and conj["name"] in cambios["conjuntos"]:
                meta_id = frappe.db.get_value("Conjunto Anuncios", conj["name"], "meta_id")
                if meta_id:
                    _post_nombre(meta_id, conj.get("nombre", ""), f"Conjunto '{conj.get('nombre')}'")
                else:
                    log.append({"tipo": "warn", "msg": f"Meta Conjunto '{conj.get('nombre')}': sin meta_id, no se sincronizó"})

            # Solo sincronizar anuncios que cambiaron de nombre
            for anuncio in conj.get("anuncios", []):
                if anuncio.get("name") and anuncio["name"] in cambios["anuncios"]:
                    an_meta_id = frappe.db.get_value("Anuncio", anuncio["name"], "meta_id")
                    if an_meta_id:
                        _post_nombre(an_meta_id, anuncio.get("nombre", ""), f"Anuncio '{anuncio.get('nombre')}'", es_anuncio=True)
                    else:
                        log.append({"tipo": "warn", "msg": f"Meta Anuncio '{anuncio.get('nombre')}': sin meta_id, no se sincronizó"})

    except Exception as e:
        log.append({"tipo": "error", "msg": f"Error de conexión con Meta: {str(e)}"})

    return log


@frappe.whitelist()
def diagnosticar_renombrado():
    """Prueba renombrar un anuncio de cada campaña para detectar el patrón de error."""
    _require_admin()
    import requests
    token = _conf_get_meta_token()
    if not token:
        return {"error": "Sin token de Meta"}

    campanas = frappe.get_all("Campana Meta", fields=["name", "nombre", "meta_id"])
    resultados = []

    for camp in campanas:
        if not camp.meta_id:
            continue

        # Obtener info de la campaña (budget a nivel campaña = CBO)
        camp_res = requests.get(
            f"https://graph.facebook.com/v22.0/{camp.meta_id}",
            params={"fields": "name,objective,buying_type,daily_budget,lifetime_budget,smart_promotion_type,bid_strategy", "access_token": token},
            timeout=10
        ).json()
        if "error" in camp_res:
            continue

        tiene_budget_campana = bool(camp_res.get("daily_budget") or camp_res.get("lifetime_budget"))
        tipo_budget = "CBO (Advantage+)" if tiene_budget_campana else "ABO (por conjunto)"

        # Buscar un anuncio de esta campaña
        doc = frappe.get_doc("Campana Meta", camp.name)
        anuncio_test = None
        for row in (doc.conjunto_anuncios_asociados or []):
            conj = frappe.get_doc("Conjunto Anuncios", row.conjunto_anuncios)
            for a_row in (conj.anuncios_asociados or []):
                an = frappe.get_doc("Anuncio", a_row.anuncios)
                if an.meta_id:
                    anuncio_test = an
                    break
            if anuncio_test:
                break

        if not anuncio_test:
            continue

        # Intentar renombrar con el MISMO nombre (no cambia nada, solo testea permisos)
        test_res = requests.post(
            f"https://graph.facebook.com/v22.0/{anuncio_test.meta_id}",
            data={"name": anuncio_test.nombre, "access_token": token},
            timeout=10
        ).json()

        puede_renombrar = "error" not in test_res
        error_info = ""
        if not puede_renombrar:
            error_info = f"[{test_res['error'].get('code', '')}] {test_res['error'].get('message', '')} (subcode:{test_res['error'].get('error_subcode', '')})"

        resultados.append({
            "campana": camp.nombre,
            "objetivo": camp_res.get("objective", "?"),
            "buying_type": camp_res.get("buying_type", "?"),
            "smart_type": camp_res.get("smart_promotion_type", ""),
            "bid_strategy": camp_res.get("bid_strategy", "?"),
            "tipo_budget": tipo_budget,
            "anuncio_test": anuncio_test.nombre,
            "anuncio_meta_id": anuncio_test.meta_id,
            "puede_renombrar": puede_renombrar,
            "error": error_info
        })

    return resultados


@frappe.whitelist()
def eliminar_campana(nombre):
    check_edit_permission()
    if not nombre or not frappe.db.exists("Campana Meta", nombre):
        frappe.throw(_("Campana no encontrada"))
    frappe.delete_doc("Campana Meta", nombre, ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def obtener_anuncios_disponibles():
    _require_view()
    return frappe.get_all("Anuncio", fields=["name", "nombre", "etiqueta"])


@frappe.whitelist()
def obtener_conjuntos_disponibles():
    _require_view()
    return frappe.get_all("Conjunto Anuncios", fields=["name", "nombre", "valor"])


# ─────────────────────────────────────────────
# ETIQUETAS LEAD
# ─────────────────────────────────────────────

@frappe.whitelist()
def obtener_etiquetas_lead():
    """Devuelve todas las Etiqueta Lead con nombre y palabras_clave (activadores).

    palabras_clave es un custom field opcional; algunos sites (barra.tiranidos)
    no lo tienen. Si no existe la columna, se devuelve cadena vacia en su lugar.
    """
    _require_view()
    fields = ["name"]
    if frappe.db.has_column("Etiqueta Lead", "palabras_clave"):
        fields.append("palabras_clave")
    rows = frappe.get_all("Etiqueta Lead", fields=fields, order_by="name asc")
    # Garantizar shape consistente para el frontend
    for r in rows:
        r.setdefault("palabras_clave", "")
    return rows


@frappe.whitelist()
def crear_etiqueta_lead(nombre, palabras_clave=""):
    """Crea una nueva Etiqueta Lead con sus activadores."""
    check_edit_permission()
    nombre = nombre.strip() if nombre else ""
    if not nombre:
        frappe.throw(_("El nombre de la etiqueta es obligatorio."))

    if frappe.db.exists("Etiqueta Lead", nombre):
        frappe.throw(_("La etiqueta '{}' ya existe.").format(nombre))

    doc = frappe.get_doc({
        "doctype": "Etiqueta Lead",
        "nombre": nombre,
        "palabras_clave": palabras_clave.strip() if palabras_clave else ""
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok", "name": doc.name, "palabras_clave": doc.palabras_clave}


@frappe.whitelist()
def actualizar_palabras_clave_etiqueta(nombre, palabras_clave):
    """Actualiza las palabras clave (activadores) de una Etiqueta Lead existente."""
    check_edit_permission()
    if not frappe.db.exists("Etiqueta Lead", nombre):
        frappe.throw(_("Etiqueta no encontrada."))
    frappe.db.set_value("Etiqueta Lead", nombre, "palabras_clave", palabras_clave)
    frappe.db.commit()
    return {"status": "ok"}


@frappe.whitelist()
def obtener_leads_por_etiquetas(etiquetas_json):
    """Retorna leads agrupados por etiqueta dado un array JSON de nombres de etiquetas."""
    _require_view()
    import json
    etiquetas = json.loads(etiquetas_json)
    if not etiquetas:
        return {}
    resultado = {}
    for etiqueta in etiquetas:
        leads = frappe.db.sql("""
            SELECT L.name, L.lead_name, L.mobile_no, L.creation
            FROM `tabLead` L
            WHERE EXISTS (
                SELECT 1 FROM `tabEtiqueta Lead Asociado` E
                WHERE E.parent = L.name AND E.parenttype = 'Lead' AND E.etiqueta = %(etiqueta)s
            )
            ORDER BY L.creation DESC
            LIMIT 100
        """, {"etiqueta": etiqueta}, as_dict=True)
        resultado[etiqueta] = [dict(r) for r in leads]
    return resultado
