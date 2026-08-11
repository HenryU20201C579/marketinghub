# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Guion(Document):
	def before_save(self):
		self._autofill_desde_referencia()
		self._sync_estado_con_checks()
		self._calc_ratio()

	def _autofill_desde_referencia(self):
		"""Copia competidor desde la publicacion referente para poder filtrar."""
		if not self.referencia_publicacion:
			self.competidor_ref = None
			return
		competidor = frappe.db.get_value(
			"Publicacion Competencia", self.referencia_publicacion, "competidor"
		)
		if competidor:
			self.competidor_ref = competidor

	def _sync_estado_con_checks(self):
		"""Bidireccional: check_publicado ↔ estado='Publicado'."""
		# check → estado
		if self.check_publicado and self.estado != "Publicado":
			self.estado = "Publicado"
		elif self.check_editado and self.estado in ("Idea", "Guión", "Grabar"):
			self.estado = "Editar"
		elif self.check_grabado and self.estado in ("Idea", "Guión"):
			self.estado = "Editar"
		# estado → check (para la UI simple)
		if self.estado == "Publicado":
			self.check_publicado = 1

	def _calc_ratio(self):
		"""Ratio = mis_vistas / vistas_referente. 0 si falta alguno."""
		if not self.mi_vistas or not self.referencia_publicacion:
			self.ratio_vs_referente = 0
			return
		ref_vistas = frappe.db.get_value(
			"Publicacion Competencia", self.referencia_publicacion, "vistas_actual"
		) or 0
		if ref_vistas > 0:
			self.ratio_vs_referente = round(self.mi_vistas / ref_vistas, 2)
		else:
			self.ratio_vs_referente = 0
