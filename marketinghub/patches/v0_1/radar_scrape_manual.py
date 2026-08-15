"""Pasa el scrapeo del Radar a modo manual: el cron queda detenido y la corrida
solo se dispara desde el botón 'Ejecutar ahora' de /radar/settings."""
import frappe

from marketinghub.marketinghub.doctype.radar_settings.radar_settings import (
	PRESET_MANUAL,
	SCHEDULER_METHOD,
)


def execute():
	if not frappe.db.exists("DocType", "Radar Settings"):
		return

	s = frappe.get_single("Radar Settings")
	s.preset_frecuencia = PRESET_MANUAL
	s.flags.ignore_scheduler_sync = True
	s.save(ignore_permissions=True)

	name = frappe.db.get_value("Scheduled Job Type", {"method": SCHEDULER_METHOD}, "name")
	if name:
		frappe.db.set_value("Scheduled Job Type", name, "stopped", 1)
