"""Dashboard /conversiones — ventas atribuidas a CTWA.

Serie temporal + ranking de anuncios que efectivamente generan facturacion.
Cruza Sales Invoice.custom_anuncio (herencia via lead → SO → SI) contra
Anuncio para mostrar la evolucion temporal, top anuncios y KPIs
consolidados.
"""

import frappe
from frappe.utils import today, add_days, add_months, getdate, flt


VIEW_ROLES = ("Ventahub-Marketing-Ver", "Ventahub-Marketing-Administrar")


def _can_view():
	if frappe.session.user == "Administrator":
		return True
	return any(r in frappe.get_roles() for r in VIEW_ROLES)


def _require_view():
	if not _can_view():
		frappe.throw(
			"No tienes permisos para ver Conversiones. "
			"Se requiere Ventahub-Marketing-Ver o Ventahub-Marketing-Administrar.",
			frappe.PermissionError,
		)


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/conversiones"
		raise frappe.Redirect

	if not _can_view():
		context.no_access = True
		context.has_access = False
		context.required_roles = list(VIEW_ROLES)
		context.title = "Conversiones CTWA"
		return

	context.no_cache = 1
	context.has_access = True
	context.title = "Conversiones CTWA"


def _resolve_granularidad(granularidad, days):
	"""Sugiere DAY/WEEK/MONTH segun el rango si no se especifica."""
	if granularidad in ("day", "week", "month"):
		return granularidad
	if days <= 31:
		return "day"
	if days <= 120:
		return "week"
	return "month"


def _bucket_expr(granularidad):
	if granularidad == "month":
		return "DATE_FORMAT(si.posting_date, '%%Y-%%m-01')"
	if granularidad == "week":
		return "DATE(DATE_SUB(si.posting_date, INTERVAL WEEKDAY(si.posting_date) DAY))"
	return "si.posting_date"


@frappe.whitelist()
def get_conversiones_data(from_date=None, to_date=None, granularidad=None):
	"""Retorna KPIs, serie temporal y top anuncios de ventas CTWA en el rango.

	Args:
		from_date, to_date: str YYYY-MM-DD (default: ultimos 30 dias).
		granularidad: 'day'|'week'|'month' (default: auto por rango).
	"""
	_require_view()

	if not from_date:
		from_date = str(add_days(today(), -30))
	if not to_date:
		to_date = str(today())

	dias = max(1, (getdate(to_date) - getdate(from_date)).days + 1)
	granularidad = _resolve_granularidad(granularidad, dias)
	bucket = _bucket_expr(granularidad)

	params = {"from_date": from_date, "to_date": to_date}

	# KPIs consolidados.
	kpis_row = frappe.db.sql(
		"""
		SELECT
			COUNT(*)              AS total_facturas,
			SUM(si.grand_total)   AS total_revenue,
			AVG(si.grand_total)   AS ticket_promedio,
			COUNT(DISTINCT si.custom_anuncio) AS anuncios_distintos
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND si.custom_anuncio IS NOT NULL AND si.custom_anuncio != ''
		""",
		params,
		as_dict=True,
	)[0] or {}

	# Total facturacion GLOBAL en el mismo rango — para calcular % CTWA.
	global_row = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(si.grand_total), 0) AS revenue_global,
			   COUNT(*) AS facturas_global
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		""",
		params,
		as_dict=True,
	)[0] or {}

	revenue_ctwa = flt(kpis_row.get("total_revenue"))
	revenue_global = flt(global_row.get("revenue_global"))
	pct_revenue = (revenue_ctwa / revenue_global * 100.0) if revenue_global else 0.0

	# Serie temporal por bucket.
	serie = frappe.db.sql(
		f"""
		SELECT {bucket} AS bucket_date,
			   SUM(si.grand_total) AS revenue,
			   COUNT(*) AS facturas
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND si.custom_anuncio IS NOT NULL AND si.custom_anuncio != ''
		GROUP BY bucket_date
		ORDER BY bucket_date ASC
		""",
		params,
		as_dict=True,
	)
	for row in serie:
		row["bucket_date"] = str(row["bucket_date"])
		row["revenue"] = flt(row["revenue"])
		row["facturas"] = int(row["facturas"])

	# Ranking anuncios: revenue, facturas, ticket, primera y ultima fecha.
	ranking = frappe.db.sql(
		"""
		SELECT si.custom_anuncio AS anuncio_id,
			   SUM(si.grand_total) AS revenue,
			   COUNT(*) AS facturas,
			   AVG(si.grand_total) AS ticket,
			   MIN(si.posting_date) AS primera,
			   MAX(si.posting_date) AS ultima
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1
		  AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
		  AND si.custom_anuncio IS NOT NULL AND si.custom_anuncio != ''
		GROUP BY si.custom_anuncio
		ORDER BY revenue DESC
		LIMIT 20
		""",
		params,
		as_dict=True,
	)

	# Enriquecer con nombre legible del anuncio.
	nombres = {}
	if ranking and frappe.db.exists("DocType", "Anuncio"):
		ids = [r["anuncio_id"] for r in ranking]
		rows = frappe.db.get_all(
			"Anuncio", filters={"name": ["in", ids]}, fields=["name", "nombre"],
		)
		for r in rows:
			nombres[r.name] = r.get("nombre") or r.name

	for r in ranking:
		r["nombre"] = nombres.get(r["anuncio_id"], r["anuncio_id"])
		r["revenue"] = flt(r["revenue"])
		r["ticket"] = flt(r["ticket"])
		r["facturas"] = int(r["facturas"])
		r["primera"] = str(r["primera"]) if r.get("primera") else None
		r["ultima"] = str(r["ultima"]) if r.get("ultima") else None

	return {
		"from_date": from_date,
		"to_date": to_date,
		"granularidad": granularidad,
		"kpis": {
			"total_facturas": int(kpis_row.get("total_facturas") or 0),
			"total_revenue": revenue_ctwa,
			"ticket_promedio": flt(kpis_row.get("ticket_promedio")),
			"anuncios_distintos": int(kpis_row.get("anuncios_distintos") or 0),
			"revenue_global": revenue_global,
			"facturas_global": int(global_row.get("facturas_global") or 0),
			"pct_revenue": pct_revenue,
		},
		"serie": serie,
		"ranking": ranking,
	}
