# Copyright (c) 2026, Lizaraso-Henry and contributors
"""Recorre todas las Publicacion Competencia y recalcula su tier."""

import frappe


def execute():
	pubs = frappe.db.get_all("Publicacion Competencia", pluck="name")
	print(f"[radar] recalculando tier de {len(pubs)} publicaciones...")
	actualizadas = 0
	for name in pubs:
		try:
			doc = frappe.get_doc("Publicacion Competencia", name)
			# save() dispara before_save que llama _calc_tier
			doc.save(ignore_permissions=True)
			actualizadas += 1
		except Exception as e:
			print(f"  ✗ {name}: {e}")
	frappe.db.commit()
	print(f"[radar] {actualizadas}/{len(pubs)} publicaciones actualizadas")
