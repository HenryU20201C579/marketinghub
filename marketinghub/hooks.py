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
	# --- Radar de Competencia ---
	# N2: colapsado a un solo tile. La navegacion entre secciones (Metricas,
	# Publicaciones, Calendario, Ads Library, Competidores, Ajustes) vive
	# ahora en el navbar horizontal que inyecta radar-sidebar.js dentro de
	# cada pagina /radar/*. Antes eran 6 tiles distintos en el sidebar del
	# /panel — el sidebar externo quedaba saturado con items de Radar.
	{
		"label": "Radar",
		"url": "/radar/metricas",
		"icon": "trending-up",
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
