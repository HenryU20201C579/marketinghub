# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
import statistics
from frappe.model.document import Document


class CuentaSocial(Document):
	@frappe.whitelist()
	def refrescar_metricas(self):
		"""Recalcula seguidores_actual, engagement_promedio, velocidad_promedio."""
		settings = frappe.get_cached_doc("Radar Settings")
		n = settings.n_pubs_baseline or 30

		# seguidores_actual = ultimo snapshot
		if self.historico_seguidores:
			ordenados = sorted(self.historico_seguidores, key=lambda r: r.fecha)
			self.seguidores_actual = ordenados[-1].seguidores

		# engagement_promedio = mediana de las ultimas N publicaciones
		pubs = frappe.db.get_all(
			"Publicacion Competencia",
			filters={"cuenta_social": self.name},
			fields=["engagement_pct"],
			order_by="fecha_publicacion desc",
			limit=n,
		)
		vals = [p.engagement_pct for p in pubs if p.engagement_pct]
		if vals:
			self.engagement_promedio = round(statistics.median(vals), 2)

		# velocidad_promedio = mediana de velocidad_diaria de snapshots recientes
		vel = frappe.db.sql("""
			SELECT ms.velocidad_diaria
			FROM `tabMetrica Snapshot` ms
			INNER JOIN `tabPublicacion Competencia` p ON ms.parent = p.name
			WHERE p.cuenta_social = %s AND ms.velocidad_diaria IS NOT NULL
			ORDER BY ms.fecha_snapshot DESC
			LIMIT 100
		""", (self.name,), as_dict=True)
		vels = [v.velocidad_diaria for v in vel if v.velocidad_diaria]
		if vels:
			self.velocidad_promedio = round(statistics.median(vels), 2)

		self.save(ignore_permissions=True)
