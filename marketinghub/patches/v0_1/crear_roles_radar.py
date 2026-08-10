# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt
"""Crea los 3 roles del Radar de Competencia si no existen."""

import frappe


ROLES = [
	("Marketinghub-Radar-Administrar", "Puede crear/editar competidores, cuentas sociales y Radar Settings."),
	("Marketinghub-Radar-Analista", "Puede analizar publicaciones (formato, notas, elementos_a_copiar, estado)."),
	("Marketinghub-Radar-Ver", "Solo lectura del Radar de Competencia."),
]


def execute():
	for role_name, desc in ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		doc = frappe.new_doc("Role")
		doc.role_name = role_name
		doc.desk_access = 1
		doc.description = desc
		doc.insert(ignore_permissions=True)
		print(f"[radar] rol creado: {role_name}")
	frappe.db.commit()
