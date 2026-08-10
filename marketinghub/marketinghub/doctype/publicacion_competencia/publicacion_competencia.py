# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from marketinghub.marketinghub.doctype.radar_settings.radar_settings import asignar_tier


class PublicacionCompetencia(Document):
	def before_insert(self):
		self._autofill_desde_cuenta()

	def before_save(self):
		self._autofill_desde_cuenta()
		self._calc_titulo_hook()
		self._calc_engagement_pct()
		self._calc_tier()

	def _autofill_desde_cuenta(self):
		if not self.cuenta_social:
			return
		cuenta = frappe.db.get_value(
			"Cuenta Social", self.cuenta_social,
			["competidor", "plataforma"], as_dict=True,
		)
		if cuenta:
			self.competidor = cuenta.competidor
			self.plataforma = cuenta.plataforma

	def _calc_titulo_hook(self):
		if self.descripcion:
			primer_renglon = self.descripcion.split("\n", 1)[0]
			self.titulo_hook = primer_renglon[:80]
		else:
			self.titulo_hook = None

	def _calc_engagement_pct(self):
		"""Solo usa vistas como denominador (medicion absoluta del post)."""
		interacciones = (
			(self.likes_actual or 0)
			+ (self.comentarios_actual or 0)
			+ (self.compartidos_actual or 0)
			+ (self.guardados_actual or 0)
		)
		if self.vistas_actual and self.vistas_actual > 0:
			self.engagement_pct = round((interacciones / self.vistas_actual) * 100, 2)
		else:
			self.engagement_pct = 0

	def _calc_tier(self):
		"""Asigna el tier segun umbrales configurados en Radar Settings."""
		tier = asignar_tier(self.vistas_actual or 0, self.engagement_pct or 0)
		if tier:
			self.tier = tier["nombre"]
			self.tier_orden = tier["orden"]
			self.es_viral = int(tier["es_viral"])
		else:
			self.tier = None
			self.tier_orden = None
			self.es_viral = 0
