# Historial de cambios — www/campanas_meta

## 2026-04-16 20:20 — Refactor roles sintaxis `L-<Modulo>-<Funcion>` con split Ver/Administrar

**Tipo**: refactor

**Descripcion**:
Primera entrada. Migracion del modulo "Gestion de Campanas Meta" del
split legacy `L-Ver Campanas` / `L-Editar Campanas` al estandar:
- `L-CampanasMeta-Ver`: lectura de campanas + conjuntos + anuncios
  (`obtener_campanas`, `obtener_anuncios_disponibles`,
  `obtener_conjuntos_disponibles`, `obtener_etiquetas_lead`,
  `obtener_leads_por_etiquetas`).
- `L-CampanasMeta-Administrar`: ademas crear/editar/eliminar campanas
  (`guardar_campana`, `eliminar_campana`), sincronizar nombres con
  Meta API, crear/actualizar etiquetas de lead
  (`crear_etiqueta_lead`, `actualizar_palabras_clave_etiqueta`) y
  ejecutar diagnostico de renombrado (`diagnosticar_renombrado`).

**Archivos modificados**:
- `index.py` — tuplas `ADMIN_ROLES` / `VIEW_ROLES`, helpers estandar
  `_is_admin`, `_can_view`, `_require_view`, `_require_admin`. La
  funcion `check_edit_permission()` del modulo ahora delega a
  `_require_admin()` (antes hacia `frappe.throw` inline con el rol
  legacy). `get_context` expone `no_access`, `required_roles` y
  `can_edit` (reemplaza el par `has_view_role` / `has_edit_role`).
  Endpoints gateados: 5 view + 5 admin + 1 diagnostico admin.
- `index.html` — overlay canonico `cmp-na-*`. Bloque
  `{% if no_access %}...{% else %}...{% endif %}` alrededor del
  contenido. `window.CMP_CAN_EDIT` inyectado. Jinja
  `{% if can_edit %}` sobre los botones "Sincronizar desde Meta" y
  "Diagnostico renombrado" (antes visibles para view-only). Script
  tags solo si hay acceso.
- `../panel_ventas/index.py` — `context.has_campanas_role` ahora
  acepta legacy (`L-Ver Campanas`, `L-Editar Campanas`) + nuevos
  (`L-CampanasMeta-Ver`, `L-CampanasMeta-Administrar`) para no
  romper el sidebar durante la transicion.

**Cambio relacionado en**:
- `../meta_ads/Historial_cambios.md`

**Notas**:
- **Fix colateral**: antes los botones "Sincronizar desde Meta" y
  "Diagnostico renombrado" estaban visibles para users con solo
  view role, aunque los endpoints backend si gateaban. Ahora ambos
  botones se ocultan via jinja para viewers.
- **Pasos Desk**: crear `L-CampanasMeta-Ver` y
  `L-CampanasMeta-Administrar`. Reasignar users que tenian
  `L-Ver Campanas` → `-Ver`; `L-Editar Campanas` → `-Administrar`.
  `bench clear-cache` + hard-reload.

---
