# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today, getdate


class PublicacionCompetencia(Document):
	def before_insert(self):
		self._autofill_desde_cuenta()

	def before_save(self):
		self._autofill_desde_cuenta()
		self._calc_titulo_hook()
		self._calc_engagement_pct()
		self._calc_score_y_viralidad()

	def after_insert(self):
		# Refrescar baseline de la cuenta al llegar publicacion nueva
		if self.cuenta_social:
			frappe.get_doc("Cuenta Social", self.cuenta_social).refrescar_metricas()

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
		interacciones = (
			(self.likes_actual or 0)
			+ (self.comentarios_actual or 0)
			+ (self.compartidos_actual or 0)
			+ (self.guardados_actual or 0)
		)
		denominador = None
		if self.vistas_actual and self.vistas_actual > 0:
			denominador = self.vistas_actual
		elif self.cuenta_social:
			# Fallback: seguidores de la cuenta (para IG posts sin vistas)
			seg = frappe.db.get_value("Cuenta Social", self.cuenta_social, "seguidores_actual")
			if seg and seg > 0:
				denominador = seg
		if denominador and denominador > 0:
			self.engagement_pct = round((interacciones / denominador) * 100, 2)
		else:
			self.engagement_pct = 0

	def _calc_score_y_viralidad(self):
		settings = frappe.get_cached_doc("Radar Settings")
		umbral = settings.umbral_viralidad or 2.0
		piso = settings.piso_minimo_vistas or 10000
		umbral_vel = settings.umbral_velocidad or 3.0

		# Baseline de engagement de la cuenta
		baseline = frappe.db.get_value("Cuenta Social", self.cuenta_social, "engagement_promedio") or 0
		vel_promedio_cuenta = frappe.db.get_value("Cuenta Social", self.cuenta_social, "velocidad_promedio") or 0

		# Score de engagement
		if baseline > 0:
			self.score_viralidad = round((self.engagement_pct or 0) / baseline, 2)
		else:
			self.score_viralidad = 0

		viral_por_engagement = self.score_viralidad >= umbral

		# Velocidad temprana: solo si hay al menos 2 snapshots y menos de 7 dias
		viral_por_velocidad = False
		if self.fecha_publicacion:
			dias = (getdate(today()) - getdate(self.fecha_publicacion)).days
			if dias < 7 and self.historico_metricas and len(self.historico_metricas) >= 2:
				ultima_vel = self.historico_metricas[-1].velocidad_diaria or 0
				if vel_promedio_cuenta > 0:
					ratio_vel = ultima_vel / vel_promedio_cuenta
					viral_por_velocidad = ratio_vel >= umbral_vel

		# Piso de vistas aplica a ambos
		tiene_vistas = (self.vistas_actual or 0) >= piso

		self.es_viral = int((viral_por_engagement or viral_por_velocidad) and tiene_vistas)

		if self.es_viral:
			if viral_por_engagement and viral_por_velocidad:
				self.motivo_viralidad = "ambos"
			elif viral_por_engagement:
				self.motivo_viralidad = "engagement"
			else:
				self.motivo_viralidad = "velocidad"
		else:
			self.motivo_viralidad = None
