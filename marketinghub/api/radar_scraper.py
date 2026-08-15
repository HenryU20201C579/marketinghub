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

# Precio por item scrapeado, calibrado con el coste real de runs de Apify
# (15/08/26: IG 30 posts = $0.081 y 50 = $0.135; TikTok 20 = $0.075, 50 = $0.186).
# Solo se usa para estimar de antemano: lo que se registra es el coste real.
COSTE_ITEM = {"Instagram": 0.0027, "TikTok": 0.0037}

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
	try:
		if valor:
			frappe.cache().set_value(CANCELAR_KEY, "1", expires_in_sec=PROGRESO_TTL)
		else:
			frappe.cache().delete_value(CANCELAR_KEY)
	except Exception:
		pass


def _cancelacion_pedida():
	try:
		return bool(frappe.cache().get_value(CANCELAR_KEY))
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


def _limite_de(cuenta, limites, limit_ig, limit_tt):
	"""El límite de la marca manda; si no tiene, el default global de su red."""
	propio = limites.get(cuenta.get("competidor")) or 0
	if propio > 0:
		return propio
	return limit_ig if cuenta["plataforma"] == "Instagram" else limit_tt


def correr_scrape(limit_per_profile=None, origen="Programada", disparada_por=None,
                  solo_marca=None):
	"""Se invoca desde el scheduled job o manualmente. NO usa HTTP — corre in-process.

	El scrapeo va marca por marca: cada marca en cada red es una llamada
	independiente a Apify, así se sabe cuántos items trajo y cuánto costó cada una.
	El límite de posts sale de `Competidor.limite_posts` y, si la marca no tiene uno
	propio, del default global de Radar Settings según la red.

	limit_per_profile: fallback global si Radar Settings no tiene nada configurado.
	solo_marca: si se pasa un Competidor, se scrapea únicamente esa marca."""
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
		limite = _limite_de(delcaso[0], limites, limit_ig, limit_tt)
		antes = dict(stats)
		fila = {"marca": marca, "plataforma": plataforma, "limite": limite,
		        "items": 0, "inicio_epoch": time.time(), "fin_epoch": None, "error": ""}
		_set_progreso(base, f"{marca} · {plataforma} · pidiendo {limite}…")
		try:
			items = _scrape_grupo(token, plataforma, delcaso, limite)
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
				f"{marca} · {plataforma} · límite {limite} · {len(items)} items "
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
	estimado = round(
		items_por_red["Instagram"] * COSTE_ITEM["Instagram"]
		+ items_por_red["TikTok"] * COSTE_ITEM["TikTok"], 4
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

	# si Apify no confirmó, cada marca se queda con su parte estimada
	for fila in por_marca:
		if not confirmado or "coste_usd" not in fila:
			fila["coste_usd"] = round(fila["items"] * COSTE_ITEM[fila["plataforma"]], 4)
			fila["coste_real"] = 0
		else:
			fila["coste_real"] = 1

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
	}


def _scrape_grupo(token, plataforma, cuentas, limite):
	if plataforma == "Instagram":
		urls = [c["url_perfil"] for c in cuentas if c.get("url_perfil")]
		return apify_actor.scrape_instagram(token, urls, limite) if urls else []
	handles = [c["handle"] for c in cuentas if c.get("handle")]
	return apify_actor.scrape_tiktok(token, handles, limite) if handles else []


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


@frappe.whitelist()
def ejecutar_scrape_ahora(marca=None):
	"""Endpoint para el boton 'Ejecutar ahora' en /radar/settings.

	`marca` (un Competidor) limita la corrida a esa marca; sin ella van todas."""
	roles = set(frappe.get_roles(frappe.session.user))
	if not (roles & set(INGEST_ROLES)):
		frappe.throw("Permiso denegado", frappe.PermissionError)

	if marca and not frappe.db.exists("Competidor", marca):
		frappe.throw(f"La marca «{marca}» no existe.")

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
	)
	return {"ok": True, "mensaje": f"Corrida de {marca} encolada." if marca else "Corrida encolada."}


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
