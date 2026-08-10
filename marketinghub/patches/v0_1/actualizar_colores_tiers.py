# Copyright (c) 2026, Lizaraso-Henry and contributors
"""Actualiza los colores de los tiers según su nombre (psicología del color)."""

import frappe

# Colores según nombre del tier
COLOR_POR_ORDEN = {
	1:  "#c0c0c0",   # Dragón Plateado → plateado metálico
	2:  "#2563eb",   # Dragón Azul → azul rey
	3:  "#06b6d4",   # Cetro de Diamante → cyan brillante
	4:  "#dc2626",   # Hachón dorado gema roja → rojo carmesí
	5:  "#3b82f6",   # Hachón gema azul → azul zafiro
	6:  "#d4af37",   # Hacha dorada → dorado
	7:  "#94a3b8",   # Hacha simple → plata clara
	8:  "#6b7280",   # Maso de piedra → gris piedra
	9:  "#a16207",   # Maso de madera → marrón madera
	10: "#facc15",   # Pollito → amarillo pollito
}


def execute():
	s = frappe.get_single("Radar Settings")
	if not s.tiers_viralidad:
		print("[radar] no hay tiers configurados")
		return
	cambios = 0
	for t in s.tiers_viralidad:
		nuevo = COLOR_POR_ORDEN.get(t.orden)
		if nuevo and t.color_hex != nuevo:
			t.color_hex = nuevo
			cambios += 1
	if cambios:
		s.flags.ignore_scheduler_sync = True
		s.save(ignore_permissions=True)
		frappe.db.commit()
		print(f"[radar] {cambios} tiers actualizados con color según nombre")
	else:
		print("[radar] tiers ya tienen colores correctos")
