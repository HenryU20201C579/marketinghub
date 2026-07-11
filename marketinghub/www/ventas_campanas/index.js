frappe.ready(function () {
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    const elFrom = $('#filterFrom');
    const elTo = $('#filterTo');
    const elAccount = $('#filterAccount');
    const elBtnLoad = $('#btnLoad');
    const elBtnExport = $('#btnExport');
    const elTable = $('#dataTable');
    const elBody = $('#tableBody');
    const elLoading = $('#loadingState');
    const elEmpty = $('#emptyState');
    const elSummary = $('#summaryCards');

    let currentData = [];

    // Default: ultimos 7 dias
    const today = new Date();
    const past = new Date(today);
    past.setDate(past.getDate() - 7);
    elFrom.value = fmt(past);
    elTo.value = fmt(today);

    function fmt(d) {
        return d.toISOString().slice(0, 10);
    }

    function money(v) {
        if (!v && v !== 0) return '-';
        return 'S/ ' + Number(v).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function fmtDate(d) {
        if (!d) return '';
        var parts = d.split('-');
        if (parts.length !== 3) return d;
        return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    function esc(s) {
        if (!s) return '';
        const d = document.createElement('div');
        d.textContent = s;
        return d.innerHTML.replace(/"/g, '&quot;');
    }

    // Cargar cuentas publicitarias
    frappe.call({
        method: "marketinghub.api.meta_ads.get_ad_accounts",
        callback: function (r) {
            if (r.message) {
                r.message.forEach(function (acc) {
                    const opt = document.createElement('option');
                    opt.value = acc.account_id;
                    opt.textContent = acc.name + ' (' + acc.account_id + ')';
                    if (acc.name && acc.name.indexOf('Lizaraso PEN') !== -1) {
                        opt.selected = true;
                    }
                    elAccount.appendChild(opt);
                });
            }
        }
    });

    // Cargar datos
    elBtnLoad.addEventListener('click', loadData);

    function loadData() {
        const fromDate = elFrom.value;
        const toDate = elTo.value;
        const accountId = elAccount.value;

        if (!fromDate || !toDate) {
            frappe.msgprint('Selecciona un rango de fechas');
            return;
        }

        elLoading.style.display = 'flex';
        elEmpty.style.display = 'none';
        elTable.style.display = 'none';
        elSummary.style.display = 'none';
        elBtnLoad.disabled = true;

        frappe.call({
            method: "marketinghub.www.ventas_campanas.index.get_ventas_data",
            args: {
                from_date: fromDate,
                to_date: toDate,
                account_id: accountId || null
            },
            callback: function (r) {
                elLoading.style.display = 'none';
                elBtnLoad.disabled = false;

                if (r.message && r.message.length > 0) {
                    currentData = r.message;
                    renderTable(currentData);
                    renderSummary(currentData);
                    elTable.style.display = 'table';
                    elSummary.style.display = 'flex';
                    elBtnExport.disabled = false;
                } else {
                    currentData = [];
                    elEmpty.style.display = 'flex';
                    elEmpty.querySelector('p').innerHTML = 'No se encontraron ventas en este rango de fechas.';
                    elBtnExport.disabled = true;
                }
            },
            error: function () {
                elLoading.style.display = 'none';
                elBtnLoad.disabled = false;
                elEmpty.style.display = 'flex';
                elEmpty.querySelector('p').innerHTML = 'Error al cargar los datos.';
            }
        });
    }

    function tip(text, tipText) {
        return '<span class="cell-tip" data-tip="' + esc(tipText) + '">' + text + '</span>';
    }

    function renderTable(data) {
        let html = '';
        data.forEach(function (r, i) {
            const roasClass = r.roas >= 3 ? 'roas-good' : r.roas >= 1 ? 'roas-ok' : r.roas > 0 ? 'roas-bad' : '';
            var ganCellClass = r.ganancia > 0 ? 'cell-pos' : r.ganancia < 0 ? 'cell-neg' : '';
            var roasCellClass = r.roas >= 3 ? 'cell-pos' : r.roas >= 1 ? 'cell-warn' : r.roas > 0 ? 'cell-neg' : '';
            var rowClass = r.ganancia > 0 ? 'row-pos' : r.ganancia < 0 ? 'row-neg' : (r.ganancia === 0 && r.gasto_dia > 0 ? 'row-warn' : '');

            // Tooltips de calculo
            var nVentas = r.n_ventas_anuncio || 1;
            var gastoTotal = r.gasto_dia_total || 0;

            var gastoTip = r.gasto_dia
                ? (nVentas > 1
                    ? 'Gasto prorrateado del anuncio "' + (r.nombre_anuncio || '?') + '" en la fecha de contacto (' + fmtDate(r.fecha_contacto) + '). Se suma el gasto de todos los duplicados de este anuncio ese dia. Calculo: ' + money(gastoTotal) + ' (gasto total) / ' + nVentas + ' (ventas historicas de esta etiqueta+fecha) = ' + money(r.gasto_dia) + ' por venta'
                    : 'Gasto del anuncio "' + (r.nombre_anuncio || '?') + '" en la fecha de contacto (' + fmtDate(r.fecha_contacto) + '). Es el gasto completo porque solo hubo 1 venta de este anuncio ese dia. Monto: ' + money(r.gasto_dia))
                : 'Sin gasto. Posibles causas: (1) el anuncio no tiene meta_id configurado, (2) no hay fecha de contacto, (3) el anuncio no tuvo gasto ese dia en Meta, o (4) no hay etiqueta que vincule esta venta con un anuncio';

            var roasTip = r.roas
                ? 'Retorno sobre gasto publicitario. Formula: ticket / gasto prorrateado. Calculo: ' + money(r.ticket_venta) + ' / ' + money(r.gasto_dia) + ' = ' + r.roas.toFixed(2) + 'x. ' + (r.roas >= 3 ? 'Excelente retorno' : r.roas >= 1 ? 'Moderado, recupera la inversion' : 'Perdida publicitaria')
                : 'Sin ROAS. No se puede calcular porque no hay gasto publicitario vinculado a esta venta. Verifica que el anuncio tenga meta_id y que haya gasto registrado en la fecha de contacto';

            var costoTip = r.costo_producto
                ? 'Costo del producto. Incluye: precio en lista "Compra estandar" + costos adicionales del item (comisiones, empaque, etc). Si hubo Items Extra que no son envio (ej: grabado), tambien se suman aqui. Total: ' + money(r.costo_producto)
                : 'Sin costo de producto. El item no tiene precio en la lista "Compra estandar". Debe cargarse para que la ganancia sea precisa';

            var envioTip = r.envio
                ? 'Costo de envio. Solo se cuentan Items Extra cuyo nombre contiene "envio". Total: ' + money(r.envio)
                : 'Sin envio. No hay Items Extra con "envio" en el nombre en este pedido';

            var gananciaTip = 'Ganancia real de esta venta. Formula: ticket - costo producto - envio - gasto publicitario prorrateado. Calculo: ' + money(r.ticket_venta) + ' - ' + money(r.costo_producto || 0) + ' (costo) - ' + money(r.envio || 0) + ' (envio) - ' + money(r.gasto_dia || 0) + ' (publicidad' + (nVentas > 1 ? ': ' + money(gastoTotal) + ' total / ' + nVentas + ' ventas' : '') + ') = ' + money(r.ganancia);

            html += '<tr class="' + (i % 2 === 0 ? '' : 'alt') + ' ' + rowClass + '">'
                + '<td>' + esc(r.vendedora) + '</td>'
                + '<td>' + fmtDate(r.fecha_venta) + '</td>'
                + '<td>' + fmtDate(r.fecha_contacto) + '</td>'
                + '<td>' + esc(r.whatsapp_cliente) + '</td>'
                + '<td>' + esc(r.whatsapp_empresa) + '</td>'
                + '<td>' + esc(r.nombre_campana) + '</td>'
                + '<td>' + esc(r.nombre_conjunto) + '</td>'
                + '<td>' + esc(r.nombre_anuncio) + '</td>'
                + '<td class="num">' + tip(r.gasto_dia ? money(r.gasto_dia) : '-', gastoTip) + '</td>'
                + '<td><span class="bd-tag">' + esc(r.codigo_campana) + '</span></td>'
                + '<td class="num ' + roasCellClass + '">' + tip(r.roas ? r.roas.toFixed(2) + 'x' : '-', roasTip) + '</td>'
                + '<td class="num">' + money(r.ticket_venta) + '</td>'
                + '<td class="num">' + tip(r.costo_producto ? money(r.costo_producto) : '-', costoTip) + '</td>'
                + '<td class="num">' + tip(r.envio ? money(r.envio) : '-', envioTip) + '</td>'
                + '<td class="num ' + ganCellClass + '">' + tip(money(r.ganancia), gananciaTip) + '</td>'
                + '<td>' + esc(r.cliente) + '</td>'
                + '</tr>';
        });
        elBody.innerHTML = html;
    }

    function renderSummary(data) {
        const total = data.length;
        const sumTicket = data.reduce(function (a, r) { return a + (r.ticket_venta || 0); }, 0);
        const avgTicket = total > 0 ? sumTicket / total : 0;
        const conCampana = data.filter(function (r) { return r.nombre_campana; }).length;
        const roasValues = data.filter(function (r) { return r.roas > 0; }).map(function (r) { return r.roas; });
        const avgRoasNum = roasValues.length > 0
            ? roasValues.reduce(function (a, b) { return a + b; }, 0) / roasValues.length
            : 0;
        const avgRoas = avgRoasNum > 0 ? avgRoasNum.toFixed(2) + 'x' : '-';

        var totalGanancia = data.reduce(function (a, r) { return a + (r.ganancia || 0); }, 0);
        var totalCosto = data.reduce(function (a, r) { return a + (r.costo_producto || 0); }, 0);
        var totalEnvio = data.reduce(function (a, r) { return a + (r.envio || 0); }, 0);
        var totalGasto = data.reduce(function (a, r) { return a + (r.gasto_dia || 0); }, 0);

        var sinCosto = data.filter(function (r) { return !r.costo_producto && r.ticket_venta > 0; }).length;

        $('#sumVentas').textContent = total;
        $('#sumTicket').innerHTML = '<span class="cell-tip" data-tip="' + esc('Ticket promedio. Suma de todos los tickets / cantidad de ventas. Calculo: ' + money(sumTicket) + ' / ' + total + ' ventas = ' + money(avgTicket)) + '">' + money(avgTicket) + '</span>';
        $('#sumCampana').innerHTML = '<span class="cell-tip" data-tip="' + esc('Ventas vinculadas a una campana de Meta Ads (tienen etiqueta -> anuncio -> campana). ' + conCampana + ' de ' + total + ' ventas (' + (total > 0 ? (conCampana/total*100).toFixed(1) : 0) + '%). Las que no tienen campana son ventas directas o sin etiqueta asignada') + '">' + conCampana + ' / ' + total + '</span>';
        $('#sumRoas').innerHTML = '<span class="cell-tip" data-tip="' + esc('ROAS promedio de las ventas que tienen gasto publicitario. Solo se promedian ' + roasValues.length + ' ventas (las que tienen gasto > 0). Formula: suma de todos los ROAS individuales / ' + roasValues.length + ' = ' + avgRoas + '. Cada ROAS individual usa el gasto prorrateado (gasto del anuncio ese dia / ventas historicas de esa etiqueta)') + '">' + avgRoas + '</span>';
        $('#sumGanancia').innerHTML = '<span class="cell-tip" data-tip="' + esc('Ganancia total de todas las ventas. Formula: total tickets - total costos - total envios - total publicidad prorrateada. Calculo: ' + money(sumTicket) + ' (ventas) - ' + money(totalCosto) + ' (costos producto) - ' + money(totalEnvio) + ' (envios) - ' + money(totalGasto) + ' (publicidad prorrateada) = ' + money(totalGanancia) + (sinCosto > 0 ? '. Nota: ' + sinCosto + ' ventas no tienen costo de producto registrado' : '')) + '">' + money(totalGanancia) + '</span>';
    }

    // Export
    elBtnExport.addEventListener('click', function () {
        const fromDate = elFrom.value;
        const toDate = elTo.value;
        const accountId = elAccount.value;

        const params = new URLSearchParams();
        if (fromDate) params.set('from_date', fromDate);
        if (toDate) params.set('to_date', toDate);
        if (accountId) params.set('account_id', accountId);

        window.open('/api/method/marketinghub.www.ventas_campanas.index.export_ventas_xlsx?' + params.toString(), '_blank');
    });
});
