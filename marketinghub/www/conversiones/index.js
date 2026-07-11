// Dashboard /conversiones — serie temporal + ranking anuncios CTWA.
(function () {
    'use strict';

    let chart = null;
    let currentRange = { from: null, to: null, days: 30 };

    function formatSoles(v) {
        const n = Number(v || 0);
        return 'S/ ' + n.toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function formatShortSoles(v) {
        const n = Number(v || 0);
        if (n >= 1000000) return 'S/ ' + (n / 1000000).toFixed(1) + 'M';
        if (n >= 1000) return 'S/ ' + (n / 1000).toFixed(1) + 'k';
        return 'S/ ' + n.toFixed(0);
    }

    function isoDate(d) {
        return d.toISOString().slice(0, 10);
    }

    function setRangeInputs(from, to) {
        document.getElementById('range-from').value = from;
        document.getElementById('range-to').value = to;
    }

    function setActiveDaysButton(days) {
        document.querySelectorAll('.range-btn').forEach(b => {
            b.classList.toggle('active', Number(b.dataset.days) === Number(days));
        });
    }

    function fetchData() {
        const args = {
            from_date: currentRange.from,
            to_date: currentRange.to,
        };

        frappe.call({
            method: 'marketinghub.www.conversiones.index.get_conversiones_data',
            args: args,
            callback: (r) => {
                if (!r || !r.message) return;
                renderKPIs(r.message.kpis);
                renderChart(r.message.serie, r.message.granularidad);
                renderRanking(r.message.ranking);
                document.getElementById('chart-granularidad').textContent = {
                    day: 'día', week: 'semana', month: 'mes',
                }[r.message.granularidad] || 'día';
            },
        });
    }

    function renderKPIs(kpis) {
        document.getElementById('kpi-revenue').textContent = formatShortSoles(kpis.total_revenue);
        const pct = Number(kpis.pct_revenue || 0).toFixed(1);
        document.getElementById('kpi-revenue-sub').textContent =
            pct + '% del total (' + formatShortSoles(kpis.revenue_global) + ')';

        document.getElementById('kpi-facturas').textContent = kpis.total_facturas;
        const globalCount = kpis.facturas_global || 0;
        const pctFacturas = globalCount ? Math.round(kpis.total_facturas / globalCount * 100) : 0;
        document.getElementById('kpi-facturas-sub').textContent =
            pctFacturas + '% del total (' + globalCount + ')';

        document.getElementById('kpi-ticket').textContent = formatShortSoles(kpis.ticket_promedio);
        document.getElementById('kpi-anuncios').textContent = kpis.anuncios_distintos;
    }

    function destroyChart(canvas) {
        // Chart.js v4: Chart.getChart(canvas) es la referencia autoritativa
        // aunque la variable local `chart` este stale por race conditions
        // entre callbacks del range picker.
        const existing = (typeof Chart !== 'undefined' && Chart.getChart)
            ? Chart.getChart(canvas)
            : null;
        if (existing) existing.destroy();
        chart = null;
    }

    function renderChart(serie, granularidad) {
        const canvas = document.getElementById('chart-serie');
        const empty = document.getElementById('chart-empty');

        if (!serie || serie.length === 0) {
            destroyChart(canvas);
            canvas.style.display = 'none';
            empty.style.display = 'block';
            return;
        }
        canvas.style.display = 'block';
        empty.style.display = 'none';

        const labels = serie.map(p => p.bucket_date);
        const revenues = serie.map(p => Number(p.revenue || 0));
        const facturas = serie.map(p => Number(p.facturas || 0));

        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
        const tickColor = isDark ? '#94a3b8' : '#6b7280';

        destroyChart(canvas);
        chart = new Chart(canvas.getContext('2d'), {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Revenue',
                        data: revenues,
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.12)',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: true,
                        yAxisID: 'y',
                        pointRadius: 3,
                        pointHoverRadius: 5,
                    },
                    {
                        label: '# Facturas',
                        data: facturas,
                        borderColor: '#22c55e',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [4, 4],
                        tension: 0.2,
                        fill: false,
                        yAxisID: 'y1',
                        pointRadius: 2,
                        pointHoverRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                if (ctx.datasetIndex === 0) {
                                    return 'Revenue: ' + formatSoles(ctx.parsed.y);
                                }
                                return 'Facturas: ' + ctx.parsed.y;
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { color: gridColor },
                        ticks: { color: tickColor },
                    },
                    y: {
                        position: 'left',
                        grid: { color: gridColor },
                        ticks: {
                            color: tickColor,
                            callback: (v) => formatShortSoles(v),
                        },
                    },
                    y1: {
                        position: 'right',
                        grid: { display: false },
                        ticks: { color: tickColor, precision: 0 },
                        beginAtZero: true,
                    },
                },
            },
        });
    }

    function renderRanking(rows) {
        const tbody = document.getElementById('ranking-tbody');
        const countEl = document.getElementById('ranking-count');
        countEl.textContent = rows.length + (rows.length === 1 ? ' anuncio' : ' anuncios');

        if (!rows || rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="ranking-empty">Sin datos en el rango seleccionado.</td></tr>';
            return;
        }

        tbody.innerHTML = rows.map(r => {
            const nombre = r.nombre || r.anuncio_id || '';
            return '<tr>'
                + '<td class="ad-name" title="' + String(nombre).replace(/"/g, '&quot;') + '">' + nombre + '</td>'
                + '<td class="right">' + r.facturas + '</td>'
                + '<td class="right revenue-cell">' + formatSoles(r.revenue) + '</td>'
                + '<td class="right">' + formatSoles(r.ticket) + '</td>'
                + '<td>' + (r.primera || '—') + '</td>'
                + '<td>' + (r.ultima || '—') + '</td>'
                + '</tr>';
        }).join('');
    }

    function applyDaysRange(days) {
        const to = new Date();
        const from = new Date();
        from.setDate(from.getDate() - Number(days) + 1);
        currentRange = { from: isoDate(from), to: isoDate(to), days: Number(days) };
        setRangeInputs(currentRange.from, currentRange.to);
        setActiveDaysButton(days);
        fetchData();
    }

    function applyCustomRange() {
        const from = document.getElementById('range-from').value;
        const to = document.getElementById('range-to').value;
        if (!from || !to) {
            frappe.show_alert && frappe.show_alert('Selecciona fechas válidas.', 3);
            return;
        }
        currentRange = { from: from, to: to, days: null };
        setActiveDaysButton(null);
        fetchData();
    }

    function init() {
        document.querySelectorAll('.range-btn').forEach(b => {
            b.addEventListener('click', () => applyDaysRange(Number(b.dataset.days)));
        });
        document.getElementById('range-apply').addEventListener('click', applyCustomRange);

        applyDaysRange(30);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
