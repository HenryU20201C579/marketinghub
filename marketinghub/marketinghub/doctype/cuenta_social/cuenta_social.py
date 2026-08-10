# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import re
import statistics
import frappe
from frappe.model.document import Document


# Regex por plataforma para extraer el handle desde la URL del perfil.
# Cada patron captura el handle en el grupo 1.
HANDLE_PATTERNS = {
	"Instagram": re.compile(
		r"instagram\.com/(?:@)?([a-zA-Z0-9._]+)/?", re.IGNORECASE
	),
	"TikTok": re.compile(
		r"tiktok\.com/@([a-zA-Z0-9._]+)", re.IGNORECASE
	),
	"Facebook": re.compile(
		r"facebook\.com/(?:pg/|profile\.php\?id=)?([a-zA-Z0-9.\-]+)", re.IGNORECASE
	),
	"YouTube": re.compile(
		r"youtube\.com/(?:@|channel/|c/|user/)?([a-zA-Z0-9._\-]+)", re.IGNORECASE
	),
}


def extraer_handle(url: str, plataforma: str) -> str | None:
	"""Extrae el handle de un URL de perfil segun la plataforma.

	Retorna None si el URL no matchea el patron esperado."""
	if not url or not plataforma:
		return None
	patron = HANDLE_PATTERNS.get(plataforma)
	if not patron:
		return None
	m = patron.search(url.strip())
	return m.group(1) if m else None


class CuentaSocial(Document):
	def autoname(self):
		"""Se ejecuta antes de set_new_name (antes que before_insert).
		Deriva el handle desde la URL y asigna el nombre del documento."""
		self._derivar_handle()
		self.name = f"{self.plataforma}-{self.handle}"

	def before_save(self):
		self._derivar_handle()

	def _derivar_handle(self):
		"""Deriva self.handle desde self.url_perfil + self.plataforma."""
		if not self.url_perfil:
			frappe.throw(
				"Debes indicar la URL del perfil (ej: "
				"https://www.instagram.com/lizarasocueros/)."
			)
		handle = extraer_handle(self.url_perfil, self.plataforma)
		if not handle:
			frappe.throw(
				f"No pude extraer el handle desde la URL '{self.url_perfil}'. "
				f"Verifica que sea una URL valida de {self.plataforma}."
			)
		self.handle = handle

	@frappe.whitelist()
	def refrescar_metricas(self):
		"""Recalcula seguidores_actual, engagement_promedio, velocidad_promedio."""
		settings = frappe.get_cached_doc("Radar Settings")
		n = settings.n_pubs_baseline or 30

		# seguidores_actual = ultimo snapshot
		if self.historico_seguidores:
			ordenados = sorted(self.historico_seguidores, key=lambda r: r.fecha)
			self.seguidores_actual = ordenados[-1].seguidores

		# engagement_promedio = mediana de las ultimas N publicaciones
		pubs = frappe.db.get_all(
			"Publicacion Competencia",
			filters={"cuenta_social": self.name},
			fields=["engagement_pct"],
			order_by="fecha_publicacion desc",
			limit=n,
		)
		vals = [p.engagement_pct for p in pubs if p.engagement_pct]
		if vals:
			self.engagement_promedio = round(statistics.median(vals), 2)

		# velocidad_promedio = mediana de velocidad_diaria de snapshots recientes
		vel = frappe.db.sql("""
			SELECT ms.velocidad_diaria
			FROM `tabMetrica Snapshot` ms
			INNER JOIN `tabPublicacion Competencia` p ON ms.parent = p.name
			WHERE p.cuenta_social = %s AND ms.velocidad_diaria IS NOT NULL
			ORDER BY ms.fecha_snapshot DESC
			LIMIT 100
		""", (self.name,), as_dict=True)
		vels = [v.velocidad_diaria for v in vel if v.velocidad_diaria]
		if vels:
			self.velocidad_promedio = round(statistics.median(vels), 2)

		self.save(ignore_permissions=True)
