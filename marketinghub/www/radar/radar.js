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
				// KPIs arriba
				document.querySelectorAll('[data-kpi]').forEach(el => {
					const key = el.dataset.kpi;
					el.textContent = (c[key] ?? 0).toLocaleString('es-PE');
				});
				// Counts en sidebar
				document.querySelectorAll('[data-count]').forEach(el => {
					const k = el.dataset.count;
					const v = c[k];
					if (v != null && v > 0) el.textContent = v;
					else el.textContent = '';
				});
				// CTA "Analizar N"
				const cta = document.getElementById('rad-cta-analizar');
				if (cta && c.nuevos > 0) cta.textContent = `Analizar ${c.nuevos}`;
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
			document.querySelectorAll('#rad-top-range .rad-seg__item').forEach(btn => {
				btn.addEventListener('click', async () => {
					document.querySelectorAll('#rad-top-range .rad-seg__item').forEach(b => b.classList.remove('is-on'));
					btn.classList.add('is-on');
					this._topRangeDias = parseInt(btn.dataset.dias);
					await this._renderTopVirales();
				});
			});
		},

		async _renderTopVirales() {
			const cont = document.getElementById('rad-top-list');
			const foot = document.getElementById('rad-top-foot');
			if (!cont) return;
			cont.innerHTML = '<div style="text-align:center;color:var(--muted);padding:16px;font-size:12px;">Cargando…</div>';
			try {
				const posts = await apiCall('marketinghub.www.radar.index.obtener_top_virales',
				                             {limite: 10, dias: this._topRangeDias});
				if (!posts.length) {
					const txt = this._topRangeDias === 7 ? 'esta semana' : 'este mes';
					cont.innerHTML = `<div style="text-align:center;color:var(--muted);padding:20px;font-size:12px;">Sin publicaciones ${txt}.</div>`;
					if (foot) foot.textContent = '';
					return;
				}
				cont.innerHTML = posts.map((p, i) => {
					const rank = i + 1;
					const rankMod = rank <= 3 ? 'rad-viral__rank--top' : '';
					const eng = p.engagement_pct || 0;
					const engMod = eng >= 2 ? 'rad-viral__eng--high' : '';
					// bar por tier
					let barMod = '';
					if (p.tier_orden && p.tier_orden <= 5) barMod = 'rad-viral__bar--viral';
					else if (p.tier_orden && p.tier_orden <= 7) barMod = 'rad-viral__bar--casi';
					const fecha = p.fecha_publicacion ? p.fecha_publicacion.split('-').reverse().slice(0,2).join('/') : '';
					return `
						<a class="rad-viral" href="${escapeHtml(p.url_publicacion || '#')}" target="_blank" rel="noopener">
							<span class="rad-viral__rank ${rankMod}">${rank}</span>
							<span class="rad-viral__bar ${barMod}"></span>
							<span class="rad-viral__text">
								<span class="rad-viral__title">${escapeHtml(p.titulo_hook || '(sin título)')}</span>
								<span class="rad-viral__meta">${escapeHtml(p.competidor || '')} · ${escapeHtml(p.plataforma || '')} · ${fecha}</span>
							</span>
							<span class="rad-viral__nums">
								<span class="rad-viral__views">${_fmtNum(p.vistas_actual)}</span>
								<span class="rad-viral__eng ${engMod}">${eng.toFixed(1)}% eng</span>
							</span>
						</a>`;
				}).join('');
				if (foot) {
					const rangoTxt = this._topRangeDias === 7 ? 'semana' : 'mes';
					foot.textContent = `${posts.length} publicaciones · orden por vistas · ${rangoTxt}`;
				}
			} catch(e) { console.error('top:', e); }
		},

		async _renderViralesPorComp() {
			const cont = document.getElementById('rad-vpc-body');
			if (!cont) return;
			try {
				const rows = await apiCall('marketinghub.www.radar.index.obtener_virales_por_competidor', {dias: 30});
				if (!rows.length) {
					cont.innerHTML = '<div style="text-align:center;color:var(--muted);padding:16px;font-size:12px;">Sin publicaciones en el último mes.</div>';
					return;
				}
				const maxTotal = Math.max(...rows.map(r => r.total)) || 1;
				let html = '';
				rows.forEach((r, i) => {
					const pctV = (r.virales      / maxTotal) * 100;
					const pctC = (r.casi_virales / maxTotal) * 100;
					const dotMod = i === 1 ? 'rad-comp__dot--accent' : '';
					html += `
						<div class="rad-comp">
							<span class="rad-comp__name"><span class="rad-comp__dot ${dotMod}" style="background:${escapeHtml(r.color || '')}"></span>${escapeHtml(r.competidor || '')}</span>
							<span class="rad-comp__track">
								${r.virales      ? `<span class="rad-comp__viral" style="width:${pctV}%">${r.virales >= 2 ? r.virales : ''}</span>` : ''}
								${r.casi_virales ? `<span class="rad-comp__casi"  style="width:${pctC}%">${r.casi_virales >= 2 ? r.casi_virales : ''}</span>` : ''}
							</span>
							<span class="rad-comp__sum">${r.virales} · ${r.casi_virales} · ${r.bajo}</span>
						</div>
					`;
				});
				html += `
					<div class="rad-legend">
						<span class="rad-legend__item"><span class="rad-legend__sw" style="background:var(--top)"></span>Viral (Dragón · Cetro · Hachón)</span>
						<span class="rad-legend__item"><span class="rad-legend__sw" style="background:var(--accent-soft)"></span>Casi viral (tier 6-7)</span>
						<span class="rad-legend__item"><span class="rad-legend__sw" style="background:var(--raise)"></span>Bajo (tier 8-10)</span>
					</div>`;
				cont.innerHTML = html;
			} catch(e) { console.error('vpc:', e); cont.innerHTML = '<div style="text-align:center;color:#dc2626;padding:16px;font-size:12px;">Error: ' + escapeHtml(e.message) + '</div>'; }
		},

		async _renderDiasSemana() {
			const cont = document.getElementById('rad-dow-body');
			if (!cont) return;
			try {
				const rows = await apiCall('marketinghub.www.radar.index.obtener_publicaciones_por_dia_semana', {dias: 90});
				if (!rows.some(r => r.count)) {
					cont.innerHTML = '<div style="text-align:center;color:var(--muted);padding:16px;font-size:12px;">Sin datos suficientes.</div>';
					return;
				}
				const maxC = Math.max(...rows.map(r => r.count)) || 1;
				const top1 = rows[0]?.nombre;
				const top2 = rows[1]?.nombre;
				let html = '';
				rows.forEach(r => {
					const pct = Math.round((r.count / maxC) * 100);
					const isTop = r.count === maxC && r.count > 0;
					const isZero = r.count === 0;
					const lblMod = isTop ? 'rad-day__label--top' : (isZero ? 'rad-day__label--zero' : '');
					const fillMod = isTop ? 'rad-day__fill--top' : '';
					html += `
						<div class="rad-day">
							<span class="rad-day__label ${lblMod}">${escapeHtml(r.nombre)}</span>
							<span class="rad-day__track"><span class="rad-day__fill ${fillMod}" style="width:${pct}%"></span></span>
							<span class="rad-day__n">${r.count}</span>
						</div>`;
				});
				if (top1 && top2 && rows[0].count > 0) {
					const pctTop = Math.round(((rows[0].count + (rows[1]?.count || 0)) / rows.reduce((s,x)=>s+x.count,0)) * 100);
					html += `<p class="rad-note">El ${pctTop}% de las publicaciones salen <strong>${top1.toLowerCase()} y ${top2.toLowerCase()}</strong>.</p>`;
				}
				cont.innerHTML = html;
			} catch(e) { console.error('dow:', e); cont.innerHTML = '<div style="text-align:center;color:#dc2626;padding:16px;font-size:12px;">Error: ' + escapeHtml(e.message) + '</div>'; }
		},
	};
})();
