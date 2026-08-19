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
		"label": "Radar · Calendario pubs",
		"url": "/radar/comparativa",
		"icon": "calendar-days",
	},
	{
		"label": "Radar · Ads Library",
		"url": "/radar/ads",
		"icon": "store",
	},
	{
		# B-Op3+F3: Cuentas y Categorias se unificaron dentro de Competidores
		# (cuentas via acordeon, categorias via modal ⚙️). «Radar · Cuentas» y
		# «Radar · Categorias» ya no aparecen — sus URLs redirigen aqui.
		"label": "Radar · Competidores",
		"url": "/radar/competidores",
		"icon": "users",
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
# Radar de Competencia - sin scrapeo automatico
# ------------------------------------------------------------
# A proposito NO hay scheduler_events: el scrapeo cuesta dinero real en Apify y
# la unica forma de dispararlo es el boton ▶ de /radar/settings, que ademas
# valida los topes de gasto. El cron diario de 6 AM se llevaba el 80% de la
# factura corriendo solo. Si algun dia vuelve a programarse, tiene que pasar
# por _validar_tope_ciclo primero.
