# Funcionamiento Total - Ventas & Campanas

## Proposito
Pagina que muestra un reporte tipo Excel con todas las ventas vinculadas a campanas
publicitarias de Meta Ads, incluyendo datos de contacto, gasto a nivel de anuncio y ROAS.

Accesible en: `/ventas_campanas`

## Flujo de Datos

### Cadena de vinculacion
1. **Sales Invoice** (factura) -> tiene `custom_conversacion_chatwoot`
2. **Conversacion Chatwoot** -> tiene `etiquetas` (Etiqueta Lead Asociado) y `inbox_name`
3. **Etiqueta Lead** (ej: "BH10 #60") -> vinculada a un **Anuncio** via campo `etiqueta`
4. **Anuncio** -> pertenece a un **Conjunto Anuncios** via child table `anuncios_asociados`
5. **Conjunto Anuncios** -> pertenece a una **Campana Meta** via child table `conjunto_anuncios_asociados`
6. **Anuncio** -> tiene `meta_id` para consultar gasto diario via Meta API a nivel de anuncio

### Gasto diario
Se obtiene en tiempo real desde la API de Meta Ads:
- Endpoint: `GET /act_{account_id}/insights?level=ad&time_increment=1&fields=ad_id,spend`
- Filtrado por ad_ids (meta_id de los anuncios) relevantes
- El gasto se cruza con la fecha de contacto de cada venta
- IMPORTANTE: el gasto es a nivel de ANUNCIO individual, no de toda la campana

### ROAS
Calculado como: `ticket_venta / gasto_dia_anuncio`
- Verde (>= 3x): excelente
- Amarillo (>= 1x): moderado
- Rojo (< 1x): perdida

### Ganancia
Calculada como: `ticket_venta - costo_producto - envio - gasto_dia_anuncio`

## Columnas

| Columna | Fuente |
|---------|--------|
| VENDEDORA | Sales Order owner -> User full_name |
| FECHA VENTA | Sales Invoice posting_date |
| FECHA CONTACTO | Conversacion Chatwoot creation |
| WHATSAPP CLIENTE | Customer custom_numero |
| WHATSAPP EMPRESA | Conversacion Chatwoot inbox_name o SO numeros_contacto |
| NOMBRE CAMPANA | Campana Meta nombre (via cadena etiqueta->anuncio->conjunto->campana) |
| CONJUNTO ANUNCIOS | Conjunto Anuncios nombre (via cadena etiqueta->anuncio->conjunto) |
| ANUNCIO | Anuncio nombre (via cadena etiqueta->anuncio) |
| GASTO DIA | Meta API insights spend del dia de contacto (a nivel anuncio) |
| CODIGO CAMPANA | Etiquetas lead del Sales Order |
| ROAS | ticket_venta / gasto_dia_anuncio |
| TICKET VENTA | Sales Invoice grand_total |
| COSTO PROD. | Precio compra (Item Price 'Compra estandar') + costos adicionales por item |
| ENVIO | Items con item_code "Item Extra" del Sales Order |
| GANANCIA | ticket - costo_producto - envio - gasto_dia |
| CLIENTE | Sales Invoice customer_name |

## Permisos
Requiere rol "Pedidos" o "L-Web Meta".

## Endpoints

### GET get_ventas_data
Parametros: from_date, to_date, account_id (opcional)
Retorna array de objetos con todas las columnas.

### GET export_ventas_xlsx
Mismos parametros. Descarga archivo XLSX con formato profesional.
