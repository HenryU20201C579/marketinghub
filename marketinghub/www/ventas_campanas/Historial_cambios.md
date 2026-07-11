# Historial de Cambios - ventas_campanas

## 2026-04-10 18:41 — Creacion de pagina Base de Datos de Ventas

**Tipo**: feature

**Descripcion**:
Nueva pagina que replica el formato del Excel del gerente, mostrando ventas vinculadas
con campanas de Meta Ads, datos de contacto y gasto publicitario.

Columnas implementadas:
- VENDEDORA: owner del Sales Order
- FECHA DE VENTA: posting_date de la factura
- FECHA DE CONTACTO: creation de la Conversacion Chatwoot vinculada
- WHATSAPP CLIENTE: custom_numero del Customer
- WHATSAPP EMPRESA: inbox_name de la conversacion o numeros de contacto del SO
- NOMBRE DE CAMPANA: cruce etiqueta lead -> Anuncio -> Conjunto -> Campana Meta
- GASTO ESE DIA CAMPANA: spend diario desde Meta API (insights con time_increment=1)
- CODIGO DE CAMPANA: etiquetas lead del Sales Order
- ROAS: ticket_venta / gasto_dia
- TICKET DE VENTA: grand_total de la factura
- CLIENTE: customer_name

Funcionalidades:
- Filtro por rango de fechas
- Selector de cuenta publicitaria Meta para obtener gasto
- Exportar a XLSX
- KPIs resumen: total ventas, ticket promedio, ventas con campana, ROAS promedio

**Archivos modificados**:
- `index.py` — backend con endpoints get_ventas_data y export_ventas_xlsx
- `index.html` — template con filtros, tabla y resumen
- `index.js` — logica frontend para carga de datos y renderizado
- `index.css` — estilos de la pagina

---

## 2026-04-11 09:01 — Corregir gasto a nivel anuncio + agregar columnas conjunto y anuncio

**Tipo**: fix

**Descripcion**:
El gasto publicitario se estaba obteniendo a nivel de CAMPANA completa desde la Meta API
(level=campaign), lo que significaba que si una venta venia de un anuncio especifico dentro
de una campana con multiples anuncios, el gasto mostrado correspondia a TODA la campana,
no solo al anuncio que genero la venta. Esto distorsionaba el ROAS y la ganancia real.

Cambios realizados:
1. La Meta API ahora consulta a nivel `ad` (anuncio) en vez de `campaign`, usando el
   `meta_id` del Anuncio especifico vinculado a la etiqueta lead.
2. Se agregaron 2 nuevas columnas: "Conjunto de Anuncios" y "Anuncio", para que el usuario
   vea exactamente de que anuncio viene cada venta.
3. Se actualizo el encabezado de gasto de "GASTO DIA CAMPANA" a "GASTO DIA" (ahora es del anuncio).
4. Se actualizo la funcion `_build_campaign_chain` para incluir `anuncio_meta_id` y
   `conjunto_nombre` (nombre amigable del conjunto).
5. Se actualizo el export XLSX con las 2 columnas nuevas y los indices de formato corregidos.

**Archivos modificados**:
- `index.py` — cambio en _fetch_daily_spend (level=ad), _build_campaign_chain (anuncio_meta_id, conjunto_nombre), get_ventas_data (nuevos campos), export_ventas_xlsx (columnas nuevas)
- `index.html` — 2 nuevas columnas th: CONJUNTO ANUNCIOS y ANUNCIO
- `index.js` — 2 nuevas celdas td en renderTable

**Notas**:
- El ROAS y ganancia ahora son precisos a nivel de anuncio individual
- Si un anuncio no tiene meta_id, el gasto sera 0 (mismo comportamiento anterior)

---

## 2026-04-11 09:05 — Agregar tooltips informativos en encabezados de tabla

**Tipo**: feature

**Descripcion**:
Se agrego un icono de info (Lucide circle-info) en cada encabezado de columna de la tabla.
Al hacer hover sobre el icono, aparece un tooltip oscuro con flecha que explica de donde
viene cada dato y como se calcula.

Tooltips por columna:
- VENDEDORA: quien creo el Sales Order
- FECHA VENTA: posting_date de Sales Invoice
- FECHA CONTACTO: creation de Conversacion Chatwoot
- WHATSAPP CLIENTE: custom_numero del Customer
- WHATSAPP EMPRESA: inbox de Chatwoot o numeros del SO
- NOMBRE CAMPANA: cadena etiqueta -> Anuncio -> Conjunto -> Campana
- CONJUNTO ANUNCIOS: etiqueta -> Anuncio -> Conjunto
- ANUNCIO: etiqueta -> Anuncio (su meta_id se usa para obtener gasto)
- GASTO DIA: Meta API level=ad, solo ese anuncio, no toda la campana
- CODIGO CAMPANA: etiquetas lead del Sales Order
- ROAS: ticket / gasto dia del anuncio
- TICKET VENTA: grand_total de Sales Invoice
- COSTO PROD.: Item Price 'Compra estandar' + costos adicionales
- ENVIO: items 'Item Extra' del Sales Order
- GANANCIA: ticket - costo - envio - gasto publicitario
- CLIENTE: customer_name de Sales Invoice

**Archivos modificados**:
- `index.html` — SVG de Lucide info + atributo data-tip en cada th
- `index.css` — estilos .th-content, .th-tip, pseudo-elementos ::after y ::before

---
