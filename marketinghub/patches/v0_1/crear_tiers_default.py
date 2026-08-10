# Copyright (c) 2026, Lizaraso-Henry and contributors
"""Inserta los 10 tiers Gunbound como default en Radar Settings."""

import frappe

TIERS = [
	{"orden": 1,  "nombre": "Dragón Plateado",              "imagen_url": "/radar/tiers/01_dragon_plateado.png",         "vistas_min": 5000000, "engagement_min": 5.0, "es_viral": 1, "color_hex": "#e5e7eb"},
	{"orden": 2,  "nombre": "Dragón Azul",                  "imagen_url": "/radar/tiers/02_dragon_azul.png",             "vistas_min": 1000000, "engagement_min": 4.0, "es_viral": 1, "color_hex": "#3b82f6"},
	{"orden": 3,  "nombre": "Cetro de Diamante",            "imagen_url": "/radar/tiers/03_cetro_diamante.png",          "vistas_min": 500000,  "engagement_min": 3.5, "es_viral": 1, "color_hex": "#a78bfa"},
	{"orden": 4,  "nombre": "Hachón dorado (gema roja)",    "imagen_url": "/radar/tiers/04_hachon_dorado_gema_roja.png", "vistas_min": 200000,  "engagement_min": 3.0, "es_viral": 1, "color_hex": "#dc2626"},
	{"orden": 5,  "nombre": "Hachón dorado (gema azul)",    "imagen_url": "/radar/tiers/05_hachon_dorado_gema_azul.png", "vistas_min": 100000,  "engagement_min": 2.5, "es_viral": 1, "color_hex": "#2563eb"},
	{"orden": 6,  "nombre": "Doble hacha dorada",           "imagen_url": "/radar/tiers/06_doble_hacha_dorada.png",      "vistas_min": 50000,   "engagement_min": 2.0, "es_viral": 0, "color_hex": "#f59e0b"},
	{"orden": 7,  "nombre": "Doble hacha simple",           "imagen_url": "/radar/tiers/07_doble_hacha_simple.png",      "vistas_min": 20000,   "engagement_min": 2.0, "es_viral": 0, "color_hex": "#94a3b8"},
	{"orden": 8,  "nombre": "Doble maso de piedra",         "imagen_url": "/radar/tiers/08_doble_maso_piedra.png",       "vistas_min": 10000,   "engagement_min": 1.5, "es_viral": 0, "color_hex": "#78716c"},
	{"orden": 9,  "nombre": "Doble maso de madera",         "imagen_url": "/radar/tiers/09_doble_maso_madera.png",       "vistas_min": 3000,    "engagement_min": 1.0, "es_viral": 0, "color_hex": "#a16207"},
	{"orden": 10, "nombre": "Pollito",                      "imagen_url": "/radar/tiers/10_pollito.png",                 "vistas_min": 0,       "engagement_min": 0,   "es_viral": 0, "color_hex": "#facc15"},
]


def execute():
	s = frappe.get_single("Radar Settings")
	# solo insertar si no hay tiers ya (idempotente)
	if s.tiers_viralidad:
		print(f"[radar] tiers ya existen ({len(s.tiers_viralidad)} filas) — no se sobrescriben")
		return
	for t in TIERS:
		s.append("tiers_viralidad", t)
	# evitar disparar sync scheduler
	s.flags.ignore_scheduler_sync = True
	s.save(ignore_permissions=True)
	frappe.db.commit()
	print(f"[radar] {len(TIERS)} tiers insertados")
