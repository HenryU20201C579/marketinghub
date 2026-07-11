# Calculo de Gastos Publicitarios - Ventas & Campanas

## Resumen

Este documento explica como se calcula el gasto publicitario por venta, el ROAS y la ganancia real en la pagina `/ventas_campanas`. Incluye los problemas detectados el 11/04/2026 y las correcciones aplicadas.

---

## Flujo de vinculacion: De la venta al anuncio

```
Sales Invoice (factura)
    -> Customer -> Lead (via custom_lead)
        -> Conversacion Chatwoot (via lead)
            -> fecha_contacto (creation de la conversacion)
            -> etiquetas lead (ej: "BH10 #48")
                -> Anuncio (doctype, via campo etiqueta)
                    -> meta_id del anuncio (para consultar gasto en Meta API)
                    -> Conjunto Anuncios (via child table anuncios_asociados)
                        -> Campana Meta (via child table conjunto_anuncios_asociados)
```

Cada venta se vincula a un anuncio especifico de Meta Ads a traves de la etiqueta lead asignada en Chatwoot.

---

## Como se obtiene el gasto

### Fuente de datos
- **API de Meta Ads**: `GET /act_{account_id}/insights`
- **Nivel**: `ad` (anuncio individual, NO campana)
- **Granularidad**: `time_increment=1` (gasto por dia)
- **Campo**: `ad_id, spend`

### Rango de fechas expandido
El sistema NO consulta solo las fechas del filtro del usuario. Detecta todas las `fecha_contacto` de las ventas encontradas y expande el rango para cubrirlas.

**Ejemplo**: Si filtras ventas del 10/04 pero un cliente contacto el 15/03, el sistema consulta gasto desde el 15/03 hasta el 10/04.

**Razon**: El costo de adquirir un lead es el gasto del anuncio el dia que ese lead respondio, sin importar cuando compre despues.

---

## Prorrateo del gasto entre ventas

### Problema original
Si un anuncio gasta S/ 30 en un dia y genera 3 ventas, antes se asignaba S/ 30 a CADA venta. Esto triplicaba el gasto real:

| Venta | Gasto asignado (mal) | Ganancia calculada |
|-------|---------------------|-------------------|
| Venta 1 | S/ 30 | S/ 100 |
| Venta 2 | S/ 30 | S/ 110 |
| Venta 3 | S/ 30 | S/ 90 |
| **Total** | **S/ 90 (3x real)** | **S/ 300** |

### Correccion: prorrateo
Ahora el gasto se divide entre todas las ventas generadas por ese anuncio ese dia:

```
gasto_por_venta = gasto_total_anuncio_ese_dia / cantidad_de_ventas
```

| Venta | Gasto prorrateado | Ganancia real |
|-------|-------------------|--------------|
| Venta 1 | S/ 10 (30/3) | S/ 120 |
| Venta 2 | S/ 10 (30/3) | S/ 130 |
| Venta 3 | S/ 10 (30/3) | S/ 110 |
| **Total** | **S/ 30 (correcto)** | **S/ 360** |

### Conteo historico (no depende del filtro)
El conteo de ventas para el prorrateo busca en **todas las facturas historicas**, no solo las del rango del filtro actual.

**Ejemplo**: Si "BH10 #48" genero 5 ventas el 10/03 (4 compraron en marzo, 1 compro en abril), y filtras solo abril:
- Antes: 1 venta en el filtro -> gasto/1 (incorrecto)
- Ahora: 5 ventas historicas totales -> gasto/5 (correcto)

Esto garantiza que el prorrateo sea consistente sin importar que rango de fechas filtre el usuario.

---

## Duplicados de anuncios

### Problema
El gerente a veces duplica un anuncio en Meta Ads (mismo contenido, diferente `ad_id`). Ambos comparten la misma etiqueta (ej: "BH10 #48") pero tienen distintos `meta_id`.

### Solucion
1. **Gasto**: Se SUMAN los gastos de todos los `meta_id` que comparten la misma etiqueta
2. **Prorrateo**: Se agrupa por `etiqueta + fecha_contacto` (no por `meta_id + fecha`)
3. **Consulta Meta API**: Se incluyen TODOS los `meta_id` de la misma etiqueta

**Ejemplo**:
- Anuncio original (meta_id A): gasto S/ 20 el dia X
- Duplicado (meta_id B): gasto S/ 15 el dia X
- Gasto total real para etiqueta "BH10 #48" = S/ 35
- Si genero 5 ventas: gasto por venta = S/ 35 / 5 = S/ 7

---

## Formula de ganancia

```
Ganancia = Ticket venta - Costo producto - Envio - Gasto publicitario prorrateado
```

Donde:
- **Ticket venta**: `grand_total` de la Sales Invoice
- **Costo producto**: precio en lista "Compra estandar" + costos adicionales del item
- **Envio**: solo items "Item Extra" cuyo nombre contiene "envio" (los demas Item Extra van a costo producto)
- **Gasto publicitario**: gasto total de todos los meta_ids de la etiqueta ese dia / cantidad de ventas historicas

## Formula de ROAS

```
ROAS = Ticket venta / Gasto publicitario prorrateado
```

Indicadores:
- Verde (>= 3x): excelente retorno
- Amarillo (>= 1x): moderado, recupera la inversion
- Rojo (< 1x): perdida publicitaria

---

## Vinculacion automatica de conversaciones

Al emitir (submit) una Sales Invoice, un hook automatico (`vincular_conversacion_on_submit`) busca la Conversacion Chatwoot del lead vinculado al cliente y la asigna a la factura. Tambien sincroniza las etiquetas del chat al Sales Order.

Esto permite que la cadena `factura -> conversacion -> etiqueta -> anuncio -> gasto` funcione automaticamente sin intervencion manual.

---

## Tooltips

Cada celda numerica tiene un tooltip (hover) que muestra el calculo:

- **Gasto dia**: `S/ X (gasto total anuncio) / N ventas = S/ Y por venta`
- **ROAS**: `S/ ticket / S/ gasto_prorrateado = Xx`
- **Ganancia**: `S/ ticket - S/ costo (costo) - S/ envio (envio) - S/ gasto (publicidad) = S/ ganancia`

Las tarjetas de resumen tambien tienen tooltips con el desglose total.

---

## Historial de correcciones (11/04/2026)

| Problema | Correccion |
|----------|-----------|
| Gasto a nivel campana (inflado) | Cambiado a nivel anuncio (`level=ad`) |
| Gasto repetido en multiples ventas | Prorrateo: gasto / cantidad de ventas |
| Prorrateo variaba segun filtro | Conteo historico de todas las facturas |
| Rango de fechas no cubria fecha_contacto | Rango expandido a todas las fechas de contacto |
| Item Extra siempre contado como envio | Solo si nombre contiene "envio" |
| Etiqueta con multiples meta_ids (duplicados) | Sumar gasto de todos + probar todos los meta_ids |
| Conversaciones no se vinculaban automaticamente | Hook on_submit en Sales Invoice |
| Faltaban columnas de conjunto y anuncio | Agregadas en tabla, JS y export XLSX |
