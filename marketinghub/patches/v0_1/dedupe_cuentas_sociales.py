# Copyright (c) 2026, Lizaraso-Henry and contributors
"""Detecta y consolida Cuentas Sociales duplicadas (mismo competidor+plataforma+handle).

Estrategia:
  - Agrupar por (competidor, plataforma, handle).
  - Elegir la 'ganadora' = la que tiene MÁS publicaciones.
  - Mover pubs de las duplicadas → ganadora.
  - Borrar las duplicadas vacías.
"""

import frappe
from collections import defaultdict


def execute():
	cuentas = frappe.db.get_all(
		"Cuenta Social",
		fields=["name", "competidor", "plataforma", "handle"],
	)
	# agrupar
	grupos = defaultdict(list)
	for c in cuentas:
		key = (c.competidor or "", c.plataforma or "", (c.handle or "").lower())
		grupos[key].append(c.name)

	total_borradas = 0
	total_migradas = 0
	for key, names in grupos.items():
		if len(names) < 2:
			continue
		# contar publicaciones de cada una
		conteos = [(n, frappe.db.count("Publicacion Competencia", {"cuenta_social": n})) for n in names]
		conteos.sort(key=lambda x: (-x[1], x[0]))  # más pubs primero
		ganadora = conteos[0][0]
		print(f"[dedupe] {key} → ganadora={ganadora!r} (con {conteos[0][1]} pubs)")
		for otra_name, cnt in conteos[1:]:
			# migrar pubs si tiene
			if cnt > 0:
				frappe.db.sql(
					"UPDATE `tabPublicacion Competencia` SET cuenta_social = %s WHERE cuenta_social = %s",
					(ganadora, otra_name),
				)
				total_migradas += cnt
				print(f"    · migradas {cnt} pubs de {otra_name!r}")
			# borrar la duplicada
			try:
				frappe.delete_doc("Cuenta Social", otra_name,
				                  ignore_permissions=True, force=True)
				total_borradas += 1
				print(f"    · borrada {otra_name!r}")
			except Exception as e:
				print(f"    · NO pude borrar {otra_name!r}: {e}")
	frappe.db.commit()
	print(f"[dedupe] {total_borradas} duplicadas borradas, {total_migradas} pubs migradas")
