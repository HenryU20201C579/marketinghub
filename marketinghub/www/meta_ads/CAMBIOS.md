# Meta Ads - Cambios Realizados

## Editar Configuracion de Campana desde Meta Ads

Se agrego la funcionalidad de editar la configuracion de campanas (nombre, conjuntos, anuncios, etiquetas) directamente desde meta_ads, sin necesidad de ir a campanas_meta. Los cambios se sincronizan automaticamente con Meta API.

### Archivos modificados

- `index.html` - Modal de edicion, modal de log de resultados, elemento toast
- `index.js` - Logica completa del editor, selector de etiquetas, guardado, notificaciones
- `index.css` - Estilos del editor tree-layout, tag selector, toast, log modal

### Funcionalidades

**Boton de editar en la tabla**
- Icono de lapiz al lado del nombre de cada fila (campana/conjunto/anuncio)
- Aparece con hover sobre la fila
- Tambien disponible en el modal de detalle (boton "Editar Config" en el header)

**Modal de edicion (tree-layout)**
- Panel izquierdo: datos de campana (nombre, objetivo) + lista de conjuntos clicable
- Panel derecho: detalle del conjunto seleccionado (nombre, presupuesto) + anuncios con selector de etiqueta
- Al cambiar de conjunto, se guardan automaticamente los cambios del panel actual

**Selector de etiquetas (replica el patron de campanas_meta)**
- Trigger clicable con badge de etiqueta actual
- Dropdown con buscador que filtra por nombre y palabras clave
- Preview de activadores/keywords debajo de cada opcion
- Boton "Nueva etiqueta" para crear inline
- Boton de editar (lapiz) para modificar activadores de una etiqueta existente
- Boton X para quitar la etiqueta asignada

**Crear / Editar etiqueta**
- Modal dedicado (z-index 10020) con campos nombre + activadores
- Llama a los mismos endpoints de campanas_meta: `crear_etiqueta_lead` y `actualizar_palabras_clave_etiqueta`
- Al crear, auto-selecciona la nueva etiqueta en el anuncio

**Guardar y Sincronizar**
- Llama a `lizaraso.www.campanas_meta.index.guardar_campana` (mismo endpoint que campanas_meta)
- Sincroniza automaticamente con Meta API los nombres que fueron renombrados
- Despues de guardar, recarga el mapping ERP y re-renderiza la tabla

**Indicadores de resultado**
- Toast (esquina inferior derecha): notificacion rapida verde/rojo/amarillo para acciones como crear etiqueta, errores de validacion, etc.
- Modal de log detallado: se abre automaticamente despues de guardar mostrando resumen (X OK, X Avisos, X Errores) y cada linea con el detalle de lo que se hizo

### Endpoints reutilizados (de campanas_meta)

- `lizaraso.www.campanas_meta.index.obtener_campanas` - carga la jerarquia completa
- `lizaraso.www.campanas_meta.index.guardar_campana` - guarda y sincroniza con Meta
- `lizaraso.www.campanas_meta.index.obtener_etiquetas_lead` - lista etiquetas con palabras clave
- `lizaraso.www.campanas_meta.index.crear_etiqueta_lead` - crea nueva etiqueta
- `lizaraso.www.campanas_meta.index.actualizar_palabras_clave_etiqueta` - edita activadores

### Jerarquia de modales (z-index)

| Modal | z-index |
|---|---|
| Row Detail | 9998 |
| Chat Conversacion | 10000 |
| Edit Campaign | 10001 |
| Log Modal | 10005 |
| Tag Dropdown | 10010 |
| Crear/Editar Etiqueta | 10020 |

Escape cierra en orden de prioridad: etiqueta modal > tag dropdown > log modal > edit camp > chat > row detail.

---

## Error conocido: Meta no permite renombrar ciertos anuncios

Al renombrar un anuncio en Meta, puede aparecer el siguiente aviso:

> Meta Anuncio 'BH03 #2 | Le regalas - P': no permite renombrar (Cuenta de WhatsApp Business obligatoria) - guardado solo en ERP

**Causa:** Meta rechaza el renombrado de anuncios que estan vinculados a una Cuenta de WhatsApp Business. Esto ocurre tipicamente con anuncios de tipo "Click to WhatsApp" o campanas de mensajes que requieren una cuenta de WhatsApp Business verificada.

**Comportamiento:** El cambio de nombre se guarda correctamente en el ERP local, pero NO se refleja en Meta Ads Manager. El modal de log muestra esto como "aviso" (warning) en amarillo.

**Solucion:** Para renombrar estos anuncios en Meta, se debe hacer manualmente desde el Ads Manager de Meta. El nombre en el ERP quedara actualizado independientemente.

---

## Otros cambios previos en esta sesion

**Fix: LEADS (FILTRO) consistente con LEADS CLIENTE**
- La columna LEADS (FILTRO) ahora solo cuenta leads que son clientes con factura en el periodo seleccionado
- Usa la misma logica de filtrado por fecha de factura que `get_sales_data_por_etiquetas`

**Feature: Ver conversacion desde meta_ads**
- Boton "Ver Mensajes" en cada lead del modal de detalle
- Reconstruye la conversacion WhatsApp desde los Comments del ERP
- Link directo a la conversacion en Chatwoot
