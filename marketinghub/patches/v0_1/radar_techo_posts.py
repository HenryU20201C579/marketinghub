"""Aplica el techo de posts por marca a lo que ya estaba guardado.

`max_posts_marca` recorta las corridas en `_limite_de`, pero los valores viejos
(defaults de 20, límites por marca de 10 o 30) seguirían viéndose en la página
como si fueran a pedirse. Se recortan para que lo que se ve sea lo que se pide.
"""
import frappe


def execute():
	if not frappe.db.exists("DocType", "Radar Settings"):
		return

	techo = int(frappe.db.get_single_value("Radar Settings", "max_posts_marca") or 0)
	if not techo:
		return

	for campo in ("posts_por_perfil_ig", "posts_por_perfil_tiktok"):
		actual = int(frappe.db.get_single_value("Radar Settings", campo) or 0)
		if actual > techo:
			frappe.db.set_value("Radar Settings", "Radar Settings", campo, techo)
			print(f"[radar] {campo}: {actual} -> {techo}")

	for c in frappe.db.get_all("Competidor", filters={"limite_posts": [">", techo]},
	                           fields=["name", "limite_posts"]):
		frappe.db.set_value("Competidor", c["name"], "limite_posts", techo)
		print(f"[radar] {c['name']}: límite {c['limite_posts']} -> {techo}")
