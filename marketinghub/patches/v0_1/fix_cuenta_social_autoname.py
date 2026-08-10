# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt
"""Renombra Cuentas Sociales cuyo name quedo con handle vacio (ej: 'TikTok-')."""

import frappe
from marketinghub.marketinghub.doctype.cuenta_social.cuenta_social import extraer_handle


def execute():
	# Buscar cuentas con name que termina en guion (handle vacio)
	rotas = frappe.db.sql(
		"""SELECT name, plataforma, handle, url_perfil
		   FROM `tabCuenta Social`
		   WHERE name LIKE %s OR handle IS NULL OR handle = ''""",
		("%-",),
		as_dict=True,
	)
	for cs in rotas:
		nuevo_handle = extraer_handle(cs.url_perfil or "", cs.plataforma or "")
		if not nuevo_handle:
			print(
				f"[radar] no puedo arreglar Cuenta Social {cs.name!r}: "
				f"URL '{cs.url_perfil}' invalida para {cs.plataforma}"
			)
			continue
		nuevo_name = f"{cs.plataforma}-{nuevo_handle}"
		if nuevo_name == cs.name:
			# Solo faltaba el handle en columna, no el name
			frappe.db.set_value("Cuenta Social", cs.name, "handle", nuevo_handle)
			print(f"[radar] handle actualizado en {cs.name}")
			continue
		if frappe.db.exists("Cuenta Social", nuevo_name):
			print(
				f"[radar] no puedo renombrar {cs.name!r} → {nuevo_name!r} "
				f"(ya existe otro doc con ese nombre)"
			)
			continue
		frappe.rename_doc("Cuenta Social", cs.name, nuevo_name, force=True)
		frappe.db.set_value("Cuenta Social", nuevo_name, "handle", nuevo_handle)
		print(f"[radar] renombrado {cs.name!r} → {nuevo_name!r}")
	frappe.db.commit()
