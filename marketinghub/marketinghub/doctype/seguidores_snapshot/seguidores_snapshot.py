# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class SeguidoresSnapshot(Document):
	def before_save(self):
		if not self.parent or not self.fecha:
			return
		previos = frappe.db.get_all(
			"Seguidores Snapshot",
			filters={"parent": self.parent, "fecha": ["<", self.fecha]},
			fields=["seguidores"],
			order_by="fecha desc",
			limit=1,
		)
		if previos:
			self.delta_vs_anterior = (self.seguidores or 0) - (previos[0].seguidores or 0)
		else:
			self.delta_vs_anterior = 0
