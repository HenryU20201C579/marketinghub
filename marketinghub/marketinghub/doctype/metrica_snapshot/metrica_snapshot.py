# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class MetricaSnapshot(Document):
	def before_insert(self):
		self._calc_dias_y_velocidad()

	def before_save(self):
		self._calc_dias_y_velocidad()

	def _calc_dias_y_velocidad(self):
		if not self.parent or not self.fecha_snapshot:
			return
		# dias_desde_publicacion
		fecha_pub = frappe.db.get_value("Publicacion Competencia", self.parent, "fecha_publicacion")
		if fecha_pub:
			self.dias_desde_publicacion = (getdate(self.fecha_snapshot) - getdate(fecha_pub)).days

		# velocidad_diaria: comparar contra snapshot previo del mismo parent
		previos = frappe.db.get_all(
			"Metrica Snapshot",
			filters={
				"parent": self.parent,
				"fecha_snapshot": ["<", self.fecha_snapshot],
			},
			fields=["fecha_snapshot", "vistas"],
			order_by="fecha_snapshot desc",
			limit=1,
		)
		if previos:
			prev = previos[0]
			delta_dias = (getdate(self.fecha_snapshot) - getdate(prev.fecha_snapshot)).days
			if delta_dias > 0:
				delta_v = (self.vistas or 0) - (prev.vistas or 0)
				self.velocidad_diaria = round(delta_v / delta_dias, 2)
		elif self.dias_desde_publicacion and self.dias_desde_publicacion > 0:
			# Primer snapshot: usar dias desde publicacion
			self.velocidad_diaria = round((self.vistas or 0) / self.dias_desde_publicacion, 2)
