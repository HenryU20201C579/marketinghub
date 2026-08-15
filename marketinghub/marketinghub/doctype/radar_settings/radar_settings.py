# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

SCHEDULER_METHOD = "marketinghub.api.radar_scraper.correr_scrape"

# El Radar es 100% manual: la única forma de gastar en Apify es pulsando ▶ en
# /radar/settings. Ya no hay presets de cron ni Scheduled Job Type (se quitó de
# hooks.py); esta constante sobrevive porque el resto del código la referencia.
PRESET_MANUAL = "Manual"
# valores que usaron versiones anteriores del campo; se normalizan al guardar
PRESET_MANUAL_LEGACY = "Manual (solo con el botón)"


class RadarSettings(Document):
	def validate(self):
		# no hay más modo que manual: cualquier valor heredado se normaliza
		self.preset_frecuencia = PRESET_MANUAL
		self._validar_topes()
		self._validar_tiers()

	def on_update(self):
		# el job programado ya no existe; si quedó uno de una versión anterior,
		# nos aseguramos de que siga detenido
		self._detener_scheduled_job()

	# ------------------- Programación -------------------
	def _detener_scheduled_job(self):
		name = frappe.db.get_value(
			"Scheduled Job Type", {"method": SCHEDULER_METHOD}, "name"
		)
		if name and not frappe.db.get_value("Scheduled Job Type", name, "stopped"):
			frappe.db.set_value("Scheduled Job Type", name, "stopped", 1)

	# ------------------- Topes de gasto -------------------
	def _validar_topes(self):
		for campo, etiqueta in (
			("tope_corrida_usd", "tope por corrida"),
			("tope_mes_usd", "tope mensual"),
		):
			valor = float(self.get(campo) or 0)
			if valor < 0:
				frappe.throw(f"El {etiqueta} no puede ser negativo.")
		corrida = float(self.tope_corrida_usd or 0)
		mes = float(self.tope_mes_usd or 0)
		if corrida and mes and corrida > mes:
			frappe.throw(
				f"El tope por corrida (${corrida:.3f}) no puede ser mayor "
				f"que el tope mensual (${mes:.2f})."
			)

	# ------------------- Tiers -------------------
	def _validar_tiers(self):
		if not self.tiers_viralidad:
			return
		# Verificar que 'orden' sea unico
		ordenes = [t.orden for t in self.tiers_viralidad]
		if len(ordenes) != len(set(ordenes)):
			frappe.throw("Los valores de 'Orden' en Tiers deben ser únicos.")


def obtener_tiers_ordenados():
	"""Retorna los tiers de mayor (orden=1) a menor (orden=N)."""
	s = frappe.get_cached_doc("Radar Settings")
	tiers = list(s.tiers_viralidad or [])
	tiers.sort(key=lambda t: t.orden)  # menor orden = mejor tier
	return tiers


def asignar_tier(vistas, engagement_pct):
	"""Devuelve dict con name, orden, imagen_url, color_hex, es_viral del tier
	   MAS ALTO cuyos 2 umbrales cumple el post. None si no hay tiers."""
	tiers = obtener_tiers_ordenados()
	if not tiers:
		return None
	vistas = int(vistas or 0)
	eng = float(engagement_pct or 0)
	# recorrer de mejor (orden=1) al peor, tomar el primero que cumple
	for t in tiers:
		if vistas >= (t.vistas_min or 0) and eng >= (t.engagement_min or 0):
			return {
				"nombre": t.nombre,
				"orden": t.orden,
				"imagen_url": t.imagen_url,
				"color_hex": t.color_hex,
				"es_viral": bool(t.es_viral),
			}
	# no cumple ninguno (raro si Pollito tiene umbrales 0/0)
	return None
