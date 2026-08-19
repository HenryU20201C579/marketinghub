"""Página de configuración del Radar.

Solo lo que hace falta para operar el scrapeo y controlar lo que cuesta: cuántos
posts pedir por marca, el tope de gasto y lo que Apify ha cobrado.

Lo que se quitó y por qué:
- Alertas: `canal_alerta` no lo leía nadie, no existe código que envíe avisos.
- Tiers de viralidad: no tienen relación con el scrapeo ni con el gasto; se
  editan en el doctype Radar Settings.
- Frecuencia: el Radar es solo manual, ya no hay cron que elegir.
- Retención: el campo no borraba nada, no hay job de limpieza.
"""
import json

import frappe
from frappe.utils.password import get_decrypted_password

from marketinghub.api import apify_actor
from marketinghub.api.radar_scraper import (
	IMPORTADA,
	coste_item,
	credito_apify,
	estimar_corrida,
	resumen_gasto,
)

no_cache = 1

ADMIN_ROLES = ("Marketinghub-Radar-Administrar", "System Manager")
VIEW_ROLES = (
	"Marketinghub-Radar-Ver",
	"Marketinghub-Radar-Analista",
	"Marketinghub-Radar-Administrar",
	"System Manager",
)


def _has_role(roles):
	return bool(set(frappe.get_roles(frappe.session.user)) & set(roles))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/radar/settings"
		raise frappe.Redirect

	context.no_cache = 1
	context.no_header = 1
	context.no_footer = 1
	context.title = "Configuración · Radar"
	context.no_access = not _has_role(VIEW_ROLES)
	context.required_roles = list(VIEW_ROLES)
	context.can_edit = _has_role(ADMIN_ROLES)
	if context.no_access:
		return

	s = frappe.get_cached_doc("Radar Settings")

	# precio por item ya calibrado con lo que Apify cobró de verdad
	estimacion = estimar_corrida()
	datos = obtener_settings(estimacion["por_marca"])
	precio = estimacion["precio"]

	context.ig = datos["posts_por_perfil_ig"]
	context.tt = datos["posts_por_perfil_tiktok"]
	context.techo = datos["max_posts_marca"]
	context.incremental = datos["modo_incremental"]
	context.horas = datos["horas_entre_corridas"]
	# IG y TikTok devuelven hasta 3 anclados que el scraper descarta: con un techo
	# así de bajo se puede pagar la corrida entera y no guardar ni un post
	context.techo_justo = bool(context.techo and context.techo <= 3)

	# Límite por marca: una fila por competidor con cuentas activas
	context.marcas = datos["marcas"]
	context.marcas_json = frappe.as_json(datos["marcas"]).replace("</", "<\\/")
	context.coste_ig = f"{precio['Instagram']:.4f}"
	context.coste_tt = f"{precio['TikTok']:.4f}"
	# el JS recalcula el estimado mientras editas: con el precio redondeado a 4
	# decimales le salía un total distinto al del server en la misma pantalla
	context.coste_ig_js = repr(precio["Instagram"])
	context.coste_tt_js = repr(precio["TikTok"])
	context.coste_total = f"{estimacion['total']:.3f}"
	context.calibrado = precio["corridas"] and abs(precio["factor"] - 1) > 0.001
	context.calibracion = {
		"factor": f"{precio['factor']:.2f}",
		"corridas": precio["corridas"],
		"sube": precio["factor"] > 1,
	}

	# Control de gasto: cada corrida, el acumulado y el presupuesto del ciclo
	gasto = resumen_gasto()
	propias = gasto["propias"]
	context.gasto = {
		"ultima": f"{gasto['ultima_usd']:.3f}",
		"mes": f"{gasto['mes_usd']:.2f}",
		"mes_corridas": gasto["mes_corridas"],
		"total": f"{gasto['total_usd']:.2f}",
		"total_corridas": gasto["total_corridas"],
		# el promedio solo cuenta las corridas del panel: las importadas del
		# histórico de Apify no traen items y ensucian la media
		"promedio": f"{propias['promedio']:.3f}",
		"propias_n": propias["corridas"],
		"importadas_n": gasto["total_corridas"] - propias["corridas"],
		"importadas_usd": f"{gasto['total_usd'] - propias['usd']:.2f}",
	}

	p = gasto["presupuesto"]
	context.presupuesto = {
		"tope": _num(p["tope"]),
		"hay_tope": bool(p["tope"]),
		"techo": f"{p['techo']:.2f}" if p["techo"] else "",
		"limite_apify": f"{p['limite_apify']:.0f}" if p["limite_apify"] else "",
		"gastado": f"{p['gastado']:.2f}",
		"restante": f"{p['restante']:.2f}" if p["restante"] is not None else "",
		"restante_num": p["restante"] if p["restante"] is not None else 0,
		"pct": p["pct"],
		"agotado": p["agotado"],
		"renueva": _fecha_corta(p.get("renueva")),
		"dias_a_renovar": p["dias_a_renovar"],
		"ritmo": f"{p['ritmo_dia']:.2f}",
		"hay_ritmo": p["ritmo_dia"] > 0,
		"ritmo_fiable": p["ritmo_fiable"],
		"dias_ciclo": p["dias_ciclo"],
		"agotamiento": frappe.utils.formatdate(p["agotamiento"], "dd/MM") if p["agotamiento"] else "",
		"dias_restantes": p["dias_restantes"],
		"llega": p["llega"],
		"corridas_media": p["corridas_media"],
		"corridas_completas": p["corridas_completas"],
		"media_corrida": f"{p['media_corrida']:.3f}",
	}

	# conteo de lo scrapeado por red social.
	# las claves NO pueden llamarse "items": en Jinja `r.items` resuelve el método
	# del dict en vez del valor (ya pasó con `corrida.update` y con `c.items`)
	context.redes = [
		{
			"nombre": red,
			"corto": "IG" if red == "Instagram" else "TT",
			"unidad": "posts" if red == "Instagram" else "videos",
			"cantidad": (gasto["por_red"].get(red) or {}).get("items", 0),
			"cantidad_mes": (gasto["por_red"].get(red) or {}).get("items_mes", 0),
			"coste": f"{(gasto['por_red'].get(red) or {}).get('total', 0):.3f}",
		}
		for red in ("Instagram", "TikTok")
	]

	context.corridas = []
	for c in gasto["ultimas"]:
		# las corridas reconstruidas desde Apify no tienen conteo de items; ojo,
		# no vale mirar items==0 porque una corrida fallida también trae cero
		historica = c["disparada_por"] == IMPORTADA
		context.corridas.append({
			"cuando": frappe.utils.format_datetime(c["fecha_inicio"], "dd/MM HH:mm"),
			"coste": f"{float(c['coste_usd'] or 0):.3f}",
			"real": int(c["coste_real"] or 0),
			# ojo: la clave NO puede llamarse "items" — en Jinja `c.items` resuelve
			# el método del dict, no el valor (mismo caso que `corrida.update`)
			"n_items": "—" if historica else c["items_total"],
			"meta": "histórico Apify" if historica
			        else f"{c['alcance'] or 'Todas'} · {c['insertados']} nuevas",
			"estado": c["estado"] or "",
		})

	stats = {}
	if s.ultima_corrida_stats:
		try:
			stats = json.loads(s.ultima_corrida_stats)
		except Exception:
			stats = {}
	# ojo: no usar "update"/"insert" como claves — en Jinja `corrida.update`
	# resuelve el método del dict, no el valor
	context.corrida = {
		"cuando": frappe.utils.format_datetime(s.ultima_corrida, "dd/MM HH:mm") if s.ultima_corrida else "—",
		"estado": {"ok": "Correcta", "warn": "Con avisos", "error": "Con errores",
		           "cancelada": "Detenida"}.get(s.ultima_corrida_estado or "", "Sin datos"),
		"insertados": int(stats.get("insert") or 0),
		"actualizados": int(stats.get("update") or 0),
		"saltados": int(stats.get("skip") or 0),
		"errores": int(stats.get("error") or 0),
		"duracion": f"{float(s.ultima_corrida_duracion or 0):.0f} s",
		"mensaje": s.ultima_corrida_mensaje or "Sin registro de la última corrida.",
	}
	# ---- Estado del token de Apify (puntos 1, 2, 5) ----
	# Guardamos solo los últimos 4 chars para que la UI muestre "•••••7ZvXhR4oLfIS"
	# sin exponer el token entero. Si no hay token, el input queda vacío.
	token = get_decrypted_password("Radar Settings", "Radar Settings", "apify_token", raise_exception=False) or ""
	context.token_hay = bool(token)
	context.token_tail = token[-4:] if len(token) >= 4 else ""
	# Healthcheck: si hay token, preguntamos a Apify si sigue vivo. `credito_apify`
	# cachea 10 min y llama a /users/me/limits: si devuelve None es que el token
	# esta roto o Apify no responde.
	credito = None
	if token:
		try:
			credito = credito_apify()
		except Exception:
			credito = None
	context.token_invalido = bool(token) and credito is None
	if credito:
		usado = float(credito.get("usado") or 0)
		limite = float(credito.get("limite") or 0)
		restante = float(credito.get("restante") or 0)
		pct = round(usado / limite * 100, 1) if limite else 0
		context.credito_apify = {
			"usado": f"{usado:.3f}",
			"limite": f"{limite:.2f}",
			"restante": f"{restante:.3f}",
			"pct": pct,
			"agotado": limite > 0 and restante <= 0,
			"casi_agotado": pct >= 80 and not (limite > 0 and restante <= 0),
			"renueva": _fecha_corta(credito.get("renueva")),
		}
	else:
		context.credito_apify = None

	try:
		context.csrf_token = frappe.local.session.data.csrf_token
	except Exception:
		context.csrf_token = ""


VACIAS = {"de", "del", "la", "el", "y", "en"}


def _iniciales(nombre):
	partes = [p for p in (nombre or "").split() if p.lower() not in VACIAS]
	if not partes:
		return "··"
	if len(partes) == 1:
		return partes[0][:2]
	return partes[0][:1] + partes[1][:1]


def _num(valor):
	"""0.5 -> '0.5' · 3.0 -> '3' (los topes se editan como texto)."""
	try:
		f = float(valor or 0)
	except (TypeError, ValueError):
		return "0"
	return str(int(f)) if f == int(f) else str(round(f, 3))


def _fecha_corta(iso):
	"""'2026-09-01T00:00:00.000Z' -> '01/09'."""
	if not iso or len(iso) < 10:
		return ""
	return f"{iso[8:10]}/{iso[5:7]}"


def _ultima_por_marca():
	"""Fecha y hora de la última corrida en la que entró cada marca."""
	filas = frappe.db.sql("""
		SELECT m.marca AS marca, MAX(c.fecha_inicio) AS ultima
		FROM `tabRadar Corrida Marca` m
		JOIN `tabRadar Corrida` c ON c.name = m.parent
		GROUP BY m.marca
	""", as_dict=True)
	return {f["marca"]: f["ultima"] for f in filas if f["ultima"]}


def _roi_por_marca(dias=30):
	"""ROI = posts nuevos insertados / USD gastado, últimos N días.

	Sale de `tabRadar Corrida Marca` (una fila por marca por corrida):
	agrega insertados y coste_usd solo de corridas dentro del rango. Marcas
	sin gasto en el periodo salen con roi=None (no las divido por cero)."""
	desde = frappe.utils.add_days(frappe.utils.nowdate(), -int(dias))
	filas = frappe.db.sql("""
		SELECT m.marca AS marca,
		       COALESCE(SUM(m.insertados), 0) AS nuevos,
		       COALESCE(SUM(m.coste_usd), 0)  AS gastado
		FROM `tabRadar Corrida Marca` m
		JOIN `tabRadar Corrida` c ON c.name = m.parent
		WHERE c.fecha_inicio >= %s AND m.marca IS NOT NULL
		GROUP BY m.marca
	""", (desde,), as_dict=True)
	out = {}
	for f in filas:
		nuevos = int(f["nuevos"] or 0)
		gastado = float(f["gastado"] or 0)
		out[f["marca"]] = {
			"nuevos": nuevos,
			"gastado": gastado,
			# posts/USD: cuanto mayor mejor. Si gastado=0 (marca sin corridas),
			# no calculamos: 0/0 no es informativo. Si nuevos=0 pero gastado>0
			# el ROI es 0 (marca "cara" que no da nada).
			"roi": round(nuevos / gastado, 2) if gastado > 0 else None,
		}
	return out


def _marcas_con_cuentas(estimados=None):
	"""Competidores que tienen al menos una cuenta activa, con su límite propio.

	`estimados` = {marca: usd} de estimar_corrida(), para no recalcularlo aquí."""
	cuentas = frappe.db.get_all(
		"Cuenta Social",
		filters={"activo": 1, "plataforma": ["in", ("Instagram", "TikTok")]},
		fields=["competidor", "plataforma"],
	)
	if not cuentas:
		return []
	por_marca = {}
	for c in cuentas:
		m = por_marca.setdefault(c["competidor"], {"ig": 0, "tt": 0})
		m["ig" if c["plataforma"] == "Instagram" else "tt"] += 1

	ajustes = {
		c["name"]: c for c in frappe.db.get_all(
			"Competidor",
			filters={"name": ["in", list(por_marca)]},
			fields=["name", "limite_posts", "pausar_radar"],
		)
	}
	ultimas = _ultima_por_marca()
	rois = _roi_por_marca(30)
	estimados = estimados or {}
	ahora = frappe.utils.now_datetime()

	marcas = []
	for nombre, redes in por_marca.items():
		redes_txt = " · ".join(
			t for t in (
				f"{redes['ig']} IG" if redes["ig"] else "",
				f"{redes['tt']} TikTok" if redes["tt"] else "",
			) if t
		)
		ultima = ultimas.get(nombre)
		# aviso si se scrapeó hace poco: repetir el mismo día vuelve a pagar los
		# mismos posts, que es donde se fue el dinero el 15/08
		horas = ((ahora - ultima).total_seconds() / 3600) if ultima else None
		roi = rois.get(nombre) or {}
		roi_val = roi.get("roi")
		# etiquetas legibles para la UI: `roi` bruto es number/None; damos texto
		# corto y una clase (mala=<3, ok=3-8, buena=>8 posts/USD). Los umbrales
		# son heurísticos: se pueden calibrar cuando haya más historial.
		if roi_val is None:
			roi_txt = "—"
			roi_cls = "n/a"
		elif roi_val >= 8:
			roi_txt = f"{roi_val:.1f}"
			roi_cls = "buena"
		elif roi_val >= 3:
			roi_txt = f"{roi_val:.1f}"
			roi_cls = "ok"
		else:
			roi_txt = f"{roi_val:.1f}"
			roi_cls = "mala"
		marcas.append({
			"nombre": nombre,
			"ini": _iniciales(nombre),
			"limite": int((ajustes.get(nombre) or {}).get("limite_posts") or 0),
			"pausada": int((ajustes.get(nombre) or {}).get("pausar_radar") or 0),
			"ig": redes["ig"],
			"tt": redes["tt"],
			"redes": redes_txt,
			"ultima": frappe.utils.format_datetime(ultima, "dd/MM/yy HH:mm") if ultima else "",
			"reciente": bool(horas is not None and horas < 24),
			"estimado": f"{estimados.get(nombre, 0):.3f}",
			"roi_txt": roi_txt,
			"roi_cls": roi_cls,
			"roi_nuevos": int(roi.get("nuevos") or 0),
			"roi_gastado": f"{float(roi.get('gastado') or 0):.2f}",
		})
	marcas.sort(key=lambda m: m["nombre"].lower())
	return marcas


@frappe.whitelist()
def obtener_settings(estimados=None):
	"""Valores actuales de Radar Settings que pinta la página."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	s = frappe.get_doc("Radar Settings")
	return {
		"posts_por_perfil_ig": s.posts_por_perfil_ig or 20,
		"posts_por_perfil_tiktok": s.posts_por_perfil_tiktok or 20,
		"max_posts_marca": int(s.get("max_posts_marca") or 0),
		"modo_incremental": int(s.get("modo_incremental") or 0),
		"horas_entre_corridas": int(s.get("horas_entre_corridas") or 0),
		"tope_ciclo_usd": float(s.get("tope_ciclo_usd") or 0),
		"marcas": _marcas_con_cuentas(estimados),
	}


@frappe.whitelist()
def guardar_settings(
	posts_por_perfil_ig=None,
	posts_por_perfil_tiktok=None,
	max_posts_marca=None,
	modo_incremental=None,
	horas_entre_corridas=None,
	tope_ciclo_usd=None,
	limites_marca=None,
	pausas_marca=None,
):
	"""Guarda los valores de Radar Settings.

	limites_marca = JSON string {competidor: posts_por_corrida}; 0 = usar el
	default global. Se guarda en Competidor.limite_posts, no en Radar Settings."""
	import json as _json
	if not _has_role(ADMIN_ROLES):
		frappe.throw(
			"Solo un administrador puede modificar la configuración.",
			frappe.PermissionError,
		)
	s = frappe.get_single("Radar Settings")
	if max_posts_marca is not None:          s.max_posts_marca = max(0, int(max_posts_marca or 0))
	if modo_incremental is not None:         s.modo_incremental = 1 if int(modo_incremental or 0) else 0
	if horas_entre_corridas is not None:     s.horas_entre_corridas = max(0, int(horas_entre_corridas or 0))
	if posts_por_perfil_ig is not None:      s.posts_por_perfil_ig = int(posts_por_perfil_ig)
	if posts_por_perfil_tiktok is not None:  s.posts_por_perfil_tiktok = int(posts_por_perfil_tiktok)
	if tope_ciclo_usd is not None:           s.tope_ciclo_usd = _usd(tope_ciclo_usd, "tope por ciclo")

	# el techo recorta también los defaults: si no, la marca sin límite propio
	# pediría más que el máximo por la puerta de atrás
	techo = int(s.max_posts_marca or 0)
	if techo:
		s.posts_por_perfil_ig = min(int(s.posts_por_perfil_ig or 0), techo)
		s.posts_por_perfil_tiktok = min(int(s.posts_por_perfil_tiktok or 0), techo)

	s.save(ignore_permissions=True)

	if limites_marca is not None:
		try:
			mapa = _json.loads(limites_marca) if isinstance(limites_marca, str) else limites_marca
		except Exception:
			frappe.throw("Los límites por marca deben ser un JSON válido.")
		for marca, limite in (mapa or {}).items():
			try:
				valor = max(0, int(limite or 0))
			except (TypeError, ValueError):
				frappe.throw(f"El límite de «{marca}» debe ser un número entero.")
			if techo and valor > techo:
				frappe.throw(
					f"«{marca}» pide {valor} posts y el máximo por marca es {techo}. "
					f"Sube el máximo si de verdad quieres pedir más."
				)
			if not frappe.db.exists("Competidor", marca):
				continue
			if frappe.db.get_value("Competidor", marca, "limite_posts") != valor:
				frappe.db.set_value("Competidor", marca, "limite_posts", valor)

	if pausas_marca is not None:
		try:
			mapa = _json.loads(pausas_marca) if isinstance(pausas_marca, str) else pausas_marca
		except Exception:
			frappe.throw("Las pausas por marca deben ser un JSON válido.")
		for marca, pausada in (mapa or {}).items():
			if not frappe.db.exists("Competidor", marca):
				continue
			valor = 1 if pausada else 0
			if int(frappe.db.get_value("Competidor", marca, "pausar_radar") or 0) != valor:
				frappe.db.set_value("Competidor", marca, "pausar_radar", valor)

	frappe.db.commit()
	return {"ok": True}


def _usd(valor, etiqueta):
	"""'0.5' -> 0.5 · '' -> 0. Un tope mal tecleado no puede quedar en None."""
	txt = str(valor).strip().replace("$", "").replace(",", ".")
	if not txt:
		return 0.0
	try:
		monto = float(txt)
	except ValueError:
		frappe.throw(f"El {etiqueta} debe ser un número (ej.: 0.5).")
	if monto < 0:
		frappe.throw(f"El {etiqueta} no puede ser negativo.")
	return round(monto, 4)


# ============ Gestión del Apify token (puntos 1, 2, 3) ============

def _probar_token(token):
	"""Preguntamos a /users/me con el token: si no vuelve 200 el token es basura.

	Devuelve dict con {ok, usuario, plan, mensaje}. Usamos urllib directo y no
	el helper `apify_actor.credito()` porque queremos poder distinguir 'sin
	internet' de 'token muerto' (credito devuelve None en ambos)."""
	import urllib.request
	import urllib.error
	if not token:
		return {"ok": False, "mensaje": "Token vacío."}
	try:
		req = urllib.request.Request(
			"https://api.apify.com/v2/users/me",
			headers={"Authorization": f"Bearer {token}"},
		)
		with urllib.request.urlopen(req, timeout=10) as r:
			data = json.loads(r.read().decode("utf-8"))["data"]
			return {
				"ok": True,
				"usuario": data.get("username") or data.get("email") or "?",
				"plan": (data.get("plan") or {}).get("id") or "?",
				"mensaje": "",
			}
	except urllib.error.HTTPError as e:
		if e.code in (401, 403):
			return {"ok": False, "mensaje": "Apify rechazó el token (401/403). Verifica que sea válido y esté activo."}
		return {"ok": False, "mensaje": f"Apify respondió HTTP {e.code}. Reintenta en unos minutos."}
	except Exception as e:
		return {"ok": False, "mensaje": f"No pude contactar Apify: {e}. Revisa la conexión."}


@frappe.whitelist()
def guardar_token(token=None):
	"""Actualiza `Radar Settings.apify_token` tras validarlo contra la API.

	El campo es Password (encriptado en tabPasswords). Si el token es basura
	no lo guardamos: preferimos rechazar antes que dejar el cron mudo por
	semanas. Un string vacío borra el token y desactiva el scraper."""
	if not _has_role(ADMIN_ROLES):
		frappe.throw("Solo un administrador puede cambiar el token.", frappe.PermissionError)
	token = (token or "").strip()
	if not token:
		# borrar el token: no lo probamos contra Apify, solo lo limpiamos.
		s = frappe.get_single("Radar Settings")
		s.apify_token = ""
		s.save(ignore_permissions=True)
		# invalidamos el cache de crédito porque cambia el token
		frappe.cache().delete_value("radar_apify_credito")
		frappe.db.commit()
		return {"ok": True, "borrado": True}
	prueba = _probar_token(token)
	if not prueba["ok"]:
		frappe.throw(prueba["mensaje"])
	s = frappe.get_single("Radar Settings")
	s.apify_token = token
	s.save(ignore_permissions=True)
	frappe.cache().delete_value("radar_apify_credito")
	frappe.db.commit()
	return {"ok": True, "usuario": prueba["usuario"], "plan": prueba["plan"]}


@frappe.whitelist()
def test_token(token=None):
	"""Prueba un token contra Apify SIN guardarlo. Sirve para el botón 'Probar'.

	Si no se pasa token, prueba el que hay guardado en Radar Settings."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	token = (token or "").strip()
	if not token:
		token = get_decrypted_password(
			"Radar Settings", "Radar Settings", "apify_token", raise_exception=False
		) or ""
	return _probar_token(token)
