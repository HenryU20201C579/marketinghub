"""Aplica el techo de posts por marca a lo que ya estaba guardado.

`max_posts_marca` recorta las corridas en `_limite_de`, pero los valores viejos
(defaults de 20, límites por marca de 10 o 30) seguirían viéndose en la página
como si fueran a pedirse. Se recortan para que lo que se ve sea lo que se pide.
"""
import frappe


def execute():
	if not frappe.db.exists("DocType", "Radar Settings"):
		return

	# el default del doctype solo aplica a documentos nuevos y Radar Settings es un
	# Single que ya existe: si nunca se fijó (None), se inicializa aquí. Un 0
	# explícito sí se respeta, que significa "sin techo".
	actual = frappe.db.get_single_value("Radar Settings", "max_posts_marca")
	if actual is None or actual == "":
		# ojo: db.set_value sobre un Single hace UPDATE, y para un campo recién
		# añadido no hay fila en tabSingles que actualizar: no escribiría nada
		doc = frappe.get_single("Radar Settings")
		doc.max_posts_marca = 3
		doc.save(ignore_permissions=True)
		actual = 3
		print("[radar] max_posts_marca inicializado en 3")

	techo = int(actual or 0)
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
