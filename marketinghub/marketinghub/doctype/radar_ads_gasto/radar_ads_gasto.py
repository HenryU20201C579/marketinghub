# Copyright (c) 2026, Lizaraso-Henry and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class RadarAdsGasto(Document):
	"""Registro histórico de un scrape de ads para una marca.

	Se crea una fila por marca cada vez que corre `correr_scrape_ads` en
	`marketinghub.api.radar_ads_scraper`. Sirve para responder:
	  - Cuánto se ha gastado en scrapear cada marca en total (SUM coste_estimado)
	  - Cuántas veces se scrapeó cada marca
	  - Qué corridas trajeron 0 ads («vacio») o menos de lo pedido («parcial»)
	"""
	pass
