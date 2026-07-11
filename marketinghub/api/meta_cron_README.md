# Sincronizacion Meta desde n8n

## Endpoint

`POST https://<sitio>/api/method/ventahub.api.meta_cron.sync_meta`

**Autenticacion:** parametro `secret` (form-urlencoded o query).
El secret vive en `site_config.json` como `ventahub_cron_secret`. Puede
ser el mismo para todos los sitios (via `common_site_config.json`) o
distinto por sitio.

**Ejemplo curl:**
```bash
curl -X POST "https://ginbak.tiranidos.com/api/method/ventahub.api.meta_cron.sync_meta" \
     -d "secret=<VENTAHUB_CRON_SECRET>"
```

## Respuestas

| HTTP | Payload | Cuando |
|---|---|---|
| 200 | `{"ok":true, "stats":{"creadas":X,"actualizadas":Y,"omitidas":Z,"errores":[]}}` | Sync ejecutado |
| 200 | `{"ok":true, "skipped":true, "reason":"..."}` | `Configuracion Meta.habilitado = 0` (no es error) |
| 400 | `{"ok":false, "error":"...ad_account_id vacio"}` | Falta config |
| 401 | `{"ok":false, "error":"Falta secret"}` | Header/body sin secret |
| 403 | `{"ok":false, "error":"Secret invalido"}` | Secret no coincide |
| 500 | `{"ok":false, "error":"..."}` | Excepcion del sync o secret no configurado en site_config |

## Endpoint auxiliar: healthcheck

`POST /api/method/ventahub.api.meta_cron.ping` con el mismo `secret`.

Devuelve `{ok, site, meta_habilitado, meta_ad_account_id_configurado}`
sin correr el sync. Util para monitoreo continuo desde n8n.

## Setup n8n para multi-sitio

### 1. Guardar el secret como credencial

En n8n → **Credentials → Header Auth** (o **Custom**):
- Nombre: `Ventahub Cron Secret`
- Valor: el `ventahub_cron_secret` (mismo en los 3 sitios).

### 2. Workflow "Meta Sync — Tiranidos"

**Trigger:** Cron / Schedule Trigger (ej. cada 1 hora, o diario).

**Nodo HTTP Request por cada sitio** (3 nodos en paralelo):
- Method: `POST`
- URL: `https://<sitio>/api/method/ventahub.api.meta_cron.sync_meta`
- Body Parameters: `secret = {{ $env.VENTAHUB_CRON_SECRET }}` (o de la credencial)
- **Options → Response → Continue On Fail: ✅ SÍ**
  (Sin esto, un sitio que falle detiene los demás.)

**Nodo IF (por cada sitio):**
- Condition: `{{ $json.message.ok }} === true`
  - Rama TRUE: continuar (o loguear success).
  - Rama FALSE: enviar notificacion (Slack, email, Telegram, etc.) con:
    - `sitio: {{ $json.message.site }}`
    - `error: {{ $json.message.error }}`
    - `stats: {{ JSON.stringify($json.message.stats) }}`

### 3. Frecuencia recomendada

- **Diario a las 2 AM** (recomendado): Meta actualiza sus stats cada
  cierto tiempo, no tiene sentido sincronizar mas seguido.
- **Cada 1 hora**: si te interesa ver stats mas frescas en `/meta_ads` y
  `/anuncios` durante el dia. El endpoint es idempotente.

## Estado actual (2026-07-10)

| Sitio | Secret en site_config | Meta habilitado | ad_account_id |
|---|---|---|---|
| erp.tiranidos.com | ✅ (via common_site_config) | ❌ | ❌ |
| barra.tiranidos.com | ✅ | ❌ | ❌ |
| ginbak.tiranidos.com | ✅ | ✅ | ✅ `1045763096651571` |

Los sitios con `habilitado=0` devuelven `skipped:true` (n8n no los
notifica como error). Cuando el admin de cada sitio active
`Configuracion Meta.habilitado`, el cron empieza a correr para ese
sitio automaticamente.

## Prueba end-to-end

```bash
# Ping (sin correr sync)
curl -X POST "https://ginbak.tiranidos.com/api/method/ventahub.api.meta_cron.ping" \
     -d "secret=<VENTAHUB_CRON_SECRET>"

# Sync completo (habilitar Meta primero en /integraciones/meta)
curl -X POST "https://ginbak.tiranidos.com/api/method/ventahub.api.meta_cron.sync_meta" \
     -d "secret=<VENTAHUB_CRON_SECRET>"
```
