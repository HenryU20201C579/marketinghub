"""Página de configuración del Radar.

El frontend es el diseño del zip: `index.html` es un documento standalone (no
extiende `templates/web.html`) y `configuracion.css` es copia literal del CSS
del diseño. `get_context` solo lee lo que pinta ese markup; el guardado sigue
pasando por `guardar_settings`, sin cambios.
"""
import json
from datetime import date, timedelta

import frappe

# el precio por item está calibrado con runs reales; vive en el scraper para no duplicarlo
from marketinghub.api.radar_scraper import COSTE_ITEM, resumen_gasto
from marketinghub.marketinghub.doctype.radar_settings.radar_settings import PRESET_MANUAL

no_cache = 1

CANALES = (
	# valor real del doctype, etiqueta del diseño, icono
	("In-app ERP", "Campanita ERP", "campana"),
	("Email", "Correo", "correo"),
	("Telegram", "Telegram", "chat"),
	("WhatsApp", "WhatsApp", "chat"),
)
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
	datos = obtener_settings()

	tiers = datos["tiers"]
	for t in tiers:
		t["ini"] = _iniciales(t["nombre"])
		t["eng"] = _num(t["engagement_min"])
		t["vistas"] = _num(t["vistas_min"])
	context.tiers = tiers
	context.tiers_json = frappe.as_json(tiers).replace("</", "<\\/")
	context.n_virales = sum(1 for t in tiers if t["es_viral"])

	context.retencion = datos["dias_retencion_snapshots"]
	context.ig = datos["posts_por_perfil_ig"]
	context.tt = datos["posts_por_perfil_tiktok"]
	context.cron = datos["cron_scrape"]
	context.preset = datos["preset_frecuencia"]
	context.presets = _opciones("preset_frecuencia")
	context.canal = datos["canal_alerta"]
	context.canales = [
		{"valor": v, "label": etiqueta, "icono": icono, "on": v == datos["canal_alerta"]}
		for v, etiqueta, icono in CANALES
	]

	context.es_manual = datos["preset_frecuencia"] == PRESET_MANUAL
	context.proxima = (
		"Solo manual" if context.es_manual else _proxima_corrida(datos["cron_scrape"])
	)
	corte = date.today() - timedelta(days=int(datos["dias_retencion_snapshots"] or 90))
	context.corte_retencion = corte.strftime("%d/%m/%y")

	# Límite por marca: una fila por competidor con cuentas activas
	context.marcas = datos["marcas"]
	context.marcas_json = frappe.as_json(datos["marcas"]).replace("</", "<\\/")
	context.coste_ig = f"{COSTE_ITEM['Instagram']:.4f}"
	context.coste_tt = f"{COSTE_ITEM['TikTok']:.4f}"
	context.coste_total = f"{_coste_corrida(datos):.3f}"

	# Control de gasto: cada corrida y el acumulado
	gasto = resumen_gasto()
	context.gasto = {
		"ultima": f"{gasto['ultima_usd']:.3f}",
		"mes": f"{gasto['mes_usd']:.2f}",
		"mes_corridas": gasto["mes_corridas"],
		"total": f"{gasto['total_usd']:.2f}",
		"total_corridas": gasto["total_corridas"],
		"promedio": f"{(gasto['total_usd'] / gasto['total_corridas']):.3f}" if gasto["total_corridas"] else "0.000",
	}
	context.corridas = []
	for c in gasto["ultimas"]:
		# las corridas reconstruidas desde Apify no tienen conteo de items
		historica = not c["items_total"] and not c["insertados"]
		context.corridas.append({
			"cuando": frappe.utils.format_datetime(c["fecha_inicio"], "dd/MM HH:mm"),
			"coste": f"{float(c['coste_usd'] or 0):.3f}",
			"real": int(c["coste_real"] or 0),
			# ojo: la clave NO puede llamarse "items" — en Jinja `c.items` resuelve
			# el método del dict, no el valor (mismo caso que `corrida.update`)
			"n_items": "—" if historica else c["items_total"],
			"meta": "histórico Apify" if historica
			        else f"{c['origen']} · {c['insertados']} nuevas",
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
		"estado": {"ok": "Correcta", "warn": "Con avisos", "error": "Con errores"}.get(
			s.ultima_corrida_estado or "", "Sin datos"),
		"insertados": int(stats.get("insert") or 0),
		"actualizados": int(stats.get("update") or 0),
		"saltados": int(stats.get("skip") or 0),
		"errores": int(stats.get("error") or 0),
		"duracion": f"{float(s.ultima_corrida_duracion or 0):.0f} s",
		"mensaje": s.ultima_corrida_mensaje or "Sin registro de la última corrida.",
	}
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
	"""3.5 -> '3.5' · 3.0 -> '3' (los umbrales se editan como texto)."""
	try:
		f = float(valor or 0)
	except (TypeError, ValueError):
		return "0"
	return str(int(f)) if f == int(f) else str(f)


def _opciones(fieldname):
	campo = frappe.get_meta("Radar Settings").get_field(fieldname)
	return [o for o in (campo.options or "").split("\n") if o.strip()]


def _marcas_con_cuentas():
	"""Competidores que tienen al menos una cuenta activa, con su límite propio."""
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

	limites = dict(frappe.db.get_all(
		"Competidor",
		filters={"name": ["in", list(por_marca)]},
		fields=["name", "limite_posts"],
		as_list=True,
	))
	# lo que costó cada marca: en la última corrida y acumulado
	gasto = resumen_gasto()
	acumulado = {g["marca"]: float(g["total"] or 0) for g in gasto["por_marca"]}
	ultima = gasto["ultima_por_marca"]

	marcas = []
	for nombre, redes in por_marca.items():
		redes_txt = " · ".join(
			t for t in (
				f"{redes['ig']} IG" if redes["ig"] else "",
				f"{redes['tt']} TikTok" if redes["tt"] else "",
			) if t
		)
		marcas.append({
			"nombre": nombre,
			"ini": _iniciales(nombre),
			"limite": int(limites.get(nombre) or 0),
			"ig": redes["ig"],
			"tt": redes["tt"],
			"redes": redes_txt,
			"gasto_ultima": f"{ultima.get(nombre, {}).get('coste', 0):.3f}",
			"gasto_total": f"{acumulado.get(nombre, 0):.3f}",
			"scrapeada": nombre in ultima,
		})
	marcas.sort(key=lambda m: m["nombre"].lower())
	return marcas


def _coste_corrida(datos):
	"""Coste estimado en Apify: suma perfil por perfil, con el límite que le toca."""
	total = 0.0
	for m in datos["marcas"]:
		lim = m["limite"] or 0
		lim_ig = lim or (datos["posts_por_perfil_ig"] or 0)
		lim_tt = lim or (datos["posts_por_perfil_tiktok"] or 0)
		total += m["ig"] * lim_ig * COSTE_ITEM["Instagram"]
		total += m["tt"] * lim_tt * COSTE_ITEM["TikTok"]
	return total


def _proxima_corrida(cron):
	try:
		from croniter import croniter

		from frappe.utils import now_datetime
		siguiente = croniter(cron, now_datetime()).get_next(type(now_datetime()))
		hoy = date.today()
		dia = {0: "hoy", 1: "mañana"}.get((siguiente.date() - hoy).days)
		if dia:
			return f"Próxima: {dia} {siguiente.strftime('%H:%M')}"
		return f"Próxima: {siguiente.strftime('%d/%m %H:%M')}"
	except Exception:
		return f"Cron: {cron}"


@frappe.whitelist()
def obtener_settings():
	"""Retorna los valores actuales de Radar Settings + tabla de tiers."""
	if not _has_role(VIEW_ROLES):
		frappe.throw("Acceso denegado", frappe.PermissionError)
	s = frappe.get_doc("Radar Settings")
	tiers = []
	for t in sorted(s.tiers_viralidad or [], key=lambda x: x.orden):
		tiers.append({
			"orden": t.orden,
			"nombre": t.nombre,
			"imagen_url": t.imagen_url,
			"vistas_min": t.vistas_min,
			"engagement_min": t.engagement_min,
			"es_viral": int(t.es_viral or 0),
			"color_hex": t.color_hex,
		})
	return {
		"dias_retencion_snapshots": s.dias_retencion_snapshots or 90,
		"canal_alerta": s.canal_alerta or "In-app ERP",
		"preset_frecuencia": s.preset_frecuencia or "Diario a las 6 AM",
		"cron_scrape": s.cron_scrape or "0 6 * * *",
		"posts_por_perfil_ig": s.posts_por_perfil_ig or 20,
		"posts_por_perfil_tiktok": s.posts_por_perfil_tiktok or 20,
		"tiers": tiers,
		"marcas": _marcas_con_cuentas(),
	}


@frappe.whitelist()
def guardar_settings(
	dias_retencion_snapshots=None,
	canal_alerta=None,
	preset_frecuencia=None,
	cron_scrape=None,
	posts_por_perfil_ig=None,
	posts_por_perfil_tiktok=None,
	tiers=None,
	limites_marca=None,
):
	"""Guarda los valores de Radar Settings. tiers = JSON string con la tabla.

	limites_marca = JSON string {competidor: posts_por_corrida}; 0 = usar el default
	global. Se guarda en Competidor.limite_posts, no en Radar Settings."""
	import json as _json
	if not _has_role(ADMIN_ROLES):
		frappe.throw(
			"Solo un administrador puede modificar la configuración.",
			frappe.PermissionError,
		)
	s = frappe.get_single("Radar Settings")
	if dias_retencion_snapshots is not None: s.dias_retencion_snapshots = int(dias_retencion_snapshots)
	if canal_alerta is not None:          s.canal_alerta = canal_alerta
	if preset_frecuencia is not None:     s.preset_frecuencia = preset_frecuencia
	if cron_scrape is not None:           s.cron_scrape = cron_scrape.strip()
	if posts_por_perfil_ig is not None:   s.posts_por_perfil_ig = int(posts_por_perfil_ig)
	if posts_por_perfil_tiktok is not None: s.posts_por_perfil_tiktok = int(posts_por_perfil_tiktok)

	if tiers is not None:
		try:
			tiers_data = _json.loads(tiers) if isinstance(tiers, str) else tiers
		except Exception:
			frappe.throw("Los tiers deben ser un JSON válido.")
		s.tiers_viralidad = []
		for t in tiers_data:
			s.append("tiers_viralidad", {
				"orden": int(t.get("orden") or 0),
				"nombre": t.get("nombre") or "",
				"imagen_url": t.get("imagen_url") or "",
				"vistas_min": int(t.get("vistas_min") or 0),
				"engagement_min": float(t.get("engagement_min") or 0),
				"es_viral": 1 if t.get("es_viral") else 0,
				"color_hex": t.get("color_hex") or "#94a3b8",
			})

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
			if not frappe.db.exists("Competidor", marca):
				continue
			if frappe.db.get_value("Competidor", marca, "limite_posts") != valor:
				frappe.db.set_value("Competidor", marca, "limite_posts", valor)

	frappe.db.commit()
	return {"ok": True}
