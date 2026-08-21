"""API endpoints para ingesta de datos scrapeados al Radar de Competencia.

Se usa desde dos lados:
  - Como scheduled job de Frappe (funcion correr_scrape) — el flujo normal.
  - Como endpoints whitelisted para debug/scripts externos.
"""
from __future__ import annotations

import json
import time
import traceback
from collections import defaultdict
from datetime import datetime

import frappe
from frappe.utils import getdate, get_datetime, cint, now_datetime

from marketinghub.api import apify_actor

# Roles permitidos para hacer ingest
INGEST_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
VIEW_ROLES = INGEST_ROLES + ("Marketinghub-Radar-Analista", "Marketinghub-Radar-Ver")

# Precio base por item scrapeado. Es solo el punto de partida: `coste_item()`
# lo re-escala con lo que Apify cobró de verdad, porque estas constantes se
# quedaron cortas (TikTok real ≈ $0.00375/item con la constante en 0.0037).
# Lo que se registra en cada corrida sigue siendo el coste real, no el estimado.
COSTE_ITEM = {"Instagram": 0.0027, "TikTok": 0.0037}

# Calibración: factor que corrige COSTE_ITEM con el histórico real.
CALIBRACION_KEY = "radar_coste_calibracion"
CALIBRACION_TTL = 600
# hacen falta unas cuantas corridas para que el factor no baile con el ruido
CALIBRACION_MIN_CORRIDAS = 3
# un factor absurdo casi siempre es un dato sucio, no un cambio de precio real
CALIBRACION_MIN, CALIBRACION_MAX = 0.5, 3.0

# Clave en redis donde el job publica su avance para que la UI lo lea por polling.
# No se usa publish_realtime porque /radar/settings es una página standalone sin
# el bundle de socket.io de Frappe.
PROGRESO_KEY = "radar_scrape_progreso"
CANCELAR_KEY = "radar_scrape_cancelar"
PROGRESO_TTL = 3600

# marca las corridas reconstruidas desde el histórico de Apify (sin datos de items)
IMPORTADA = "Importado de Apify"


def _set_progreso(pct, paso, estado="corriendo", **extra):
	"""Publica el avance de la corrida. pct 0-100, estado corriendo|ok|error."""
	datos = {"pct": max(0, min(100, int(pct))), "paso": paso, "estado": estado,
	         "ts": time.time()}
	datos.update(extra)
	try:
		frappe.cache().set_value(PROGRESO_KEY, json.dumps(datos), expires_in_sec=PROGRESO_TTL)
	except Exception:
		pass  # el progreso es cosmético: nunca debe tumbar la corrida
	return datos


def _pedir_cancelacion(valor):
	"""Escribe la bandera de cancelación directamente en redis.

	Ojo: `frappe.cache().get_value()` memoriza el valor en `frappe.local.cache`
	durante todo el job, así que el worker leería siempre el primer resultado y
	nunca se enteraría de la cancelación. Por eso se usa redis en crudo."""
	try:
		cache = frappe.cache()
		clave = cache.make_key(CANCELAR_KEY)
		if valor:
			cache.set(clave, "1", ex=PROGRESO_TTL)
		else:
			cache.delete(clave)
	except Exception:
		pass


def _cancelacion_pedida():
	try:
		cache = frappe.cache()
		return bool(cache.get(cache.make_key(CANCELAR_KEY)))
	except Exception:
		return False


@frappe.whitelist()
def cancelar_scrape():
	"""Detiene la corrida en curso y aborta el run que esté vivo en Apify.

	Abortar en Apify es lo que corta el gasto: el ERP puede dejar de esperar, pero
	el run seguiría facturando por su cuenta. Lo ya consumido no se recupera."""
	from frappe.utils.password import get_decrypted_password

	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado", frappe.PermissionError)

	_pedir_cancelacion(True)
	actual = progreso_scrape()
	_set_progreso(actual.get("pct") or 0, "Deteniendo la corrida…", estado="corriendo")

	abortados = []
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if token:
		abortados = apify_actor.abortar_runs(token, act_ids=_act_ids_radar(token))
	return {"ok": True, "abortados": len(abortados)}


@frappe.whitelist()
def progreso_scrape():
	"""Estado de la corrida en curso, para la barra de progreso de /radar/settings."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado", frappe.PermissionError)
	raw = frappe.cache().get_value(PROGRESO_KEY)
	if not raw:
		return {"pct": 0, "paso": "", "estado": "idle"}
	try:
		return json.loads(raw)
	except Exception:
		return {"pct": 0, "paso": "", "estado": "idle"}


def _require_ingest_perm():
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado para ingestar datos del scraper.",
		             frappe.PermissionError)


# ============================================================
# CUENTAS activas (lo consulta el orquestador para saber que scrapear)
# ============================================================
@frappe.whitelist()
def listar_cuentas_activas():
	"""Devuelve las Cuenta Social con activo=1 para que el scraper las procese."""
	_require_ingest_perm()
	return frappe.db.get_all(
		"Cuenta Social",
		filters={"activo": 1},
		fields=["name", "competidor", "plataforma", "handle", "url_perfil"],
	)


@frappe.whitelist()
def obtener_apify_token():
	"""Devuelve el token de Apify guardado en Radar Settings (decrypted)."""
	_require_ingest_perm()
	from frappe.utils.password import get_decrypted_password
	return get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")


# ============================================================
# UPSERT de publicaciones (evita duplicados por url_publicacion)
# ============================================================
@frappe.whitelist()
def upsert_publicacion(
	cuenta_social=None,
	url_publicacion=None,
	id_externo=None,
	fecha_publicacion=None,
	tipo_contenido=None,
	descripcion=None,
	hashtags=None,
	duracion_segundos=None,
	vistas_actual=None,
	likes_actual=None,
	comentarios_actual=None,
	compartidos_actual=None,
	guardados_actual=None,
):
	"""Inserta o actualiza una publicacion. Devuelve dict con name y accion.

	Estrategia:
	  - Buscar por url_publicacion (unique).
	  - Si existe: actualizar solo las metricas (no descripcion/fecha/etc).
	  - Si no existe: crear.
	Los hooks del DocType calculan engagement_pct, score_viralidad, es_viral.
	"""
	_require_ingest_perm()

	if not url_publicacion or not cuenta_social:
		frappe.throw("cuenta_social y url_publicacion son obligatorios.")

	existing_name = frappe.db.get_value(
		"Publicacion Competencia", {"url_publicacion": url_publicacion}, "name"
	)
	if existing_name:
		doc = frappe.get_doc("Publicacion Competencia", existing_name)
		accion = "update"
		# Solo actualizar metricas (los campos "vivos")
		if vistas_actual is not None:      doc.vistas_actual = cint(vistas_actual)
		if likes_actual is not None:       doc.likes_actual = cint(likes_actual)
		if comentarios_actual is not None: doc.comentarios_actual = cint(comentarios_actual)
		if compartidos_actual is not None: doc.compartidos_actual = cint(compartidos_actual)
		if guardados_actual is not None:   doc.guardados_actual = cint(guardados_actual)
	else:
		doc = frappe.new_doc("Publicacion Competencia")
		doc.cuenta_social = cuenta_social
		doc.url_publicacion = url_publicacion
		doc.id_externo = id_externo
		doc.fecha_publicacion = getdate(fecha_publicacion) if fecha_publicacion else None
		doc.tipo_contenido = tipo_contenido
		doc.descripcion = descripcion or ""
		doc.hashtags = hashtags or ""
		doc.duracion_segundos = cint(duracion_segundos) if duracion_segundos else 0
		doc.vistas_actual = cint(vistas_actual or 0)
		doc.likes_actual = cint(likes_actual or 0)
		doc.comentarios_actual = cint(comentarios_actual or 0)
		doc.compartidos_actual = cint(compartidos_actual or 0)
		doc.guardados_actual = cint(guardados_actual or 0)
		accion = "insert"

	doc.save(ignore_permissions=True)

	# Registrar snapshot diario (aunque sea update)
	_registrar_snapshot(doc)

	frappe.db.commit()
	return {"ok": True, "name": doc.name, "accion": accion,
	        "es_viral": bool(doc.es_viral), "engagement_pct": doc.engagement_pct}


def _registrar_snapshot(doc):
	"""Agrega o actualiza el snapshot de metricas de HOY para esta publicacion."""
	from datetime import date
	hoy = date.today()
	# ver si ya existe snapshot de hoy en historico_metricas
	existente = None
	for snap in doc.historico_metricas or []:
		if snap.fecha_snapshot == hoy:
			existente = snap
			break
	if existente:
		existente.vistas = doc.vistas_actual
		existente.likes = doc.likes_actual
		existente.comentarios = doc.comentarios_actual
		existente.compartidos = doc.compartidos_actual
		existente.guardados = doc.guardados_actual
	else:
		doc.append("historico_metricas", {
			"fecha_snapshot": hoy,
			"vistas": doc.vistas_actual,
			"likes": doc.likes_actual,
			"comentarios": doc.comentarios_actual,
			"compartidos": doc.compartidos_actual,
			"guardados": doc.guardados_actual,
		})
	doc.save(ignore_permissions=True)


# ============================================================
# CORRIDA COMPLETA — scheduled job y trigger manual
# ============================================================
def _map_instagram(item):
	tipo_map = {"Image": "Post", "Sidecar": "Carrusel", "Video": "Reel"}
	tipo = tipo_map.get(item.get("type"), "Post")
	if item.get("productType") == "clips":
		tipo = "Reel"
	return {
		"url_publicacion": item.get("url"),
		"id_externo": item.get("shortCode"),
		"fecha_publicacion": (item.get("timestamp") or "")[:10] or None,
		"tipo_contenido": tipo,
		"descripcion": (item.get("caption") or "").strip(),
		"hashtags": " ".join(f"#{h}" for h in (item.get("hashtags") or [])),
		"duracion_segundos": int(item.get("videoDuration") or 0),
		"vistas_actual": item.get("videoPlayCount") or item.get("videoViewCount") or 0,
		"likes_actual": item.get("likesCount") or 0,
		"comentarios_actual": item.get("commentsCount") or 0,
		"compartidos_actual": 0,
		"guardados_actual": 0,
		"_owner_username": (item.get("ownerUsername") or "").lower(),
		"_input_url": (item.get("inputUrl") or "").rstrip("/"),
	}


def _map_tiktok(item):
	author = item.get("authorMeta") or {}
	hashtags = " ".join(
		f"#{h.get('name', '')}" for h in (item.get("hashtags") or [])
		if isinstance(h, dict)
	)
	return {
		"url_publicacion": item.get("webVideoUrl"),
		"id_externo": str(item.get("id") or ""),
		"fecha_publicacion": (item.get("createTimeISO") or "")[:10] or None,
		"tipo_contenido": "Video",
		"descripcion": (item.get("text") or "").strip(),
		"hashtags": hashtags,
		"duracion_segundos": int(item.get("videoMeta", {}).get("duration") or 0),
		"vistas_actual": item.get("playCount") or 0,
		"likes_actual": item.get("diggCount") or 0,
		"comentarios_actual": item.get("commentCount") or 0,
		"compartidos_actual": item.get("shareCount") or 0,
		"guardados_actual": item.get("collectCount") or 0,
		"_owner_username": (author.get("name") or "").lower().lstrip("@"),
		"_seguidores": author.get("fans"),
	}


def limites_por_marca():
	"""{competidor: limite_posts} para las marcas que tienen un límite propio."""
	filas = frappe.db.get_all(
		"Competidor",
		filters={"limite_posts": [">", 0]},
		fields=["name", "limite_posts"],
	)
	return {f["name"]: int(f["limite_posts"]) for f in filas}


def marcas_pausadas():
	"""Competidores excluidos del scrapeo (interruptor de pausa por marca)."""
	filas = frappe.db.get_all("Competidor", filters={"pausar_radar": 1}, pluck="name")
	return set(filas)


def _limite_de(cuenta, limites, limit_ig, limit_tt, techo=0, override=0):
	"""El límite de la marca manda; si no tiene, el default global de su red.

	`override` es el límite puntual que pide el diálogo del ▶ para una sola
	corrida: manda sobre el de la marca pero no se guarda en el doctype.

	`techo` (max_posts_marca) recorta el resultado venga de donde venga: es el
	único punto por el que pasan todas las corridas, así que subir el límite por
	la vía del doctype —o del override— tampoco lo salta."""
	if override and int(override) > 0:
		limite = int(override)
	else:
		propio = limites.get(cuenta.get("competidor")) or 0
		limite = propio if propio > 0 else (
			limit_ig if cuenta["plataforma"] == "Instagram" else limit_tt
		)
	return min(limite, techo) if techo else limite


def techo_posts():
	"""Máximo de posts que se le puede pedir a una marca. 0 = sin techo."""
	return int(frappe.get_cached_doc("Radar Settings").get("max_posts_marca") or 0)


def correr_scrape(limit_per_profile=None, origen="Programada", disparada_por=None,
                  solo_marca=None, desde=None, hasta=None, completa=False,
                  limite=None, incremental=None):
	"""Se invoca desde el scheduled job o manualmente. NO usa HTTP — corre in-process.

	El scrapeo va marca por marca: cada marca en cada red es una llamada
	independiente a Apify, así se sabe cuántos items trajo y cuánto costó cada una.
	El límite de posts sale de `Competidor.limite_posts` y, si la marca no tiene uno
	propio, del default global de Radar Settings según la red.

	limit_per_profile: fallback global si Radar Settings no tiene nada configurado.
	solo_marca: si se pasa un Competidor, se scrapea únicamente esa marca.
	limite: límite puntual para esta corrida, sin tocar la config de la marca.
	incremental: fuerza el modo para esta corrida (None = el de Radar Settings)."""
	from frappe.utils.password import get_decrypted_password

	inicio = time.time()
	stats = {"insert": 0, "update": 0, "skip": 0, "error": 0}
	log_lines = []
	items_por_red = {"Instagram": 0, "TikTok": 0}
	_pedir_cancelacion(False)   # limpiar una cancelación vieja antes de empezar
	_set_progreso(2, "Leyendo configuración…")

	settings = frappe.get_cached_doc("Radar Settings")
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		msg = "apify_token no configurado en Radar Settings"
		_registrar_corrida(0, stats, "error", msg)
		_set_progreso(100, msg, estado="error")
		frappe.log_error(msg, "Radar Scraper")
		return {"ok": False, "error": msg}

	# Defaults por red social (con fallback al valor global legacy)
	fallback = int(limit_per_profile or settings.posts_por_perfil or 20)
	limit_ig = int(settings.posts_por_perfil_ig or fallback)
	limit_tt = int(settings.posts_por_perfil_tiktok or fallback)
	limites = limites_por_marca()

	cuentas = frappe.db.get_all(
		"Cuenta Social",
		filters={"activo": 1},
		fields=["name", "competidor", "plataforma", "handle", "url_perfil"],
	)
	if not cuentas:
		_registrar_corrida(0, stats, "ok", "sin cuentas activas")
		_set_progreso(100, "No hay cuentas activas que scrapear.", estado="ok")
		return {"ok": True, "mensaje": "sin cuentas activas"}

	# Un grupo = una marca en una red = una llamada a Apify. Se scrapea marca por
	# marca para poder imputarle a cada una sus items y su coste real.
	pausadas = marcas_pausadas()
	grupos = defaultdict(list)
	for c in cuentas:
		if c["plataforma"] not in ("Instagram", "TikTok"):
			continue
		if solo_marca and c["competidor"] != solo_marca:
			continue
		if c["competidor"] in pausadas:
			continue
		grupos[(c["competidor"], c["plataforma"])].append(c)

	if not grupos:
		if solo_marca and solo_marca in pausadas:
			aviso = f"la marca {solo_marca} está pausada"
		elif solo_marca:
			aviso = f"la marca {solo_marca} no tiene cuentas activas de Instagram/TikTok"
		else:
			aviso = "sin cuentas de Instagram/TikTok activas"
		_registrar_corrida(0, stats, "ok", aviso)
		_set_progreso(100, aviso.capitalize(), estado="ok")
		return {"ok": True, "mensaje": aviso}

	# El tramo 5→95 se reparte entre los grupos; dentro de cada uno, la llamada a
	# Apify consume el 60% del tramo y los upserts el 40% restante.
	claves = sorted(grupos.keys())
	ancho = 90.0 / len(claves)
	techo = techo_posts()
	# el override vive fuera del bucle: dentro, `limite` es el de cada grupo
	override = int(limite or 0)
	# `completa` es la vía de escape para refrescar métricas de posts ya guardados.
	# El diálogo del ▶ manda su propio modo: el switch global es solo el default.
	if incremental is None:
		incremental = bool(int(settings.get("modo_incremental") or 0))
	incremental = bool(int(incremental)) and not completa
	por_marca = []
	sin_credito = False
	cancelada = False

	for i, (marca, plataforma) in enumerate(claves):
		# la cancelación se atiende entre llamadas: la que ya está en vuelo se
		# aborta desde Apify, no desde aquí
		if _cancelacion_pedida():
			cancelada = True
			log_lines.append(f"CANCELADA antes de {marca} · {plataforma}")
			break
		base = 5 + ancho * i
		delcaso = grupos[(marca, plataforma)]
		limite = _limite_de(delcaso[0], limites, limit_ig, limit_tt, techo, override)
		g_desde, g_hasta, modo = _ventana_de(delcaso, incremental, desde, hasta)
		antes = dict(stats)
		fila = {"marca": marca, "plataforma": plataforma, "limite": limite,
		        "items": 0, "inicio_epoch": time.time(), "fin_epoch": None, "error": ""}
		_set_progreso(base, f"{marca} · {plataforma} · pidiendo {limite} ({modo})…")
		try:
			items = _scrape_grupo(token, plataforma, delcaso, limite, g_desde, g_hasta)
			fila["fin_epoch"] = time.time()
			fila["items"] = len(items)
			items_por_red[plataforma] += len(items)
			_set_progreso(base + ancho * 0.6,
			              f"{marca} · {plataforma} · procesando {len(items)} items…")
			pinned_skip = _procesar_items(
				plataforma, items, delcaso, stats,
				lambda hechos, total: _set_progreso(
					base + ancho * (0.6 + 0.4 * (hechos / total if total else 1)),
					f"{marca} · {plataforma} · {hechos}/{total} guardados",
				),
			)
			log_lines.append(
				f"{marca} · {plataforma} · límite {limite} · {modo} · {len(items)} items "
				f"({pinned_skip} anclados descartados)"
			)
		except Exception as e:
			fila["fin_epoch"] = time.time()
			if _cancelacion_pedida():
				# el run se abortó desde Apify: no es un fallo, es la cancelación
				cancelada = True
				fila["error"] = "Cancelada"
				log_lines.append(f"{marca} · {plataforma} · CANCELADA")
				por_marca.append(fila)
				break
			stats["error"] += 1
			if _es_sin_credito(e):
				sin_credito = True
				fila["error"] = "Sin crédito en Apify"
				log_lines.append(f"{marca} · {plataforma} · SIN CRÉDITO en Apify")
			else:
				fila["error"] = str(e)[:140]
				log_lines.append(f"{marca} · {plataforma} · ERROR: {e}")
				frappe.log_error(traceback.format_exc(), f"Radar Scraper · {marca} · {plataforma}")
		fila["insertados"] = stats["insert"] - antes["insert"]
		fila["actualizados"] = stats["update"] - antes["update"]
		fila["saltados"] = stats["skip"] - antes["skip"]
		fila["errores"] = stats["error"] - antes["error"]
		por_marca.append(fila)

	duracion = round(time.time() - inicio, 1)
	resumen = f"insert={stats['insert']} update={stats['update']} skip={stats['skip']} error={stats['error']}"
	if cancelada:
		estado = "cancelada"
	elif sin_credito:
		estado = "error"
	else:
		estado = "ok" if stats["error"] == 0 else "warn"
	detalle = " · ".join(log_lines) + " · " + resumen
	_registrar_corrida(duracion, stats, estado, detalle)

	_set_progreso(97, "Consultando el coste en Apify…")
	coste = _registrar_gasto(
		token, inicio, duracion, stats, estado, detalle, items_por_red,
		origen, disparada_por, por_marca, solo_marca,
	)

	frappe.db.commit()
	_pedir_cancelacion(False)
	if cancelada:
		_set_progreso(
			100,
			f"Corrida detenida · {stats['update'] + stats['insert']} publicaciones guardadas"
			f" · ${coste['coste_usd']:.3f} consumidos",
			estado="cancelada", stats=stats, duracion=duracion, coste=coste,
		)
	elif sin_credito:
		credito_apify(forzar=True)  # refrescar el saldo que pinta la página
		_set_progreso(
			100,
			"Se agotó el crédito de Apify: recarga el plan para volver a scrapear.",
			estado="error", stats=stats, duracion=duracion, coste=coste,
		)
	else:
		_set_progreso(
			100,
			f"Listo · {stats['insert']} nuevas, {stats['update']} actualizadas"
			+ (f", {stats['error']} errores" if stats["error"] else "")
			+ f" · ${coste['coste_usd']:.3f}",
			estado=estado, stats=stats, duracion=duracion, coste=coste,
		)
	return {"ok": True, "stats": stats, "duracion_s": duracion, "coste": coste}


def _es_sin_credito(e):
	"""Apify devuelve 402 not-enough-usage cuando se agotó el crédito del ciclo."""
	return "not-enough-usage" in str(e) or "HTTP 402" in str(e)


def _act_ids_radar(token):
	"""IDs de los actores que usa el Radar (IG y TikTok), para no contar los de Ads."""
	clave = "radar_apify_act_ids"
	cacheado = frappe.cache().get_value(clave)
	if cacheado:
		try:
			return set(json.loads(cacheado))
		except Exception:
			pass
	ids = set()
	for slug in (apify_actor.INSTAGRAM_ACTOR, apify_actor.TIKTOK_ACTOR):
		act_id = apify_actor.resolver_act_id(token, slug)
		if act_id:
			ids.add(act_id)
	if ids:
		frappe.cache().set_value(clave, json.dumps(sorted(ids)), expires_in_sec=86400)
	return ids


def _repartir_coste(runs, por_marca):
	"""Asigna cada run de Apify a la marca en cuya ventana temporal arrancó.

	Como las marcas se scrapean en serie, el run que arrancó entre el inicio y el
	fin de la llamada de una marca es suyo. Devuelve el nº de runs sin dueño."""
	huerfanos = 0
	for run in runs:
		duenio = None
		for fila in por_marca:
			# margen de 20 s: el run arranca en Apify un pelín antes de que la
			# petición HTTP nos devuelva el control
			desde = fila["inicio_epoch"] - 20
			hasta = (fila["fin_epoch"] or fila["inicio_epoch"]) + 20
			if desde <= run["inicio_epoch"] <= hasta:
				duenio = fila
				break
		if duenio is None:
			huerfanos += 1
			continue
		duenio["coste_usd"] = round(duenio.get("coste_usd", 0) + run["usd"], 4)
		duenio["runs"] = duenio.get("runs", 0) + 1
	return huerfanos


def _registrar_gasto(token, inicio, duracion, stats, estado, detalle, items_por_red,
                     origen, disparada_por, por_marca=None, alcance=None):
	"""Crea el Radar Corrida con el coste real de Apify (o el estimado si falla)."""
	por_marca = por_marca or []
	precio = coste_item()
	estimado = round(
		items_por_red["Instagram"] * precio["Instagram"]
		+ items_por_red["TikTok"] * precio["TikTok"], 4
	)
	# margen de 60 s hacia atrás: el run arranca en Apify antes de que volvamos aquí
	runs = apify_actor.listar_runs(token, 100, act_ids=_act_ids_radar(token))
	if runs is None:
		real, n_runs = None, 0
	else:
		mios = [r for r in runs if r["inicio_epoch"] >= inicio - 60]
		real = round(sum(r["usd"] for r in mios), 4)
		n_runs = len(mios)
		_repartir_coste(mios, por_marca)
	confirmado = real is not None and n_runs > 0

	if not confirmado:
		# sin confirmación de Apify, cada marca se queda con su parte estimada
		for fila in por_marca:
			fila["coste_usd"] = round(fila["items"] * precio[fila["plataforma"]], 4)
			fila["coste_real"] = 0
	else:
		# las filas a las que no se pudo emparejar un run se reparten el sobrante
		# del total real (proporcional a items), para que la suma por marca cuadre
		sin_run = [f for f in por_marca if "coste_usd" not in f]
		sobrante = max(real - sum(f.get("coste_usd", 0) for f in por_marca), 0)
		base = sum(f["items"] for f in sin_run)
		for fila in por_marca:
			if "coste_usd" in fila:
				fila["coste_real"] = 1
				continue
			peso = (fila["items"] / base) if base else (1.0 / len(sin_run))
			fila["coste_usd"] = round(sobrante * peso, 4)
			fila["coste_real"] = 0

	doc = frappe.new_doc("Radar Corrida")
	doc.fecha_inicio = frappe.utils.add_to_date(now_datetime(), seconds=-int(duracion))
	doc.estado = estado
	doc.origen = origen if origen in ("Manual", "Programada") else "Programada"
	doc.alcance = alcance or "Todas"
	doc.disparada_por = disparada_por or "Scheduler"
	doc.duracion_segundos = duracion
	doc.coste_usd = real if confirmado else estimado
	doc.coste_estimado_usd = estimado
	doc.coste_real = int(confirmado)
	doc.runs_apify = n_runs
	doc.items_total = items_por_red["Instagram"] + items_por_red["TikTok"]
	doc.insertados = stats["insert"]
	doc.actualizados = stats["update"]
	doc.saltados = stats["skip"]
	doc.errores = stats["error"]
	doc.detalle = (detalle or "")[:1000]
	for fila in por_marca:
		doc.append("marcas", {
			"marca": fila["marca"],
			"plataforma": fila["plataforma"],
			"limite": fila["limite"],
			"items": fila["items"],
			"insertados": fila.get("insertados") or 0,
			"actualizados": fila.get("actualizados") or 0,
			"saltados": fila.get("saltados") or 0,
			"errores": fila.get("errores") or 0,
			"coste_usd": fila.get("coste_usd") or 0,
			"coste_real": fila.get("coste_real") or 0,
			"runs_apify": fila.get("runs") or 0,
			"mensaje": fila.get("error") or "",
		})
	doc.insert(ignore_permissions=True)
	return {"coste_usd": float(doc.coste_usd), "estimado": estimado,
	        "real": confirmado, "runs": n_runs,
	        "marcas": [{"marca": f["marca"], "plataforma": f["plataforma"],
	                    "coste_usd": f.get("coste_usd") or 0} for f in por_marca]}


@frappe.whitelist()
def importar_gasto_historico(limite=200, hueco_min=15):
	"""Reconstruye las corridas pasadas desde el histórico de runs de Apify.

	Los runs de una misma corrida van seguidos: se agrupan cortando cuando entre uno
	y el siguiente pasan más de `hueco_min` minutos. Solo crea las corridas que aún
	no estén registradas, así que se puede repetir sin duplicar."""
	from frappe.utils.password import get_decrypted_password

	_require_ingest_perm()
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		frappe.throw("apify_token no configurado en Radar Settings.")

	runs = apify_actor.listar_runs(token, int(limite), act_ids=_act_ids_radar(token))
	if not runs:
		return {"ok": False, "creadas": 0, "mensaje": "Apify no devolvió runs."}

	runs.sort(key=lambda r: r["inicio_epoch"])
	grupos, actual = [], []
	for run in runs:
		if actual and (run["inicio_epoch"] - actual[-1]["fin_epoch"]) > hueco_min * 60:
			grupos.append(actual)
			actual = []
		actual.append(run)
	if actual:
		grupos.append(actual)

	creadas = 0
	for grupo in grupos:
		arranque = frappe.utils.convert_utc_to_system_timezone(
			datetime.utcfromtimestamp(grupo[0]["inicio_epoch"])
		).replace(tzinfo=None)
		# ¿ya hay una corrida registrada en esa ventana?
		ya = frappe.db.get_all("Radar Corrida", limit=1, filters={
			"fecha_inicio": ["between", [
				frappe.utils.add_to_date(arranque, seconds=-600),
				frappe.utils.add_to_date(arranque, seconds=600),
			]],
		})
		if ya:
			continue
		fallidos = sum(1 for r in grupo if r["estado"] != "SUCCEEDED")
		doc = frappe.new_doc("Radar Corrida")
		doc.fecha_inicio = arranque
		doc.estado = "warn" if fallidos else "ok"
		doc.origen = "Programada"
		doc.disparada_por = IMPORTADA
		doc.duracion_segundos = round(grupo[-1]["fin_epoch"] - grupo[0]["inicio_epoch"], 1)
		doc.coste_usd = round(sum(r["usd"] for r in grupo), 4)
		doc.coste_estimado_usd = 0
		doc.coste_real = 1
		doc.runs_apify = len(grupo)
		doc.detalle = (
			f"Reconstruida desde el histórico de Apify: {len(grupo)} runs"
			+ (f", {fallidos} no exitosos" if fallidos else "")
			+ ". Sin conteo de items (no quedó registro en el ERP)."
		)
		doc.insert(ignore_permissions=True)
		creadas += 1

	frappe.db.commit()
	return {"ok": True, "creadas": creadas, "grupos": len(grupos)}


def credito_apify(forzar=False):
	"""Crédito restante del ciclo de Apify. Se cachea 10 min: la página lo pinta
	en cada carga y no hace falta preguntar a Apify cada vez."""
	from frappe.utils.password import get_decrypted_password

	clave = "radar_apify_credito"
	if not forzar:
		cacheado = frappe.cache().get_value(clave)
		if cacheado:
			try:
				return json.loads(cacheado)
			except Exception:
				pass
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token")
	if not token:
		return None
	datos = apify_actor.credito(token)
	if datos:
		frappe.cache().set_value(clave, json.dumps(datos), expires_in_sec=600)
	return datos


def calibracion_coste(forzar=False):
	"""Cuánto se desvía COSTE_ITEM del precio que Apify cobra de verdad.

	Devuelve {"factor": k, "corridas": n}, con k = real / estimado sobre las
	corridas que Apify confirmó. Apify factura el run completo (items + compute),
	así que no hay forma de separar el precio de IG del de TikTok: se escalan los
	dos por el mismo factor y se conserva la proporción entre ellos."""
	if not forzar:
		guardado = frappe.cache().get_value(CALIBRACION_KEY)
		if guardado:
			try:
				return json.loads(guardado)
			except Exception:
				pass

	filas = frappe.db.sql("""
		SELECT c.name AS corrida, c.coste_usd AS real_usd,
		       SUM(CASE WHEN m.plataforma = 'Instagram' THEN m.items ELSE 0 END) AS ig,
		       SUM(CASE WHEN m.plataforma = 'TikTok'    THEN m.items ELSE 0 END) AS tt
		FROM `tabRadar Corrida` c
		JOIN `tabRadar Corrida Marca` m ON m.parent = c.name
		WHERE c.coste_real = 1 AND c.coste_usd > 0
		GROUP BY c.name, c.coste_usd
		HAVING ig + tt > 0
		ORDER BY MAX(c.fecha_inicio) DESC
		LIMIT 30
	""", as_dict=True)

	real = sum(float(f["real_usd"] or 0) for f in filas)
	estimado = sum(
		int(f["ig"] or 0) * COSTE_ITEM["Instagram"]
		+ int(f["tt"] or 0) * COSTE_ITEM["TikTok"]
		for f in filas
	)
	datos = {"factor": 1.0, "corridas": len(filas)}
	if len(filas) >= CALIBRACION_MIN_CORRIDAS and estimado > 0:
		datos["factor"] = round(
			min(max(real / estimado, CALIBRACION_MIN), CALIBRACION_MAX), 4
		)
	try:
		frappe.cache().set_value(CALIBRACION_KEY, json.dumps(datos),
		                         expires_in_sec=CALIBRACION_TTL)
	except Exception:
		pass
	return datos


def coste_item(forzar=False):
	"""Precio por item ya calibrado. Mismas claves que COSTE_ITEM, más el factor."""
	cal = calibracion_coste(forzar)
	k = cal["factor"]
	return {
		"Instagram": COSTE_ITEM["Instagram"] * k,
		"TikTok": COSTE_ITEM["TikTok"] * k,
		"factor": k,
		"corridas": cal["corridas"],
	}


def estimar_corrida(solo_marca=None, limite=None):
	"""Coste estimado de una corrida: perfiles activos × su límite × precio.

	`limite` es el override puntual del diálogo del ▶: sin él se estima con la
	config guardada, que es lo que usa la página al cargar.

	Las marcas en pausa NO suman: no se scrapean, así que meterlas en el total
	solo inflaba la cifra que se le enseña al usuario."""
	s = frappe.get_cached_doc("Radar Settings")
	lim_ig = int(s.posts_por_perfil_ig or 20)
	lim_tt = int(s.posts_por_perfil_tiktok or 20)
	techo = int(s.get("max_posts_marca") or 0)
	precio = coste_item()

	filtros = {"activo": 1, "plataforma": ["in", ("Instagram", "TikTok")]}
	if solo_marca:
		filtros["competidor"] = solo_marca
	cuentas = frappe.db.get_all("Cuenta Social", filters=filtros,
	                            fields=["competidor", "plataforma"])
	if not cuentas:
		return {"total": 0.0, "por_marca": {}, "precio": precio}

	marcas = sorted({c["competidor"] for c in cuentas})
	ajustes = {
		a["name"]: a for a in frappe.db.get_all(
			"Competidor", filters={"name": ["in", marcas]},
			fields=["name", "limite_posts", "pausar_radar"],
		)
	}

	override = int(limite or 0)
	por_marca, total = {}, 0.0
	for c in cuentas:
		ajuste = ajustes.get(c["competidor"]) or {}
		if int(ajuste.get("pausar_radar") or 0):
			continue
		propio = int(ajuste.get("limite_posts") or 0)
		es_ig = c["plataforma"] == "Instagram"
		pide = override or propio or (lim_ig if es_ig else lim_tt)
		if techo:
			pide = min(pide, techo)
		coste = pide * precio["Instagram" if es_ig else "TikTok"]
		por_marca[c["competidor"]] = round(por_marca.get(c["competidor"], 0) + coste, 4)
		total += coste

	return {"total": round(total, 4), "por_marca": por_marca, "precio": precio}


def _consumo_ciclo():
	"""Cuánto se lleva gastado en el ciclo de facturación actual de Apify.

	La cifra buena es la de Apify (incluye gasto de fuera del Radar). Si la API
	no contesta, se cae al acumulado de Radar Corrida desde el inicio del ciclo,
	que se deduce restando un mes a la fecha de renovación."""
	cred = credito_apify()
	if cred and cred.get("limite"):
		return float(cred.get("usado") or 0), cred

	desde = frappe.utils.add_months(frappe.utils.nowdate(), -1)
	if cred and cred.get("renueva"):
		desde = frappe.utils.add_months(cred["renueva"][:10], -1)
	gastado = frappe.db.sql("""
		SELECT COALESCE(SUM(coste_usd), 0) FROM `tabRadar Corrida`
		WHERE fecha_inicio >= %s
	""", (desde,))[0][0]
	return float(gastado or 0), cred


def _validar_tope_ciclo(solo_marca=None, limite=None):
	"""Bloquea la corrida si se pasa del tope del ciclo.

	Se valida con el estimado porque el coste real solo se sabe cuando Apify ya
	cobró: para entonces frenar no sirve de nada."""
	tope = float(frappe.get_cached_doc("Radar Settings").get("tope_ciclo_usd") or 0)
	if not tope:
		return

	gastado, _ = _consumo_ciclo()
	estimado = estimar_corrida(solo_marca, limite)["total"]
	if gastado + estimado > tope:
		frappe.throw(
			f"Este ciclo llevas ${gastado:.2f} y la corrida sumaría ≈${estimado:.3f}: "
			f"se pasa del tope de ${tope:.2f}. Baja el límite de posts, pausa marcas "
			f"o sube el tope."
		)


@frappe.whitelist()
def resumen_gasto(limite=8):
	"""Gasto en Apify: última corrida, mes en curso, total y las últimas corridas."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(VIEW_ROLES)):
		frappe.throw("Acceso denegado", frappe.PermissionError)

	ultimas = frappe.db.get_all(
		"Radar Corrida",
		fields=["name", "fecha_inicio", "estado", "origen", "alcance", "coste_usd",
		        "coste_real", "items_total", "insertados", "actualizados",
		        "duracion_segundos", "disparada_por"],
		order_by="fecha_inicio desc",
		limit=int(limite),
	)
	total = frappe.db.sql("""
		SELECT COALESCE(SUM(coste_usd), 0), COUNT(*) FROM `tabRadar Corrida`
	""")[0]
	mes = frappe.db.sql("""
		SELECT COALESCE(SUM(coste_usd), 0), COUNT(*) FROM `tabRadar Corrida`
		WHERE fecha_inicio >= %s
	""", (frappe.utils.get_first_day(frappe.utils.nowdate()),))[0]

	desde_mes = frappe.utils.get_first_day(frappe.utils.nowdate())

	# desglose por marca y red: acumulado, mes en curso y coste
	filas = frappe.db.sql("""
		SELECT m.marca AS marca, m.plataforma AS plataforma,
		       SUM(m.coste_usd) AS total,
		       SUM(CASE WHEN c.fecha_inicio >= %(desde)s THEN m.coste_usd ELSE 0 END) AS mes,
		       SUM(m.items) AS items,
		       SUM(CASE WHEN c.fecha_inicio >= %(desde)s THEN m.items ELSE 0 END) AS items_mes,
		       COUNT(DISTINCT m.parent) AS corridas
		FROM `tabRadar Corrida Marca` m
		JOIN `tabRadar Corrida` c ON c.name = m.parent
		GROUP BY m.marca, m.plataforma
	""", {"desde": desde_mes}, as_dict=True)

	por_marca, por_red = {}, {}
	for f in filas:
		clave = "ig" if f["plataforma"] == "Instagram" else "tt"
		m = por_marca.setdefault(f["marca"], {
			"marca": f["marca"], "total": 0.0, "mes": 0.0, "items": 0,
			"items_ig": 0, "items_tt": 0, "corridas": 0,
		})
		m["total"] += float(f["total"] or 0)
		m["mes"] += float(f["mes"] or 0)
		m["items"] += int(f["items"] or 0)
		m["items_" + clave] += int(f["items"] or 0)
		m["corridas"] = max(m["corridas"], int(f["corridas"] or 0))

		r = por_red.setdefault(f["plataforma"], {"items": 0, "items_mes": 0,
		                                         "total": 0.0, "mes": 0.0})
		r["items"] += int(f["items"] or 0)
		r["items_mes"] += int(f["items_mes"] or 0)
		r["total"] += float(f["total"] or 0)
		r["mes"] += float(f["mes"] or 0)

	por_marca = sorted(por_marca.values(), key=lambda m: m["total"], reverse=True)

	# lo que trajo cada marca en la última corrida, separado por red
	ultima_por_marca = {}
	if ultimas:
		for fila in frappe.db.get_all(
			"Radar Corrida Marca",
			filters={"parent": ultimas[0]["name"]},
			fields=["marca", "plataforma", "coste_usd", "items"],
		):
			acc = ultima_por_marca.setdefault(
				fila["marca"], {"coste": 0.0, "items": 0, "ig": 0, "tt": 0})
			acc["coste"] += float(fila["coste_usd"] or 0)
			acc["items"] += int(fila["items"] or 0)
			acc["ig" if fila["plataforma"] == "Instagram" else "tt"] += int(fila["items"] or 0)

	return {
		"ultimas": ultimas,
		"total_usd": float(total[0] or 0),
		"total_corridas": int(total[1] or 0),
		"mes_usd": float(mes[0] or 0),
		"mes_corridas": int(mes[1] or 0),
		"ultima_usd": float(ultimas[0]["coste_usd"]) if ultimas else 0.0,
		"por_marca": por_marca,
		"por_red": por_red,
		"ultima_por_marca": ultima_por_marca,
		"credito": credito_apify(),
		"presupuesto": _presupuesto(),
		"precio": coste_item(),
		"propias": _gasto_propio(),
	}


def _gasto_propio():
	"""Solo las corridas que lanzó alguien desde el panel.

	Las importadas del histórico de Apify tienen coste real pero ningún conteo de
	items, así que promediarlas junto con las tuyas da una cifra que no describe
	ni unas ni otras."""
	fila = frappe.db.sql("""
		SELECT COUNT(*), COALESCE(SUM(coste_usd), 0) FROM `tabRadar Corrida`
		WHERE disparada_por != %s
	""", (IMPORTADA,))[0]
	n, usd = int(fila[0] or 0), float(fila[1] or 0)
	return {"corridas": n, "usd": usd, "promedio": (usd / n) if n else 0.0}


def _presupuesto():
	"""Crédito del ciclo, tope propio y predicciones de a dónde va el gasto.

	El "ritmo" se calcula sobre el consumo del ciclo en curso, no sobre el
	histórico completo: interesa a qué velocidad se está quemando ahora."""
	tope = float(frappe.get_cached_doc("Radar Settings").get("tope_ciclo_usd") or 0)
	gastado, cred = _consumo_ciclo()

	limite = float((cred or {}).get("limite") or 0)
	# el techo real es el más bajo de los dos: tu tope o lo que Apify te da
	techo = min([x for x in (tope, limite) if x] or [0])
	restante = round(max(techo - gastado, 0), 4) if techo else None

	renueva = (cred or {}).get("renueva")
	dias_ciclo = None
	if renueva:
		inicio = frappe.utils.add_months(renueva[:10], -1)
		dias_ciclo = frappe.utils.date_diff(frappe.utils.nowdate(), inicio)

	# ritmo diario: se cuenta el día en curso como uno completo para no dividir
	# entre cero ni inflar el ritmo con unas horas sueltas
	ritmo = round(gastado / max(dias_ciclo or 1, 1), 4)
	propio = _gasto_propio()
	media_corrida = propio["promedio"]
	corrida_completa = estimar_corrida()["total"]

	agotamiento, dias_restantes = None, None
	if restante and ritmo > 0:
		dias_restantes = int(restante / ritmo)
		agotamiento = frappe.utils.add_days(frappe.utils.nowdate(), dias_restantes)

	dias_a_renovar = frappe.utils.date_diff(renueva[:10], frappe.utils.nowdate()) if renueva else None
	return {
		"tope": tope,
		"limite_apify": limite,
		"techo": techo,
		"gastado": round(gastado, 4),
		"restante": restante,
		"pct": min(100, round(gastado / techo * 100)) if techo else 0,
		"agotado": bool(techo and gastado >= techo),
		"renueva": renueva,
		"dias_a_renovar": dias_a_renovar,
		"ritmo_dia": ritmo,
		"dias_ciclo": dias_ciclo,
		# con uno o dos días de ciclo, un día atípico manda en el promedio y la
		# fecha de agotamiento se dispara: se marca para no venderla como firme
		"ritmo_fiable": bool(dias_ciclo and dias_ciclo >= 3),
		"agotamiento": agotamiento,
		"dias_restantes": dias_restantes,
		# ¿el crédito aguanta hasta la renovación al ritmo actual?
		"llega": None if (dias_restantes is None or dias_a_renovar is None)
		         else dias_restantes >= dias_a_renovar,
		"corridas_media": int(restante / media_corrida) if restante and media_corrida else None,
		"corridas_completas": int(restante / corrida_completa) if restante and corrida_completa else None,
		"media_corrida": round(media_corrida, 4),
		"corrida_completa": corrida_completa,
	}


def _scrape_grupo(token, plataforma, cuentas, limite, desde=None, hasta=None):
	if plataforma == "Instagram":
		urls = [c["url_perfil"] for c in cuentas if c.get("url_perfil")]
		# el actor de Instagram no tiene «hasta»: se ignora a propósito
		return apify_actor.scrape_instagram(token, urls, limite, desde=desde) if urls else []
	handles = [c["handle"] for c in cuentas if c.get("handle")]
	return apify_actor.scrape_tiktok(token, handles, limite, desde=desde, hasta=hasta) if handles else []


def _ultimo_post_de(cuentas):
	"""Fecha del post más reciente ya guardado del grupo. None si no hay ninguno.

	Se toma el mínimo entre las cuentas del grupo: si una va más atrasada, el
	filtro tiene que cubrirla o se perdería lo suyo."""
	nombres = [c["name"] for c in cuentas]
	if not nombres:
		return None
	filas = frappe.db.sql("""
		SELECT cuenta_social, MAX(fecha_publicacion) AS ultima
		FROM `tabPublicacion Competencia`
		WHERE cuenta_social IN %(nombres)s AND fecha_publicacion IS NOT NULL
		GROUP BY cuenta_social
	""", {"nombres": nombres}, as_dict=True)
	# una cuenta sin nada guardado necesita corrida completa: no se filtra
	if len(filas) < len(nombres):
		return None
	fechas = [f["ultima"] for f in filas if f["ultima"]]
	return min(fechas) if fechas else None


def _ventana_de(cuentas, incremental, desde, hasta):
	"""Qué ventana de fechas se le pide al actor para este grupo.

	La ventana manual manda sobre el incremental: si el usuario pidió histórico,
	es porque quiere justo lo que el incremental descartaría."""
	if desde or hasta:
		return desde, hasta, f"ventana {desde or '—'} → {hasta or 'hoy'}"
	if not incremental:
		return None, None, "completa"
	ultimo = _ultimo_post_de(cuentas)
	if not ultimo:
		return None, None, "completa (sin histórico)"
	return str(ultimo), None, f"nuevos desde {ultimo}"


def _procesar_items(plataforma, items, cuentas, stats, avisar):
	"""Mapea y guarda los items de un grupo. Devuelve cuántos pinned se descartaron."""
	url_to_cuenta = {c["url_perfil"].rstrip("/"): c for c in cuentas if c.get("url_perfil")}
	handle_to_cuenta = {c["handle"].lower(): c for c in cuentas if c.get("handle")}
	pinned_skip = 0
	total = len(items)
	for n, item in enumerate(items, 1):
		# Los posts anclados (pinned) son viejos con metricas acumuladas
		# y distorsionan el baseline. Se descartan.
		if item.get("isPinned"):
			pinned_skip += 1
			continue
		if plataforma == "Instagram":
			payload = _map_instagram(item)
			owner = payload.pop("_owner_username")
			input_url = payload.pop("_input_url")
			cuenta = url_to_cuenta.get(input_url) or handle_to_cuenta.get(owner)
		else:
			payload = _map_tiktok(item)
			payload.pop("_seguidores", None)
			cuenta = handle_to_cuenta.get(payload.pop("_owner_username", ""))
		if not cuenta or not payload["url_publicacion"]:
			stats["skip"] += 1
			continue
		payload["cuenta_social"] = cuenta["name"]
		_ejecutar_upsert(payload, stats)
		if n % 5 == 0 or n == total:
			avisar(n, total)
	return pinned_skip


def _ejecutar_upsert(payload, stats):
	try:
		# upsert inline (no via HTTP)
		url_pub = payload["url_publicacion"]
		existing = frappe.db.get_value(
			"Publicacion Competencia", {"url_publicacion": url_pub}, "name"
		)
		if existing:
			doc = frappe.get_doc("Publicacion Competencia", existing)
			doc.vistas_actual = payload["vistas_actual"]
			doc.likes_actual = payload["likes_actual"]
			doc.comentarios_actual = payload["comentarios_actual"]
			doc.compartidos_actual = payload["compartidos_actual"]
			doc.guardados_actual = payload["guardados_actual"]
			accion = "update"
		else:
			doc = frappe.new_doc("Publicacion Competencia")
			for k, v in payload.items():
				setattr(doc, k, v)
			accion = "insert"
		# Marca cuándo el scraper vio este post por última vez
		doc.fecha_ultimo_scrapeo = now_datetime()
		doc.save(ignore_permissions=True)
		_agregar_snapshot(doc)
		doc.save(ignore_permissions=True)
		stats[accion] += 1
	except Exception as e:
		stats["error"] += 1
		frappe.log_error(f"upsert {payload.get('url_publicacion')}: {e}",
		                 "Radar Scraper · upsert")


def _agregar_snapshot(doc):
	from datetime import date
	hoy = date.today()
	existente = None
	for snap in doc.historico_metricas or []:
		if snap.fecha_snapshot == hoy:
			existente = snap
			break
	campos = dict(vistas=doc.vistas_actual, likes=doc.likes_actual,
	              comentarios=doc.comentarios_actual,
	              compartidos=doc.compartidos_actual,
	              guardados=doc.guardados_actual)
	if existente:
		for k, v in campos.items():
			setattr(existente, k, v)
	else:
		doc.append("historico_metricas", {"fecha_snapshot": hoy, **campos})


def _registrar_corrida(duracion_s, stats, estado, mensaje):
	"""Guarda info de la ultima corrida en Radar Settings."""
	s = frappe.get_single("Radar Settings")
	s.ultima_corrida = now_datetime()
	s.ultima_corrida_estado = estado
	s.ultima_corrida_duracion = duracion_s
	s.ultima_corrida_mensaje = (mensaje or "")[:500]
	s.ultima_corrida_stats = json.dumps(stats)
	# evitamos disparar on_update recursivo:
	s.flags.ignore_scheduler_sync = True
	s.save(ignore_permissions=True)


def _validar_espaciado(marca):
	"""Bloquea repetir una marca antes del plazo mínimo.

	El 15/08 se corrió Ebrand tres veces en 40 minutos: 70 items, $0.24 y cero
	posts nuevos. Repetir el mismo día casi siempre es pagar dos veces lo mismo."""
	horas = int(frappe.get_cached_doc("Radar Settings").get("horas_entre_corridas") or 0)
	if not horas or not marca:
		return
	ultima = frappe.db.sql("""
		SELECT MAX(c.fecha_inicio) FROM `tabRadar Corrida Marca` m
		JOIN `tabRadar Corrida` c ON c.name = m.parent
		WHERE m.marca = %s
	""", (marca,))[0][0]
	if not ultima:
		return
	pasadas = (now_datetime() - ultima).total_seconds() / 3600
	if pasadas < horas:
		frappe.throw(
			f"«{marca}» se scrapeó hace {pasadas:.1f} h y el mínimo entre corridas "
			f"es {horas} h. Volverías a pagar por los mismos posts. "
			f"Puedes bajar el mínimo en la configuración."
		)


@frappe.whitelist()
def ejecutar_scrape_ahora(marca=None, desde=None, hasta=None, completa=0,
                          limite=None, incremental=None):
	"""Endpoint para el botón ▶ de /radar/settings.

	`marca` (un Competidor) limita la corrida a esa marca; sin ella van todas.
	`desde`/`hasta` acotan la ventana de publicación (histórico). `completa`
	ignora el modo incremental para refrescar métricas de posts ya guardados.
	`limite` pide otro nº de posts solo para esta corrida y `incremental` fuerza
	el modo: los dos los manda el diálogo del ▶, que decide por marca."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado", frappe.PermissionError)

	if marca and not frappe.db.exists("Competidor", marca):
		frappe.throw(f"La marca «{marca}» no existe.")

	desde = _fecha_valida(desde, "desde")
	hasta = _fecha_valida(hasta, "hasta")
	if desde and hasta and desde > hasta:
		frappe.throw(f"La fecha «desde» ({desde}) es posterior a «hasta» ({hasta}).")
	limite = _limite_valido(limite)

	# el tope se valida antes de encolar: una vez que Apify corre, ya cobró
	_validar_tope_ciclo(marca, limite)
	# una ventana de histórico es a propósito repetir: el espaciado no aplica
	if not (desde or hasta):
		_validar_espaciado(marca)

	actual = progreso_scrape()
	# si el worker murió a medias, el progreso se queda "corriendo" para siempre:
	# a los 15 min sin avanzar lo damos por muerto y dejamos relanzar
	fresco = (time.time() - float(actual.get("ts") or 0)) < 900
	if actual.get("estado") == "corriendo" and fresco:
		frappe.throw(f"Ya hay una corrida en curso ({actual.get('pct', 0)}%).")

	# 1% de arranque: la UI necesita ver la barra antes de que el worker despierte
	_set_progreso(1, f"Encolando la corrida de {marca}…" if marca else "Encolando la corrida…")
	# Encolar en background — usa los limites de Radar Settings y de cada marca
	frappe.enqueue(
		"marketinghub.api.radar_scraper.correr_scrape",
		queue="long",
		timeout=1800,
		origen="Manual",
		disparada_por=frappe.session.user,
		solo_marca=marca or None,
		desde=desde,
		hasta=hasta,
		completa=bool(int(completa or 0)),
		limite=limite,
		incremental=None if incremental is None else bool(int(incremental)),
	)
	return {"ok": True, "mensaje": f"Corrida de {marca} encolada." if marca else "Corrida encolada."}


def _fecha_valida(valor, etiqueta):
	"""'2026-07-01' -> '2026-07-01'. Vacío -> None. Basura -> error claro."""
	if not valor or not str(valor).strip():
		return None
	try:
		return str(frappe.utils.getdate(valor))
	except Exception:
		frappe.throw(f"La fecha «{etiqueta}» no es válida: {valor}")


def _limite_valido(valor):
	"""Límite puntual del diálogo. Vacío/0 -> None (se usa el de la marca)."""
	if valor in (None, "") or not str(valor).strip():
		return None
	try:
		n = int(float(str(valor).strip()))
	except ValueError:
		frappe.throw(f"El límite de posts debe ser un número: {valor}")
	if n <= 0:
		return None
	techo = techo_posts()
	if techo and n > techo:
		frappe.throw(
			f"Pediste {n} posts y el máximo por marca es {techo}. "
			f"Súbelo en «Máximo por marca» si de verdad quieres pedir más."
		)
	return n


@frappe.whitelist()
def estado_marca(marca):
	"""Lo que hace falta para decidir una corrida de esta marca, por red social.

	Lo pinta el diálogo del ▶ en /radar/settings: cuántos posts hay guardados y
	de qué fechas, si el histórico se quedó a medias, y qué frena la corrida
	(pausa o espaciado mínimo). El coste de cada opción lo calcula la página con
	el precio ya calibrado."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(VIEW_ROLES)):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	if not frappe.db.exists("Competidor", marca):
		frappe.throw(f"La marca «{marca}» no existe.")

	s = frappe.get_cached_doc("Radar Settings")
	limit_ig = int(s.posts_por_perfil_ig or 20)
	limit_tt = int(s.posts_por_perfil_tiktok or 20)
	techo = techo_posts()
	limites = limites_por_marca()

	cuentas = frappe.db.get_all(
		"Cuenta Social",
		filters={"activo": 1, "competidor": marca,
		         "plataforma": ["in", ("Instagram", "TikTok")]},
		fields=["name", "competidor", "plataforma", "handle"],
	)

	# qué hay guardado de cada cuenta: cuántos posts y qué tramo cubren
	guardado = {}
	if cuentas:
		for f in frappe.db.sql("""
			SELECT cuenta_social, COUNT(*) AS n,
			       MIN(fecha_publicacion) AS mn, MAX(fecha_publicacion) AS mx
			FROM `tabPublicacion Competencia`
			WHERE cuenta_social IN %(nombres)s
			GROUP BY cuenta_social
		""", {"nombres": [c["name"] for c in cuentas]}, as_dict=True):
			guardado[f["cuenta_social"]] = f

	# lo que trajo la última corrida de cada red. Si llenó el cupo justo, detrás
	# quedó histórico que nadie pidió: es la pista que faltaba en la pantalla.
	ultima = {}
	for f in frappe.db.sql("""
		SELECT m.plataforma AS plataforma, m.items AS items, m.limite AS limite,
		       c.fecha_inicio AS cuando
		FROM `tabRadar Corrida Marca` m
		JOIN `tabRadar Corrida` c ON c.name = m.parent
		WHERE m.marca = %s
		ORDER BY c.fecha_inicio DESC
	""", (marca,), as_dict=True):
		ultima.setdefault(f["plataforma"], f)

	redes = []
	for plataforma in ("Instagram", "TikTok"):
		delcaso = [c for c in cuentas if c["plataforma"] == plataforma]
		if not delcaso:
			continue
		datos = [guardado.get(c["name"]) or {} for c in delcaso]
		fechas_mn = [d["mn"] for d in datos if d.get("mn")]
		fechas_mx = [d["mx"] for d in datos if d.get("mx")]
		u = ultima.get(plataforma) or {}
		items, cupo = int(u.get("items") or 0), int(u.get("limite") or 0)
		redes.append({
			"plataforma": plataforma,
			"corto": "IG" if plataforma == "Instagram" else "TikTok",
			"cuentas": len(delcaso),
			"posts": sum(int(d.get("n") or 0) for d in datos),
			"desde": str(min(fechas_mn)) if fechas_mn else "",
			"hasta": str(max(fechas_mx)) if fechas_mx else "",
			"limite": _limite_de(delcaso[0], limites, limit_ig, limit_tt, techo),
			# la corrida se comió el cupo entero: hay más histórico sin traer
			"truncada": bool(items and cupo and items >= cupo),
			"ultimo_lote": items,
			"ultimo_cupo": cupo,
		})

	horas_min = int(s.get("horas_entre_corridas") or 0)
	cuando = frappe.db.sql("""
		SELECT MAX(c.fecha_inicio) FROM `tabRadar Corrida Marca` m
		JOIN `tabRadar Corrida` c ON c.name = m.parent
		WHERE m.marca = %s
	""", (marca,))[0][0]
	espera = 0.0
	if horas_min and cuando:
		pasadas = (now_datetime() - cuando).total_seconds() / 3600
		espera = round(max(horas_min - pasadas, 0), 1)

	return {
		"marca": marca,
		"redes": redes,
		"techo": techo,
		"incremental": int(s.get("modo_incremental") or 0),
		"horas_entre_corridas": horas_min,
		# > 0 = el server rechazará la corrida hasta que pasen esas horas
		"espera_horas": espera,
		"ultima": frappe.utils.format_datetime(cuando, "dd/MM/yy HH:mm") if cuando else "",
		"pausada": int(frappe.db.get_value("Competidor", marca, "pausar_radar") or 0),
	}


@frappe.whitelist()
def obtener_estado_scheduler():
	"""Estado actual del job programado y ultima corrida."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES) | {"Marketinghub-Radar-Ver", "Marketinghub-Radar-Analista"}):
		frappe.throw("Permiso denegado", frappe.PermissionError)
	s = frappe.get_single("Radar Settings")
	job = None
	if frappe.db.exists("Scheduled Job Type",
	                    {"method": "marketinghub.api.radar_scraper.correr_scrape"}):
		j = frappe.get_doc("Scheduled Job Type",
		                   {"method": "marketinghub.api.radar_scraper.correr_scrape"})
		job = {
			"cron_format": j.cron_format,
			"stopped": bool(j.stopped),
			"last_execution": str(j.last_execution) if j.last_execution else None,
			"next_execution": str(j.get_next_execution()) if hasattr(j, "get_next_execution") else None,
		}
	return {
		"cron_scrape": s.cron_scrape,
		"preset_frecuencia": getattr(s, "preset_frecuencia", None),
		"ultima_corrida": str(s.ultima_corrida) if s.ultima_corrida else None,
		"ultima_corrida_estado": s.ultima_corrida_estado,
		"ultima_corrida_duracion": s.ultima_corrida_duracion,
		"ultima_corrida_mensaje": s.ultima_corrida_mensaje,
		"ultima_corrida_stats": json.loads(s.ultima_corrida_stats) if s.ultima_corrida_stats else None,
		"scheduled_job": job,
	}
