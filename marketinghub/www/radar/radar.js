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
		_topRangeDias: 30,

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
			this._wireTopRange();
			await Promise.all([
				this._renderTopVirales(),
				this._renderViralesPorComp(),
				this._renderDiasSemana(),
			]);
		},

		_wireTopRange() {
			document.querySelectorAll('#rd-top-range button').forEach(btn => {
				btn.addEventListener('click', async () => {
					document.querySelectorAll('#rd-top-range button').forEach(b => b.classList.remove('on'));
					btn.classList.add('on');
					this._topRangeDias = parseInt(btn.dataset.dias);
					await this._renderTopVirales();
				});
			});
		},

		async _renderTopVirales() {
			const cont = document.getElementById('rd-top-list');
			if (!cont) return;
			cont.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:16px;font-size:12px;">Cargando…</div>';
			try {
				const posts = await apiCall('marketinghub.www.radar.index.obtener_top_virales',
				                             {limite: 10, dias: this._topRangeDias});
				if (!posts.length) {
					const txt = this._topRangeDias === 7 ? 'esta semana' : 'este mes';
					cont.innerHTML = `<div style="text-align:center;color:#9ca3af;padding:20px;font-size:12px;">Sin publicaciones ${txt}.</div>`;
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

		async _renderViralesPorComp() {
			const cont = document.getElementById('rd-vpc');
			if (!cont) return;
			try {
				const rows = await apiCall('marketinghub.www.radar.index.obtener_virales_por_competidor', {dias: 30});
				if (!rows.length) {
					cont.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:16px;font-size:12px;">Sin virales en el último mes.</div>';
					return;
				}
				const maxTotal = Math.max(...rows.map(r => r.total)) || 1;
				cont.innerHTML = rows.map(r => {
					const pctV = (r.virales / maxTotal) * 100;
					const pctC = (r.casi_virales / maxTotal) * 100;
					return `
						<div class="row">
							<div class="name">
								<span class="dot" style="background:${escapeHtml(r.color)};"></span>
								<span title="${escapeHtml(r.competidor)}">${escapeHtml(r.competidor)}</span>
							</div>
							<div class="bar">
								${r.virales      ? `<div class="seg seg-v" style="width:${pctV}%;" title="${r.virales} virales">${r.virales >= 2 ? r.virales : ''}</div>` : ''}
								${r.casi_virales ? `<div class="seg seg-c" style="width:${pctC}%;" title="${r.casi_virales} casi virales">${r.casi_virales >= 2 ? r.casi_virales : ''}</div>` : ''}
							</div>
							<div class="cnt">${r.total}</div>
						</div>`;
				}).join('');
			} catch(e) { console.error('vpc:', e); cont.innerHTML = ''; }
		},

		async _renderDiasSemana() {
			const cont = document.getElementById('rd-dow');
			if (!cont) return;
			try {
				const rows = await apiCall('marketinghub.www.radar.index.obtener_publicaciones_por_dia_semana', {dias: 90});
				const maxC = Math.max(...rows.map(r => r.count)) || 1;
				if (!rows.some(r => r.count)) {
					cont.innerHTML = '<div style="text-align:center;color:#9ca3af;padding:16px;font-size:12px;">Sin datos suficientes.</div>';
					return;
				}
				cont.innerHTML = rows.map(r => {
					const pct = Math.round((r.count / maxC) * 100);
					return `
						<div class="row">
							<div class="n">${escapeHtml(r.nombre)}</div>
							<div class="bar"><div style="width:${pct}%;"></div></div>
							<div class="c">${r.count}</div>
						</div>`;
				}).join('');
			} catch(e) { console.error('dow:', e); }
		},
	};
})();
