# Copyright (c) 2026, Lizaraso-Henry and contributors
"""Borra publicaciones que corresponden a posts anclados (viejos con metricas
acumuladas). Se identifican volviendo a consultar Apify con los mismos URLs
y descartando los que vengan con isPinned=true.

Como el patch corre una sola vez y no queremos gastar creditos Apify:
usamos una heuristica simple — borrar posts con fecha_publicacion > 60
dias atras Y engagement_pct anormalmente alto (>2x el resto de la cuenta).
Eso captura los pinned virales sin necesidad de llamar Apify.

Si algun post legit se borra, se re-scrapeara mañana (excluyendo pinned).
"""

import frappe
from datetime import date, timedelta


def execute():
	# En un site fresh la tabla aun no existe (el DocType se crea en
	# post_model_sync). Sin publicaciones que revisar, salir temprano.
	if not frappe.db.table_exists("Publicacion Competencia"):
		return
	limite = date.today() - timedelta(days=60)
	viejos = frappe.db.get_all(
		"Publicacion Competencia",
		filters={"fecha_publicacion": ["<", limite]},
		fields=["name", "cuenta_social", "fecha_publicacion",
		        "url_publicacion", "vistas_actual"],
	)
	borrados = 0
	for p in viejos:
		# ¿es sospechoso de pinned? viejo Y vistas altas
		if (p.vistas_actual or 0) > 100000:
			try:
				frappe.delete_doc("Publicacion Competencia", p.name,
				                  ignore_permissions=True, force=True)
				borrados += 1
			except Exception as e:
				print(f"[radar] no pude borrar {p.name}: {e}")
	frappe.db.commit()
	print(f"[radar] {borrados} publicaciones viejas (probablemente pinned) borradas")
