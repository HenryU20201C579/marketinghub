# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today, now_datetime


class AnuncioCompetencia(Document):
	def before_save(self):
		self._calc_dias_activo()
		self._calc_etiqueta()

	def _calc_dias_activo(self):
		"""Diferencia entre fecha_inicio y ultimo_visto (o hoy)."""
		if not self.fecha_inicio:
			self.dias_activo = 0
			return
		inicio = getdate(self.fecha_inicio)
		if self.fecha_pausado:
			fin = getdate(self.fecha_pausado)
		elif self.fecha_ultimo_visto:
			fin = getdate(self.fecha_ultimo_visto)
		else:
			fin = getdate(today())
		self.dias_activo = max(0, (fin - inicio).days)

	def _calc_etiqueta(self):
		"""Nuevo <7 · Fresco 7-13 · Test scale 14-29 · Ganador 30-59 · Ganador top 60+ · Pausado."""
		if not self.esta_activo:
			self.etiqueta_ganador = "Pausado"
			return
		d = self.dias_activo or 0
		if d < 7:      self.etiqueta_ganador = "Nuevo"
		elif d < 14:   self.etiqueta_ganador = "Fresco"
		elif d < 30:   self.etiqueta_ganador = "Test scale"
		elif d < 60:   self.etiqueta_ganador = "Ganador"
		else:          self.etiqueta_ganador = "Ganador top"
