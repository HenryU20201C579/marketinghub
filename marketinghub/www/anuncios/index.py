"""Backend de /anuncios — dashboard de Anuncios Meta con atribucion CTWA.

Muestra por Anuncio:
- Clicks recibidos (rows en `Anuncio Lead Clickeado`).
- Leads generados (unique parent Lead).
- Leads convertidos a Cliente (Lead.custom_estado="Cliente").
- Ventas atribuidas (Sales Invoice con custom_anuncio = <anuncio>).
- Ingresos (SUM Sales Invoice.grand_total).

Filtros: rango de fecha (por clickeado_en), estado del Anuncio, busqueda
por nombre o meta_id.
"""

import json

import frappe
from frappe import _


ADMIN_ROLES = ("Ventahub-Marketing-Administrar",)
VIEW_ROLES = ("Ventahub-Marketing-Ver", "Ventahub-Marketing-Administrar")


def _is_admin():
	return any(r in frappe.get_roles() for r in ADMIN_ROLES)


def _can_view():
	return any(r in frappe.get_roles() for r in VIEW_ROLES)


def _require_view():
	if not _can_view():
		frappe.throw(
			_(
				"No tienes permisos para ver Anuncios. "
				"Se requiere Ventahub-Marketing-Ver o Ventahub-Marketing-Administrar."
			),
			frappe.PermissionError,
		)


def get_context(context):
	if not _can_view():
		context.no_access = True
		context.has_access = False
		context.required_roles = list(VIEW_ROLES)
		return

	context.has_access = True
	context.can_edit = _is_admin()


def _apply_date_filter(conds, params, from_date, to_date, alias="ALC"):
	if from_date:
		conds.append(f"DATE({alias}.clickeado_en) >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conds.append(f"DATE({alias}.clickeado_en) <= %(to_date)s")
		params["to_date"] = to_date


@frappe.whitelist()
def get_anuncios_stats(from_date=None, to_date=None, estado=None, search_term=None):
	"""KPIs globales para el dashboard."""
	_require_view()

	click_conds = ["1=1"]
	click_params = {}
	_apply_date_filter(click_conds, click_params, from_date, to_date)

	anuncio_conds = ["A.name IS NOT NULL"]
	if estado:
		anuncio_conds.append("A.estado = %(estado)s")
		click_params["estado"] = estado
	if search_term:
		anuncio_conds.append("(A.nombre LIKE %(search)s OR A.meta_id LIKE %(search)s)")
		click_params["search"] = f"%{search_term}%"

	click_where = " AND ".join(click_conds)
	anuncio_where = " AND ".join(anuncio_conds)

	# Anuncios con al menos 1 click en el rango.
	anuncios_activos = frappe.db.sql(f"""
		SELECT COUNT(DISTINCT ALC.anuncio) AS total
		FROM `tabAnuncio Lead Clickeado` ALC
		JOIN `tabAnuncio` A ON A.name = ALC.anuncio
		WHERE {click_where} AND {anuncio_where}
	""", click_params, as_dict=True)[0].total or 0

	total_clicks = frappe.db.sql(f"""
		SELECT COUNT(*) AS total
		FROM `tabAnuncio Lead Clickeado` ALC
		JOIN `tabAnuncio` A ON A.name = ALC.anuncio
		WHERE {click_where} AND {anuncio_where}
	""", click_params, as_dict=True)[0].total or 0

	# Leads unicos que hicieron algun click.
	leads_totales = frappe.db.sql(f"""
		SELECT COUNT(DISTINCT ALC.parent) AS total
		FROM `tabAnuncio Lead Clickeado` ALC
		JOIN `tabAnuncio` A ON A.name = ALC.anuncio
		WHERE ALC.parenttype = 'Lead' AND {click_where} AND {anuncio_where}
	""", click_params, as_dict=True)[0].total or 0

	# Leads convertidos a Cliente.
	leads_cliente = frappe.db.sql(f"""
		SELECT COUNT(DISTINCT ALC.parent) AS total
		FROM `tabAnuncio Lead Clickeado` ALC
		JOIN `tabAnuncio` A ON A.name = ALC.anuncio
		JOIN `tabLead` L ON L.name = ALC.parent AND L.custom_estado = 'Cliente'
		WHERE ALC.parenttype = 'Lead' AND {click_where} AND {anuncio_where}
	""", click_params, as_dict=True)[0].total or 0

	# Ventas atribuidas: Sales Invoice.custom_anuncio = <anuncio> con click en rango.
	# Union con Sales Invoice.custom_anuncio_origen? No, ese es del Lead.
	ventas_row = frappe.db.sql(f"""
		SELECT COUNT(DISTINCT SI.name) AS total,
			   COALESCE(SUM(SI.grand_total), 0) AS ingresos
		FROM `tabSales Invoice` SI
		JOIN `tabAnuncio` A ON A.name = SI.custom_anuncio
		WHERE SI.docstatus = 1
		  AND SI.custom_anuncio IS NOT NULL AND SI.custom_anuncio != ''
		  AND {anuncio_where}
	""", click_params, as_dict=True)[0]

	return {
		"anuncios_con_clicks": int(anuncios_activos),
		"total_clicks": int(total_clicks),
		"leads_totales": int(leads_totales),
		"leads_cliente": int(leads_cliente),
		"conversion_pct": round((leads_cliente / leads_totales * 100), 1) if leads_totales else 0,
		"ventas": int(ventas_row.total or 0),
		"ingresos": float(ventas_row.ingresos or 0),
	}


@frappe.whitelist()
def get_anuncios_batch(start=0, page_length=25, from_date=None, to_date=None, estado=None, search_term=None, order_by="clicks"):
	"""Retorna Anuncios paginados con KPIs individuales.

	order_by: "clicks" | "leads" | "ventas" | "ingresos" | "nombre" | "estado".
	"""
	_require_view()
	start = int(start)
	page_length = int(page_length)

	params = {"start": start, "page_length": page_length}
	anuncio_conds = ["1=1"]
	if estado:
		anuncio_conds.append("A.estado = %(estado)s")
		params["estado"] = estado
	if search_term:
		anuncio_conds.append("(A.nombre LIKE %(search)s OR A.meta_id LIKE %(search)s)")
		params["search"] = f"%{search_term}%"

	date_extra = ""
	if from_date:
		date_extra += " AND DATE(ALC.clickeado_en) >= %(from_date)s"
		params["from_date"] = from_date
	if to_date:
		date_extra += " AND DATE(ALC.clickeado_en) <= %(to_date)s"
		params["to_date"] = to_date

	anuncio_where = " AND ".join(anuncio_conds)

	order_map = {
		"clicks": "clicks DESC",
		"leads": "leads DESC",
		"ventas": "ventas DESC",
		"ingresos": "ingresos DESC",
		"nombre": "A.nombre ASC",
		"estado": "A.estado ASC, A.nombre ASC",
	}
	order_clause = order_map.get(order_by, "clicks DESC")

	sql = f"""
		SELECT
			A.name, A.nombre, A.meta_id, A.estado, A.etiqueta,
			(SELECT COUNT(*) FROM `tabAnuncio Lead Clickeado` ALC
			 WHERE ALC.anuncio = A.name {date_extra}) AS clicks,
			(SELECT COUNT(DISTINCT ALC.parent) FROM `tabAnuncio Lead Clickeado` ALC
			 WHERE ALC.anuncio = A.name AND ALC.parenttype = 'Lead' {date_extra}) AS leads,
			(SELECT COUNT(DISTINCT ALC.parent) FROM `tabAnuncio Lead Clickeado` ALC
			 JOIN `tabLead` L ON L.name = ALC.parent
			 WHERE ALC.anuncio = A.name AND ALC.parenttype = 'Lead'
			   AND L.custom_estado = 'Cliente' {date_extra}) AS leads_cliente,
			(SELECT COUNT(DISTINCT SI.name) FROM `tabSales Invoice` SI
			 WHERE SI.custom_anuncio = A.name AND SI.docstatus = 1) AS ventas,
			(SELECT COALESCE(SUM(SI.grand_total), 0) FROM `tabSales Invoice` SI
			 WHERE SI.custom_anuncio = A.name AND SI.docstatus = 1) AS ingresos
		FROM `tabAnuncio` A
		WHERE {anuncio_where}
		HAVING (clicks > 0 OR ventas > 0)
		ORDER BY {order_clause}
		LIMIT %(page_length)s OFFSET %(start)s
	"""
	rows = frappe.db.sql(sql, params, as_dict=True)
	for r in rows:
		r["clicks"] = int(r.get("clicks") or 0)
		r["leads"] = int(r.get("leads") or 0)
		r["leads_cliente"] = int(r.get("leads_cliente") or 0)
		r["ventas"] = int(r.get("ventas") or 0)
		r["ingresos"] = float(r.get("ingresos") or 0)
		r["conversion_pct"] = round((r["leads_cliente"] / r["leads"] * 100), 1) if r["leads"] else 0
	return rows


@frappe.whitelist()
def get_anuncio_detail(anuncio_name):
	"""Detalle completo de un Anuncio: metadata + leads con clicks + ventas."""
	_require_view()
	if not anuncio_name:
		return {}
	anuncio = frappe.db.get_value(
		"Anuncio", anuncio_name,
		["name", "nombre", "meta_id", "estado", "etiqueta"],
		as_dict=True,
	)
	if not anuncio:
		return {}

	# Ultimos 50 clicks con datos del Lead.
	clicks = frappe.db.sql("""
		SELECT ALC.parent AS lead_name, ALC.clickeado_en, ALC.ctwa_clid, ALC.source_url,
			   L.lead_name AS lead_display_name, L.mobile_no,
			   L.custom_estado, L.custom_cliente
		FROM `tabAnuncio Lead Clickeado` ALC
		LEFT JOIN `tabLead` L ON L.name = ALC.parent
		WHERE ALC.anuncio = %(anuncio)s AND ALC.parenttype = 'Lead'
		ORDER BY ALC.clickeado_en DESC
		LIMIT 50
	""", {"anuncio": anuncio_name}, as_dict=True)

	# Ventas atribuidas a este Anuncio.
	ventas = frappe.db.sql("""
		SELECT SI.name, SI.customer_name, SI.posting_date, SI.grand_total
		FROM `tabSales Invoice` SI
		WHERE SI.custom_anuncio = %(anuncio)s AND SI.docstatus = 1
		ORDER BY SI.posting_date DESC
		LIMIT 50
	""", {"anuncio": anuncio_name}, as_dict=True)

	return {
		"anuncio": anuncio,
		"clicks": clicks,
		"ventas": ventas,
	}


@frappe.whitelist()
def get_estados_disponibles():
	"""Retorna los estados unicos usados por los Anuncios existentes."""
	_require_view()
	rows = frappe.db.sql("""
		SELECT DISTINCT estado FROM `tabAnuncio`
		WHERE estado IS NOT NULL AND estado != ''
		ORDER BY estado
	""", as_dict=True)
	return [r.estado for r in rows]
