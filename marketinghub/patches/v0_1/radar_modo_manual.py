"""Pasa el scrapeo del Radar a modo manual: el cron queda detenido y la corrida
solo se dispara desde el botón 'Ejecutar ahora' de /radar/settings.

Reemplaza a v0_1.radar_scrape_manual, que usó un label más largo para el preset.
"""
import frappe

from marketinghub.marketinghub.doctype.radar_settings.radar_settings import (
	PRESET_MANUAL,
	PRESET_MANUAL_LEGACY,
	SCHEDULER_METHOD,
)


def execute():
	if not frappe.db.exists("DocType", "Radar Settings"):
		return

	s = frappe.get_single("Radar Settings")
	# solo forzamos manual la primera vez; si alguien ya eligió un cron, se respeta
	if s.preset_frecuencia in (None, "", PRESET_MANUAL_LEGACY, "Diario a las 6 AM"):
		s.preset_frecuencia = PRESET_MANUAL
		s.flags.ignore_scheduler_sync = True
		s.save(ignore_permissions=True)

	if s.preset_frecuencia == PRESET_MANUAL:
		name = frappe.db.get_value("Scheduled Job Type", {"method": SCHEDULER_METHOD}, "name")
		if name:
			frappe.db.set_value("Scheduled Job Type", name, "stopped", 1)
