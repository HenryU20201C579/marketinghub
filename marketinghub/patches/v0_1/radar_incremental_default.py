"""Enciende el modo incremental y el mínimo entre corridas en sitios ya migrados.

Los `default` del doctype solo se aplican a documentos nuevos, y Radar Settings
es un Single que ya existe. Para un Check no vale mirar el valor (un campo
ausente se lee como 0, igual que un 0 puesto a mano), así que se mira si existe
la fila en `tabSingles`: si no existe, nadie lo ha tocado nunca.
"""
import frappe

DEFAULTS = {"modo_incremental": 1, "horas_entre_corridas": 24}


def execute():
	if not frappe.db.exists("DocType", "Radar Settings"):
		return

	faltan = {
		campo: valor for campo, valor in DEFAULTS.items()
		if not frappe.db.exists("Singles", {"doctype": "Radar Settings", "field": campo})
	}
	if not faltan:
		return

	doc = frappe.get_single("Radar Settings")
	for campo, valor in faltan.items():
		doc.set(campo, valor)
		print(f"[radar] {campo} inicializado en {valor}")
	doc.save(ignore_permissions=True)
