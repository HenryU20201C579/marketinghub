app_name = "marketinghub"
app_title = "MarketingHub"
app_publisher = "Henry Diaz"
app_description = "Gestion de marketing (Meta Ads, WhatsApp, CTWA, campanas)"
app_email = "henry1395.hd@gmail.com"
app_license = "mit"

required_apps = ["ventahub"]


# Tiles registrados en el launcher (movidos desde ventahub)
launcher_tiles = [
	{
		"label": "Campanas Meta",
		"url": "/campanas_meta",
		"icon": "megaphone",
		"role": "Marketinghub-Marketing-Ver",
	},
	{
		"label": "Meta Ads",
		"url": "/meta_ads",
		"icon": "target",
		"role": "Marketinghub-Marketing-Ver",
	},
	{
		"label": "Anuncios",
		"url": "/anuncios",
		"icon": "megaphone",
		"role": "Marketinghub-Marketing-Ver",
	},
	{
		"label": "Ventas por Campana",
		"url": "/ventas_campanas",
		"icon": "trending-up",
		"role": "Marketinghub-Marketing-Ver",
	},
	{
		"label": "Conversiones CTWA",
		"url": "/conversiones",
		"icon": "trending-up",
		"role": "Marketinghub-Marketing-Ver",
	},
	# --- Radar de Competencia: las 10 secciones de su sidebar ---
	{
		"label": "Radar · Metricas",
		"url": "/radar/metricas",
		"icon": "trending-up",
	},
	{
		"label": "Radar · Publicaciones",
		"url": "/radar/publicaciones",
		"icon": "file-text",
	},
	{
		"label": "Radar · Guiones",
		"url": "/radar/guiones",
		"icon": "pen-tool",
	},
	{
		"label": "Radar · Calendario pubs",
		"url": "/radar/comparativa",
		"icon": "calendar-days",
	},
	{
		"label": "Radar · Agenda guiones",
		"url": "/radar/guiones?vista=calendario",
		"icon": "list-checks",
	},
	{
		"label": "Radar · Ads Library",
		"url": "/radar/ads",
		"icon": "store",
	},
	{
		"label": "Radar · Competidores",
		"url": "/radar/competidores",
		"icon": "users",
	},
	{
		"label": "Radar · Cuentas",
		"url": "/radar/cuentas",
		"icon": "user-square",
	},
	{
		"label": "Radar · Categorias",
		"url": "/radar/categorias",
		"icon": "folder-kanban",
	},
	{
		"label": "Radar · Ajustes",
		"url": "/radar/settings",
		"icon": "clipboard-check",
	},
]


# Document Events se agregaran cuando se active Meta CAPI (M2).
doc_events = {}


# Fixtures: los DocTypes movidos + los nuevos roles Marketinghub-*
fixtures = [
	{"dt": "Role", "filters": [["role_name", "like", "Marketinghub-%"]]},
	{"dt": "DocType", "filters": [["name", "in", [
		"Anuncio",
		"Anuncio Lead Clickeado",
		"Anuncios Asociados",
		"Campana Meta",
		"Configuracion Meta",
		"Conjunto Anuncios",
		"Conjunto Anuncios Asociados",
	]]]},
]


# ------------------------------------------------------------
# Radar de Competencia - scheduler default (editable via UI)
# ------------------------------------------------------------
scheduler_events = {
	"cron": {
		# Default inicial: 6 AM diario. El usuario puede cambiarlo desde
		# /radar/settings — el hook on_update de Radar Settings actualiza
		# el Scheduled Job Type en la DB.
		"0 6 * * *": [
			"marketinghub.api.radar_scraper.correr_scrape",
		],
	},
}
