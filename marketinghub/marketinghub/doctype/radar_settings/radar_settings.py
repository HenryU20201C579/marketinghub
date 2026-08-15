# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

SCHEDULER_METHOD = "marketinghub.api.radar_scraper.correr_scrape"

# Con este preset el Scheduled Job Type queda detenido: el scrapeo solo corre
# cuando alguien pulsa "Ejecutar ahora" en /radar/settings.
PRESET_MANUAL = "Manual (solo con el botón)"

PRESETS = {
	"Diario a las 6 AM": "0 6 * * *",
	"Diario a las 8 PM": "0 20 * * *",
	"Cada 12 horas":     "0 */12 * * *",
	"Cada 6 horas":      "0 */6 * * *",
	"Cada hora":         "0 * * * *",
}


class RadarSettings(Document):
	def validate(self):
		self._resolver_cron_desde_preset()
		self._validar_cron()
		self._validar_tiers()

	def on_update(self):
		if self.flags.get("ignore_scheduler_sync"):
			return
		self._sincronizar_scheduled_job()

	# ------------------- Cron -------------------
	def _resolver_cron_desde_preset(self):
		if self.preset_frecuencia and self.preset_frecuencia in PRESETS:
			self.cron_scrape = PRESETS[self.preset_frecuencia]

	def _validar_cron(self):
		if self.preset_frecuencia == PRESET_MANUAL:
			# el cron queda guardado pero el job va detenido; no estorba si está vacío
			return
		if not self.cron_scrape:
			frappe.throw("La expresión cron no puede estar vacía.")
		try:
			from croniter import croniter
			croniter(self.cron_scrape.strip())
		except ImportError:
			parts = self.cron_scrape.strip().split()
			if len(parts) != 5:
				frappe.throw(
					f"Expresión cron inválida: debe tener 5 campos "
					f"(min hora día mes día-semana). Tienes {len(parts)}."
				)
		except Exception as e:
			frappe.throw(f"Expresión cron inválida: {e}")

	def _sincronizar_scheduled_job(self):
		name = frappe.db.get_value(
			"Scheduled Job Type", {"method": SCHEDULER_METHOD}, "name"
		)
		if not name:
			return
		job = frappe.get_doc("Scheduled Job Type", name)
		manual = self.preset_frecuencia == PRESET_MANUAL
		cambios = False
		if int(job.stopped or 0) != int(manual):
			job.stopped = int(manual)
			cambios = True
		if not manual and job.cron_format != self.cron_scrape:
			job.cron_format = (self.cron_scrape or "").strip()
			cambios = True
		if job.frequency != "Cron":
			job.frequency = "Cron"
			cambios = True
		if cambios:
			job.save(ignore_permissions=True)

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
