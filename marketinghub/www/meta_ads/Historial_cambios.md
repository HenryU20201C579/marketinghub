# Historial de cambios — www/meta_ads

## 2026-04-16 20:20 — Refactor roles sintaxis `L-<Modulo>-<Funcion>` con split Ver/Administrar

**Tipo**: refactor

**Descripcion**:
Primera entrada. Migracion del dashboard "Marketing Intelligence"
(meta_ads) del rol legacy `L-Web Meta` al estandar:
- `L-MetaAds-Ver`: acceso al dashboard + todos los endpoints de lectura
  (`get_meta_token`, `get_ad_accounts`, `get_leads_por_anuncio_meta`,
  `get_lead_counts_por_etiquetas`, `get_filtered_lead_counts`,
  `get_sales_data_por_etiquetas`, `get_all_lead_etiquetas`,
  `get_row_detail`, `get_page_posts`, `get_conversation`).
- `L-MetaAds-Administrar`: ademas ejecuta `sincronizar_campanas`
  (crea/actualiza Campana Meta / Conjunto Anuncios / Anuncio desde
  Meta API).

Los helpers + tuplas viven en `lizaraso/api/meta_ads.py` (canonical
entry point para los endpoints). `lizaraso/www/meta_ads/index.py`
importa para `get_context`.

**Archivos modificados**:
- `../../api/meta_ads.py` — constantes `ADMIN_ROLES` / `VIEW_ROLES`,
  helpers `_is_admin`, `_can_view`, `_require_view`, `_require_admin`.
  10 endpoints gateados como view; `sincronizar_campanas` como admin.
- `index.py` — import de helpers. `get_context` expone `no_access`,
  `required_roles` y `can_edit` (reemplaza el `frappe.throw`
  directo).
- `index.html` — overlay canonico `ma-na-*`. Bloque
  `{% if no_access %}...{% else %}...{% endif %}` alrededor del
  contenido. `window.MA_CAN_EDIT` inyectado. Boton "Guardar y
  Sincronizar" del modal editar-campaña envuelto en
  `{% if can_edit %}`; boton "Cancelar" cambia a "Cerrar" para
  viewer.
- `../panel_ventas/index.py` — `context.has_meta_ads_role` ahora
  acepta legacy (`L-Web Meta`) + nuevos (`L-MetaAds-Ver`,
  `L-MetaAds-Administrar`) para no romper el sidebar durante la
  transicion.

**Cambio relacionado en**:
- `../campanas_meta/Historial_cambios.md`

**Notas**:
- **Fix seguridad importante**: `get_meta_token` retorna el token
  crudo de Meta Ads API, que antes era accesible a cualquier user
  autenticado con `L-Web Meta`. Ahora exige `L-MetaAds-Ver` — el
  token sigue expuesto al frontend pero solo a users con rol
  explicito (no a cualquiera con cuenta). Mejora futura: mover
  las llamadas a Meta API al backend para no exponer el token.
- **Pasos Desk**: crear `L-MetaAds-Ver` y `L-MetaAds-Administrar`.
  Asignar a users con `L-Web Meta`. `bench clear-cache` + hard-reload.

---
