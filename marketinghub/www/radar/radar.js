/* ============================================
   Radar de Competencia - JS compartido
   ============================================ */
(function () {
	'use strict';

	// ---------- API helper ----------
	async function apiCall(method, args, options) {
		options = options || {};
		const csrf = (window.frappe && frappe.csrf_token) ||
		             document.querySelector('meta[name="csrf_token"]')?.content || '';
		const body = new URLSearchParams();
		if (args) {
			for (const k of Object.keys(args)) {
				const v = args[k];
				body.append(k, typeof v === 'object' ? JSON.stringify(v) : (v ?? ''));
			}
		}
		const res = await fetch('/api/method/' + method, {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				'X-Frappe-CSRF-Token': csrf,
				'X-Requested-With': 'XMLHttpRequest',
				'Content-Type': 'application/x-www-form-urlencoded',
			},
			body: body.toString(),
		});
		let data = null;
		try { data = await res.json(); } catch (e) {}
		if (!res.ok) {
			const msg = data?._server_messages
				? JSON.parse(data._server_messages).map(m => {
					try { return JSON.parse(m).message; } catch (e) { return m; }
				  }).join(' · ')
				: (data?.exception || 'Error ' + res.status);
			throw new Error(msg);
		}
		return data.message;
	}

	// ---------- Toast ----------
	function toast(msg, type) {
		const existing = document.querySelector('.rd-toast');
		if (existing) existing.remove();
		const t = document.createElement('div');
		t.className = 'rd-toast' + (type ? ' rd-' + type : '');
		t.textContent = msg;
		document.body.appendChild(t);
		requestAnimationFrame(() => t.classList.add('rd-visible'));
		setTimeout(() => {
			t.classList.remove('rd-visible');
			setTimeout(() => t.remove(), 250);
		}, type === 'error' ? 5000 : 2500);
	}

	// ---------- Modal ----------
	function modal(opts) {
		// opts: {title, bodyHtml, onConfirm, confirmText, cancelText, danger}
		const back = document.createElement('div');
		back.className = 'rd-modal-backdrop';
		back.innerHTML = `
			<div class="rd-modal" role="dialog" aria-modal="true">
				<div class="rd-modal-head">
					<div class="rd-modal-title">${escapeHtml(opts.title || '')}</div>
					<button class="rd-modal-close" type="button" aria-label="Cerrar">
						<i data-lucide="x"></i>
					</button>
				</div>
				<div class="rd-modal-body">${opts.bodyHtml || ''}</div>
				<div class="rd-modal-actions">
					<button class="rd-btn rd-btn-secondary" data-act="cancel">${escapeHtml(opts.cancelText || 'Cancelar')}</button>
					<button class="rd-btn ${opts.danger ? 'rd-btn-danger' : ''}" data-act="ok">${escapeHtml(opts.confirmText || 'Aceptar')}</button>
				</div>
			</div>
		`;
		document.body.appendChild(back);
		if (window.lucide) lucide.createIcons();
		requestAnimationFrame(() => back.classList.add('rd-visible'));

		function close() {
			back.classList.remove('rd-visible');
			setTimeout(() => back.remove(), 200);
		}

		back.addEventListener('click', function (e) {
			if (e.target === back) close();
		});
		back.querySelector('.rd-modal-close').addEventListener('click', close);
		back.querySelector('[data-act=cancel]').addEventListener('click', close);
		back.querySelector('[data-act=ok]').addEventListener('click', async function () {
			if (!opts.onConfirm) return close();
			try {
				const ok = await opts.onConfirm(back);
				if (ok !== false) close();
			} catch (e) {
				toast(e.message || 'Error', 'error');
			}
		});

		return { close, root: back };
	}

	function escapeHtml(s) {
		if (s == null) return '';
		return String(s).replace(/[&<>"']/g, c => ({
			'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
		})[c]);
	}

	// ---------- Namespace ----------
	window.Radar = {
		api: apiCall,
		toast: toast,
		modal: modal,
		escapeHtml: escapeHtml,
	};

	// ---------- Dashboard ----------
	const MESES_C = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
	function _fmtNum(n) {
		n = n || 0;
		if (n >= 1000000) return (n/1000000).toFixed(1).replace(/\.0$/,'') + 'M';
		if (n >= 1000)    return (n/1000).toFixed(1).replace(/\.0$/,'') + 'k';
		return n.toLocaleString('es-PE');
	}
	window.RadarDash = {
		async init() {
			try {
				const c = await apiCall('marketinghub.www.radar.index.obtener_contadores');
				document.querySelectorAll('#rd-stats [data-key]').forEach(el => {
					const key = el.dataset.key;
					el.textContent = (c[key] ?? 0).toLocaleString('es-PE');
				});
			} catch (e) {
				console.error(e);
				toast('No se pudieron cargar los contadores: ' + e.message, 'error');
			}
			this.renderCharts();
		},

		async renderCharts() {
			await Promise.all([
				this._renderTimeline(),
				this._renderTopVirales(),
				this._renderHeatmap(),
			]);
		},

		async _renderTimeline() {
			if (typeof Chart === 'undefined') return;
			try {
				const data = await apiCall('marketinghub.www.radar.index.obtener_timeline_virales',
				                           {semanas: 12, tier_orden_max: 5});
				this._chart('chart-timeline', {
					type: 'line',
					data: { labels: data.labels, datasets: data.datasets },
					options: {
						responsive:true, maintainAspectRatio:false,
						plugins:{
							legend:{position:'bottom', labels:{boxWidth:12, font:{size:11}}},
							tooltip:{callbacks:{title:(items) => 'Semana del ' + items[0].label}},
						},
						scales:{
							y:{beginAtZero:true, ticks:{stepSize:1, precision:0}, title:{display:true,text:'Virales por semana'}},
							x:{ticks:{font:{size:10}}},
						},
					},
				});
			} catch(e) { console.error('timeline:', e); }
		},

		async _renderTopVirales() {
			const cont = document.getElementById('rd-top-list');
			if (!cont) return;
			try {
				const posts = await apiCall('marketinghub.www.radar.index.obtener_top_virales',
				                             {limite: 10, dias: 30});
				if (!posts.length) {
					cont.innerHTML = '<div style="text-align:center;color:var(--muted);padding:30px;font-size:12px;">Sin publicaciones en el último mes.</div>';
					return;
				}
				cont.innerHTML = posts.map((p, i) => {
					const rank = i + 1;
					const fecha = p.fecha_publicacion ? p.fecha_publicacion.split('-').reverse().slice(0,2).join('/') : '';
					return `
						<a class="rd-top-item rank-${rank}" href="${escapeHtml(p.url_publicacion || '#')}" target="_blank" rel="noopener">
							<span class="rd-top-rank">${rank}</span>
							<div class="rd-top-color" style="background:${escapeHtml(p.color)}"></div>
							<div class="rd-top-body">
								<div class="rd-top-hook">${escapeHtml(p.titulo_hook || '(sin título)')}</div>
								<div class="rd-top-meta">${escapeHtml(p.competidor || '')} · ${escapeHtml(p.plataforma || '')} · ${fecha}</div>
							</div>
							<div class="rd-top-metrics">
								<b>${_fmtNum(p.vistas_actual)}</b>
								${(p.engagement_pct || 0).toFixed(1)}% eng
							</div>
						</a>`;
				}).join('');
			} catch(e) { console.error('top:', e); }
		},

		async _renderHeatmap() {
			const cont = document.getElementById('rd-heatmap-wrap');
			if (!cont) return;
			try {
				const data = await apiCall('marketinghub.www.radar.index.obtener_heatmap_semana', {semanas: 12});
				const total = data.matriz.reduce((a, fila) => a + fila.reduce((b, x) => b + x, 0), 0);
				if (!total) {
					cont.innerHTML = '<div class="rd-heatmap-empty">Sin datos suficientes.</div>';
					return;
				}
				const heatCls = (v) => {
					if (!v || !data.max) return '';
					const p = v / data.max;
					if (p >= 0.75) return 'h4';
					if (p >= 0.5)  return 'h3';
					if (p >= 0.25) return 'h2';
					return 'h1';
				};
				const n = data.labels_semana.length;
				let html = `<div class="rd-heatmap" style="--_n:${n};">`;
				// header
				html += `<div class="rd-heatmap-header" style="--_n:${n};">
					<div></div>
					${data.labels_semana.map(l => `<div class="lbl-sem">${l}</div>`).join('')}
				</div>`;
				// filas por día
				data.labels_dia.forEach((dow, i) => {
					html += `<div class="rd-heatmap-row" style="--_n:${n};">
						<div class="rd-heatmap-dow">${dow}</div>
						${data.matriz[i].map(v => `<div class="rd-heatmap-cell ${heatCls(v)}" title="${v} posts">${v || ''}</div>`).join('')}
					</div>`;
				});
				html += '</div>';
				cont.innerHTML = html;
			} catch(e) { console.error('heatmap:', e); }
		},

		_chart(canvasId, config) {
			const canvas = document.getElementById(canvasId);
			if (!canvas) return;
			if (canvas._chartInstance) canvas._chartInstance.destroy();
			canvas._chartInstance = new Chart(canvas, config);
		},

		_chart(canvasId, config) {
			const canvas = document.getElementById(canvasId);
			if (!canvas) return;
			// destruir chart previo si existe
			if (canvas._chartInstance) canvas._chartInstance.destroy();
			canvas._chartInstance = new Chart(canvas, config);
		},
	};
})();
