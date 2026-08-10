# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

SCHEDULER_METHOD = "marketinghub.api.radar_scraper.correr_scrape"

PRESETS = {
	"Diario a las 6 AM": "0 6 * * *",
	"Diario a las 8 PM": "0 20 * * *",
	"Cada 12 horas":     "0 */12 * * *",
	"Cada 6 horas":      "0 */6 * * *",
	"Cada hora":         "0 * * * *",
	# "Personalizado" no fija cron, respeta cron_scrape del usuario
}


class RadarSettings(Document):
	def validate(self):
		self._resolver_cron_desde_preset()
		self._validar_cron()

	def on_update(self):
		if self.flags.get("ignore_scheduler_sync"):
			return
		self._sincronizar_scheduled_job()

	def _resolver_cron_desde_preset(self):
		"""Si eligio un preset, sobrescribimos cron_scrape con la expresion asociada."""
		if self.preset_frecuencia and self.preset_frecuencia in PRESETS:
			self.cron_scrape = PRESETS[self.preset_frecuencia]

	def _validar_cron(self):
		"""Verifica que cron_scrape sea una expresion cron valida."""
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
		"""Actualiza el Scheduled Job Type con la expresion cron actual."""
		name = frappe.db.get_value(
			"Scheduled Job Type", {"method": SCHEDULER_METHOD}, "name"
		)
		if not name:
			# Aun no existe (bench migrate se encarga la primera vez).
			return
		job = frappe.get_doc("Scheduled Job Type", name)
		cambios = False
		if job.cron_format != self.cron_scrape:
			job.cron_format = self.cron_scrape.strip()
			cambios = True
		if job.frequency != "Cron":
			job.frequency = "Cron"
			cambios = True
		if cambios:
			job.save(ignore_permissions=True)
