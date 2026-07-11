// /anuncios — dashboard de Anuncios Meta con atribucion CTWA.

(function () {
	'use strict';

	var state = {
		orderBy: 'clicks',
		from: '',
		to: '',
		estado: '',
		search: '',
	};

	var els = {};

	function fmtNumber(n) {
		return (n || 0).toLocaleString('es-PE');
	}
	function fmtCurrency(n) {
		return (n || 0).toLocaleString('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}
	function escapeHtml(s) {
		if (s == null) return '';
		return String(s)
			.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
	}
	function fmtDate(s) {
		if (!s) return '-';
		try {
			var d = new Date(s.replace(' ', 'T'));
			return d.toLocaleDateString('es-PE', { day: '2-digit', month: 'short', year: 'numeric' });
		} catch (e) { return s; }
	}

	function callApi(method, args) {
		var params = new URLSearchParams();
		Object.keys(args || {}).forEach(function (k) {
			if (args[k] !== null && args[k] !== undefined && args[k] !== '') params.append(k, args[k]);
		});
		return fetch('/api/method/marketinghub.www.anuncios.index.' + method + '?' + params.toString(), {
			credentials: 'same-origin',
			headers: { 'X-Frappe-CSRF-Token': window.csrf_token || 'None' },
		}).then(function (r) { return r.json(); }).then(function (j) { return j.message; });
	}

	function loadEstados() {
		return callApi('get_estados_disponibles', {}).then(function (estados) {
			var opts = '<option value="">Todos</option>';
			(estados || []).forEach(function (e) {
				opts += '<option value="' + escapeHtml(e) + '">' + escapeHtml(e) + '</option>';
			});
			els.estado.innerHTML = opts;
		});
	}

	function loadStats() {
		var args = { from_date: state.from, to_date: state.to, estado: state.estado, search_term: state.search };
		return callApi('get_anuncios_stats', args).then(function (s) {
			if (!s) return;
			els.kpiAnuncios.textContent = fmtNumber(s.anuncios_con_clicks);
			els.kpiClicks.textContent = fmtNumber(s.total_clicks);
			els.kpiLeads.textContent = fmtNumber(s.leads_totales);
			els.kpiClientes.textContent = fmtNumber(s.leads_cliente) + (s.conversion_pct ? ' (' + s.conversion_pct + '%)' : '');
			els.kpiVentas.textContent = fmtNumber(s.ventas);
			els.kpiIngresos.textContent = fmtCurrency(s.ingresos);
		});
	}

	function loadAnuncios() {
		els.tbody.innerHTML = '<tr><td colspan="9" class="empty">Cargando...</td></tr>';
		var args = {
			start: 0, page_length: 100,
			from_date: state.from, to_date: state.to,
			estado: state.estado, search_term: state.search,
			order_by: state.orderBy,
		};
		return callApi('get_anuncios_batch', args).then(function (rows) {
			if (!rows || !rows.length) {
				els.tbody.innerHTML = '<tr><td colspan="9" class="empty">No hay anuncios con clicks o ventas en este rango.</td></tr>';
				return;
			}
			var html = rows.map(function (a) {
				var etiquetaHtml = a.etiqueta ? '<span class="anuncio-etiqueta">' + escapeHtml(a.etiqueta) + '</span>' : '';
				var estadoHtml = a.estado ? '<span class="estado-badge estado-' + escapeHtml(a.estado) + '">' + escapeHtml(a.estado) + '</span>' : '-';
				return '<tr data-name="' + escapeHtml(a.name) + '">' +
					'<td><span class="anuncio-name">' + escapeHtml(a.nombre || a.name) + '</span>' + etiquetaHtml + '</td>' +
					'<td>' + escapeHtml(a.meta_id || '-') + '</td>' +
					'<td>' + estadoHtml + '</td>' +
					'<td class="text-right">' + fmtNumber(a.clicks) + '</td>' +
					'<td class="text-right">' + fmtNumber(a.leads) + '</td>' +
					'<td class="text-right">' + fmtNumber(a.leads_cliente) + '</td>' +
					'<td class="text-right">' + a.conversion_pct + '%</td>' +
					'<td class="text-right">' + fmtNumber(a.ventas) + '</td>' +
					'<td class="text-right">' + fmtCurrency(a.ingresos) + '</td>' +
				'</tr>';
			}).join('');
			els.tbody.innerHTML = html;

			els.tbody.querySelectorAll('tr[data-name]').forEach(function (row) {
				row.addEventListener('click', function () { openDetail(row.dataset.name); });
			});
		});
	}

	function openDetail(anuncioName) {
		els.modal.classList.remove('hidden');
		els.detailTitle.textContent = 'Cargando detalle...';
		els.detailClicks.textContent = '';
		els.detailVentas.textContent = '';
		callApi('get_anuncio_detail', { anuncio_name: anuncioName }).then(function (d) {
			if (!d || !d.anuncio) {
				els.detailTitle.textContent = 'Anuncio no encontrado';
				return;
			}
			var a = d.anuncio;
			els.detailTitle.innerHTML = escapeHtml(a.nombre || a.name) +
				' <span style="font-weight:400;color:var(--text-muted);font-size:12px;">· meta_id ' + escapeHtml(a.meta_id || '-') + '</span>';

			// Clicks
			if (!d.clicks || !d.clicks.length) {
				els.detailClicks.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">Sin clicks registrados.</div>';
			} else {
				var clickRows = d.clicks.map(function (c) {
					var estadoBadge = c.custom_estado === 'Cliente'
						? '<span class="estado-badge estado-ACTIVE">Cliente</span>'
						: '<span style="color:var(--text-muted);font-size:11px;">Lead</span>';
					return '<tr>' +
						'<td>' + fmtDate(c.clickeado_en) + '</td>' +
						'<td>' + escapeHtml(c.lead_display_name || c.lead_name || '-') + '</td>' +
						'<td>' + escapeHtml(c.mobile_no || '-') + '</td>' +
						'<td>' + estadoBadge + '</td>' +
						'<td style="font-size:11px;color:var(--text-muted);">' + escapeHtml((c.ctwa_clid || '').substring(0, 20) || '-') + '</td>' +
					'</tr>';
				}).join('');
				els.detailClicks.innerHTML = '<table><thead><tr><th>Fecha</th><th>Lead</th><th>Teléfono</th><th>Estado</th><th>CTWA CLID</th></tr></thead><tbody>' + clickRows + '</tbody></table>';
			}

			// Ventas
			if (!d.ventas || !d.ventas.length) {
				els.detailVentas.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">Sin ventas atribuidas.</div>';
			} else {
				var ventaRows = d.ventas.map(function (v) {
					return '<tr>' +
						'<td>' + fmtDate(v.posting_date) + '</td>' +
						'<td>' + escapeHtml(v.name) + '</td>' +
						'<td>' + escapeHtml(v.customer_name || '-') + '</td>' +
						'<td class="text-right" style="font-variant-numeric:tabular-nums;">S/ ' + fmtCurrency(v.grand_total) + '</td>' +
					'</tr>';
				}).join('');
				els.detailVentas.innerHTML = '<table><thead><tr><th>Fecha</th><th>Factura</th><th>Cliente</th><th style="text-align:right;">Total</th></tr></thead><tbody>' + ventaRows + '</tbody></table>';
			}
		});
	}

	function closeDetail() {
		els.modal.classList.add('hidden');
	}

	function refreshAll() {
		state.from = els.from.value;
		state.to = els.to.value;
		state.estado = els.estado.value;
		state.search = els.search.value.trim();
		Promise.all([loadStats(), loadAnuncios()]);
	}

	function setDefaultDates() {
		var now = new Date();
		var monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
		els.from.value = monthAgo.toISOString().slice(0, 10);
		els.to.value = now.toISOString().slice(0, 10);
	}

	document.addEventListener('DOMContentLoaded', function () {
		els.from = document.getElementById('f-from');
		els.to = document.getElementById('f-to');
		els.estado = document.getElementById('f-estado');
		els.search = document.getElementById('f-search');
		els.btnRefresh = document.getElementById('btn-refresh');
		els.tbody = document.getElementById('anuncios-tbody');
		els.kpiAnuncios = document.getElementById('kpi-anuncios');
		els.kpiClicks = document.getElementById('kpi-clicks');
		els.kpiLeads = document.getElementById('kpi-leads');
		els.kpiClientes = document.getElementById('kpi-clientes');
		els.kpiVentas = document.getElementById('kpi-ventas');
		els.kpiIngresos = document.getElementById('kpi-ingresos');
		els.modal = document.getElementById('detail-modal');
		els.detailTitle = document.getElementById('detail-title');
		els.detailClicks = document.getElementById('detail-clicks');
		els.detailVentas = document.getElementById('detail-ventas');
		els.detailClose = document.getElementById('detail-close');

		setDefaultDates();
		els.btnRefresh.addEventListener('click', refreshAll);
		els.search.addEventListener('keydown', function (e) { if (e.key === 'Enter') refreshAll(); });
		els.detailClose.addEventListener('click', closeDetail);
		els.modal.addEventListener('click', function (e) { if (e.target === els.modal) closeDetail(); });

		document.querySelectorAll('.sortable').forEach(function (th) {
			th.addEventListener('click', function () {
				state.orderBy = th.dataset.order;
				loadAnuncios();
			});
		});

		loadEstados().then(refreshAll);
	});
})();
