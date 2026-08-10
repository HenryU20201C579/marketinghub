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

	def validate(self):
		self._derivar_handle()
		self._validar_no_duplicado()

	def before_save(self):
		self._derivar_handle()

	def _validar_no_duplicado(self):
		"""Impide crear 2 cuentas con mismo (competidor, plataforma, handle)."""
		if not (self.competidor and self.plataforma and self.handle):
			return
		existe = frappe.db.get_value(
			"Cuenta Social",
			{
				"competidor": self.competidor,
				"plataforma": self.plataforma,
				"handle": self.handle,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existe:
			frappe.throw(
				f"Ya existe una Cuenta Social para {self.competidor} en "
				f"{self.plataforma} con handle {self.handle!r} (id: {existe})."
			)

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

