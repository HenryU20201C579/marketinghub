"""Elimina el scrapeo programado del Radar.

El cron diario se llevaba el 80% del gasto en Apify corriendo solo (8 corridas
programadas = $2.92 vs 7 manuales = $0.74). Ahora la unica forma de gastar es
el boton de /radar/settings, que valida los topes.

`scheduler_events` ya no declara el job, asi que `sync_jobs` lo borra en el
migrate; este patch lo detiene antes por si el borrado no llega, y normaliza el
preset a 'Manual'.
"""
import frappe

from marketinghub.marketinghub.doctype.radar_settings.radar_settings import (
	PRESET_MANUAL,
	SCHEDULER_METHOD,
)


def execute():
	if not frappe.db.exists("DocType", "Radar Settings"):
		return

	name = frappe.db.get_value("Scheduled Job Type", {"method": SCHEDULER_METHOD}, "name")
	if name:
		frappe.db.set_value("Scheduled Job Type", name, "stopped", 1)
		frappe.delete_doc("Scheduled Job Type", name, force=True, ignore_permissions=True)
		print(f"[radar] job programado «{name}» eliminado")

	if frappe.db.get_single_value("Radar Settings", "preset_frecuencia") != PRESET_MANUAL:
		frappe.db.set_value("Radar Settings", "Radar Settings", "preset_frecuencia", PRESET_MANUAL)
		print("[radar] preset normalizado a Manual")
