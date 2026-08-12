/* ============================================
   Radar Ads Library — Retro-OS design
   ============================================ */
(function () {
	'use strict';

	let CAN_EDIT = false;
	let ADS = [];
	let PRESION = null;
	let SORT = { campo: 'dias_activo', dir: 'desc' };
	let FILTROS = {
		q: '', competidor: '', formato: '', etiqueta: '',
		activos: true, dias_min: null,
	};

	const BADGE_MODIFIER = {
		'Nuevo':       '',
		'Fresco':      'ads-badge--fresh',
		'Test scale':  'ads-badge--test',
		'Ganador':     'ads-badge--top',
		'Ganador top': 'ads-badge--top',
		'Pausado':     'ads-badge--paused',
	};
	const BADGE_LBL = {
		'Nuevo':       'Nuevo',
		'Fresco':      'Fresco',
		'Test scale':  'Test scale',
		'Ganador':     'Ganador',
		'Ganador top': 'Ganador top',
		'Pausado':     'Pausado',
	};

	function _esc(s) {
		if (s == null) return '';
		return String(s).replace(/[&<>"']/g, c => ({
			'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
		})[c]);
	}
	function _fmtNum(n) {
		n = n || 0;
		if (n >= 1000000) return (n/1000000).toFixed(1).replace(/\.0$/,'') + 'M';
		if (n >= 1000)    return (n/1000).toFixed(1).replace(/\.0$/,'') + 'k';
		return n.toLocaleString('es-PE');
	}
	function _fmtDDMMYY(iso) {
		if (!iso) return '—';
		const p = String(iso).split('-');
		if (p.length < 3) return iso;
		return `${p[2]}/${p[1]}/${p[0].slice(2)}`;
	}
	function _abbrev(url) {
		if (!url) return '';
		try {
			const u = new URL(url);
			const path = u.pathname.replace(/\/$/, '');
			const parts = path.split('/').filter(Boolean);
			return parts[parts.length - 1] || u.hostname;
		} catch { return String(url).substring(0, 30); }
	}
	function _iconFormato(f) {
		if (f === 'Video') return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6.5h11v11H4z M15 10.5l5-3v9l-5-3z"/></svg>';
		if (f === 'Imagen') return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5.5h16v13H4z M4 15l4.5-4.5 5 5 M14.5 12 20 17.5 M15.5 9h.01"/></svg>';
		if (f === 'Carrusel') return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 5.5h8v13H8z M5.5 8v8 M18.5 8v8"/></svg>';
		return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="7"/></svg>';
	}
	function _iconLink() {
		return '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M14 5h5v5 M19 5l-8 8 M18 14v5H5V6h5"/></svg>';
	}
	function _iconVer() {
		return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z M12 9.4a2.6 2.6 0 1 0 0 5.2 2.6 2.6 0 0 0 0-5.2z"/></svg>';
	}
	function _iconGuion() {
		return '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20l1-4 10.5-10.5 3 3-10.5 10.5z M14.5 6.5l3 3"/></svg>';
	}

	// ---------- Cargar ----------
	async function cargar() {
		try {
			const [ads, presion, comps] = await Promise.all([
				Radar.api('marketinghub.www.radar.ads.index.listar'),
				Radar.api('marketinghub.www.radar.ads.index.obtener_presion'),
				Radar.api('marketinghub.www.radar.ads.index.obtener_competidores'),
			]);
			ADS = ads || [];
			PRESION = presion || {};
			renderKPIs();
			llenarCompetidoresSelect(comps);
			renderTabla();
		} catch (e) {
			Radar.toast('Error cargando ads: ' + e.message, 'error');
			const body = document.getElementById('ads-body');
			if (body) body.innerHTML =
				`<div class="ads-empty-inline"><div class="t">Error</div><div>${_esc(e.message)}</div></div>`;
		}
	}

	function llenarCompetidoresSelect(comps) {
		const sel = document.getElementById('ads-f-comp');
		if (!sel) return;
		sel.innerHTML = '<option value="">Todos los competidores</option>' +
			(comps || []).map(c =>
				`<option value="${_esc(c.name)}">${_esc(c.nombre_comercial || c.name)}</option>`
			).join('');
	}

	// ---------- KPIs ----------
	function renderKPIs() {
		const box = document.getElementById('ads-kpis');
		if (!box) return;
		if (!PRESION || !PRESION.por_competidor || !PRESION.por_competidor.length) {
			box.innerHTML = `<div class="ads-empty-inline"><div class="t">Sin ads aún</div><div>Corre "Actualizar" para traerlos de Meta Ad Library.</div></div>`;
			return;
		}
		const t = PRESION.totales || {};
		let html = '';
		PRESION.por_competidor.forEach(c => {
			const isActive = FILTROS.competidor === c.competidor;
			html += `
				<div class="ads-kpi ${isActive ? 'is-active' : ''}" data-kpi="comp" data-val="${_esc(c.competidor)}">
					<span class="ads-kpi__label">
						<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4.5h7l9 9-6.5 6.5-9-9z M7.6 8.1h.01"/></svg>
						${_esc(c.competidor)}
					</span>
					<span class="ads-kpi__value">${c.activos}</span>
					<span class="ads-kpi__hint">ads activos · ${c.ganadores} ganadores · ${c.nuevos} nuevos</span>
				</div>
			`;
		});
		html += `
			<div class="ads-kpi ads-kpi--warn ${FILTROS.dias_min === 30 ? 'is-active' : ''}" data-kpi="ganadores">
				<span class="ads-kpi__label">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 4.5h10v4a5 5 0 0 1-10 0z M7 6H4.5v1.5A3 3 0 0 0 7 10.4 M17 6h2.5v1.5A3 3 0 0 1 17 10.4 M12 13.5v3 M8.5 19.5h7"/></svg>
					Ganadores (30d+)
				</span>
				<span class="ads-kpi__value">${t.ganadores || 0}</span>
				<span class="ads-kpi__hint">de ${t.activos || 0} activos</span>
			</div>
			<div class="ads-kpi ads-kpi--accent ${FILTROS.etiqueta === 'Nuevo' ? 'is-active' : ''}" data-kpi="nuevos">
				<span class="ads-kpi__label">
					<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5v4 M12 16.5v4 M3.5 12h4 M16.5 12h4 M6 6l2.5 2.5 M15.5 15.5 18 18 M18 6l-2.5 2.5 M8.5 15.5 6 18"/></svg>
					Nuevos esta semana
				</span>
				<span class="ads-kpi__value">${t.nuevos || 0}</span>
				<span class="ads-kpi__hint">creados hace menos de 7 días</span>
			</div>
		`;
		box.innerHTML = html;
		// Wire KPI clicks
		box.querySelectorAll('.ads-kpi').forEach(el => {
			el.addEventListener('click', function () {
				const kpi = el.dataset.kpi;
				if (kpi === 'comp') {
					const val = el.dataset.val;
					FILTROS.competidor = (FILTROS.competidor === val) ? '' : val;
					const sel = document.getElementById('ads-f-comp');
					if (sel) sel.value = FILTROS.competidor;
				} else if (kpi === 'ganadores') {
					FILTROS.dias_min = (FILTROS.dias_min === 30) ? null : 30;
					document.getElementById('ads-t-30d')?.classList.toggle('is-on', FILTROS.dias_min === 30);
				} else if (kpi === 'nuevos') {
					FILTROS.etiqueta = (FILTROS.etiqueta === 'Nuevo') ? '' : 'Nuevo';
					const sel = document.getElementById('ads-f-etiqueta');
					if (sel) sel.value = FILTROS.etiqueta;
				}
				renderKPIs();
				renderTabla();
			});
		});
	}

	// ---------- Tabla ----------
	function filtrar() {
		let lista = ADS.slice();
		if (FILTROS.q) {
			const q = FILTROS.q.toLowerCase();
			lista = lista.filter(a => (a.copy_texto || '').toLowerCase().includes(q));
		}
		if (FILTROS.competidor) lista = lista.filter(a => a.competidor === FILTROS.competidor);
		if (FILTROS.formato)    lista = lista.filter(a => a.formato === FILTROS.formato);
		if (FILTROS.etiqueta)   lista = lista.filter(a => a.etiqueta_ganador === FILTROS.etiqueta);
		if (FILTROS.activos)    lista = lista.filter(a => a.esta_activo);
		if (FILTROS.dias_min)   lista = lista.filter(a => (a.dias_activo || 0) >= FILTROS.dias_min);
		// Ordenar
		const {campo, dir} = SORT;
		const mult = dir === 'asc' ? 1 : -1;
		lista.sort((a, b) => {
			let va = a[campo], vb = b[campo];
			if (va == null) va = campo === 'dias_activo' ? 0 : '';
			if (vb == null) vb = campo === 'dias_activo' ? 0 : '';
			if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * mult;
			return String(va).localeCompare(String(vb)) * mult;
		});
		return lista;
	}

	function renderTabla() {
		const body = document.getElementById('ads-body');
		const summary = document.getElementById('ads-summary');
		if (!body) return;
		const lista = filtrar();

		// Summary "N ads · Xd promedio"
		const prom = lista.length
			? Math.round(lista.reduce((s,x)=>s+(x.dias_activo||0),0)/lista.length)
			: 0;
		if (summary) {
			summary.textContent = lista.length
				? `${lista.length} ad${lista.length===1?'':'s'} · ${prom}d promedio`
				: '0 ads';
		}

		// Sort indicators
		document.querySelectorAll('.ads-head__cell--sortable').forEach(el => {
			el.classList.toggle('is-sorted', el.dataset.sort === SORT.campo);
			// remover flechas viejas
			el.querySelectorAll('.ads-sort-dir').forEach(x => x.remove());
			if (el.dataset.sort === SORT.campo) {
				el.insertAdjacentHTML('beforeend', ` <span class="ads-sort-dir">${SORT.dir === 'asc' ? '↑' : '↓'}</span>`);
			}
		});

		if (!lista.length) {
			body.innerHTML = `<div class="ads-empty-inline">
				<div class="t">Sin resultados</div>
				<div>Ningún anuncio coincide con los filtros.</div>
				<button class="ads-btn ads-btn--primary" onclick="RadarAds.limpiar()" type="button">Limpiar filtros</button>
			</div>`;
			return;
		}

		body.innerHTML = lista.map(a => renderRow(a)).join('');
	}

	function renderRow(a) {
		const dias = a.dias_activo || 0;
		const diasMod = dias >= 30 ? 'ads-days--long' : '';
		const brand = (a.competidor || '?').charAt(0).toUpperCase();
		const badgeMod = BADGE_MODIFIER[a.etiqueta_ganador] || '';
		const badgeLbl = BADGE_LBL[a.etiqueta_ganador] || a.etiqueta_ganador || 'Nuevo';
		const liveTxt = a.esta_activo ? 'activo' : 'pausado';
		const liveMod = a.esta_activo ? '' : 'ads-live--off';
		const copyText = (a.copy_texto || '(sin texto)').replace(/\n/g,' ').substring(0, 200);
		const isPlaceholder = /^\s*\{\{.*\}\}\s*$/.test(a.copy_texto || '');
		const platsShort = (a.plataformas || '').split(',').filter(Boolean).map(p =>
			`<span class="ads-plat" title="${_esc(p.trim())}">${_esc(p.trim().substring(0,3))}</span>`
		).join('');

		return `
			<div class="ads-row ads-body-row" data-name="${_esc(a.name)}">
				<div class="ads-days ${diasMod}"><span class="ads-days__n">${dias}</span><span class="ads-days__u">d</span></div>
				<div class="ads-state">
					<span class="ads-badge ${badgeMod}">${_esc(badgeLbl)}</span>
					<span class="ads-live ${liveMod}">${liveTxt}</span>
				</div>
				<div class="ads-brand"><span class="ads-brand__ini">${brand}</span><span class="ads-brand__name">${_esc(a.competidor || '')}</span></div>
				<div class="ads-format">${_iconFormato(a.formato)}<span>${_esc(a.formato || '—')}</span></div>
				<div class="ads-cell ads-cell--date">${_fmtDDMMYY(a.fecha_inicio)}</div>
				<a class="ads-copy ${isPlaceholder ? 'ads-copy--placeholder' : ''}" href="#" data-act="ver" data-name="${_esc(a.name)}" title="${_esc(a.copy_texto || '')}">
					<span>${_esc(copyText)}</span>
					${_iconLink()}
				</a>
				<div class="ads-cell">${a.cta_type ? `<span class="ads-cta">${_esc(a.cta_type)}</span>` : ''}</div>
				<div class="ads-cell">${a.landing_url ? `<a class="ads-landing" href="${_esc(a.landing_url)}" target="_blank" rel="noopener" title="${_esc(a.landing_url)}">${_esc(_abbrev(a.landing_url))}</a>` : ''}</div>
				<div class="ads-plats">${platsShort}</div>
				<div class="ads-cell--actions">
					<button class="ads-btn ads-btn--sm" data-act="ver" data-name="${_esc(a.name)}" type="button">${_iconVer()} Ver</button>
					${CAN_EDIT ? `<button class="ads-btn ads-btn--sm ads-btn--primary" data-act="guion" data-name="${_esc(a.name)}" type="button">${_iconGuion()} Guion</button>` : ''}
				</div>
			</div>`;
	}

	// ---------- Modal detalle ----------
	async function abrirDetalle(name) {
		try {
			const doc = await Radar.api('marketinghub.www.radar.ads.index.obtener_ad', {name});
			const media = doc.video_hd_url || doc.video_sd_url
				? `<video controls playsinline poster="${_esc(doc.imagen_preview_url || '')}">
						<source src="${_esc(doc.video_hd_url || doc.video_sd_url)}">
					</video>`
				: (doc.imagen_preview_url
					? `<img src="${_esc(doc.imagen_preview_url)}" alt="ad">`
					: `<div class="noplay">Sin media disponible</div>`);
			const dlUrl = doc.video_hd_url || doc.video_sd_url || doc.imagen_preview_url;
			const bodyHtml = `
				<div class="ads-modal-media">${media}</div>
				<div class="ads-modal-copy">${_esc(doc.copy_texto || '(sin texto)')}</div>
				<div class="ads-props">
					<div class="ads-prop"><span class="ads-prop__k">Marca</span><span class="ads-prop__v">${_esc(doc.competidor || '—')}</span></div>
					<div class="ads-prop"><span class="ads-prop__k">Página FB</span><span class="ads-prop__v">${_esc(doc.page_name || '—')}${doc.page_like_count ? ` <span style="color:var(--muted);">(${_fmtNum(doc.page_like_count)} likes)</span>` : ''}</span></div>
					<div class="ads-prop"><span class="ads-prop__k">Estado</span><span class="ads-prop__v">${_esc(BADGE_LBL[doc.etiqueta_ganador] || '—')} · ${doc.esta_activo ? 'activo' : 'pausado'}</span></div>
					<div class="ads-prop"><span class="ads-prop__k">Días activo</span><span class="ads-prop__v">${doc.dias_activo || 0} d</span></div>
					<div class="ads-prop"><span class="ads-prop__k">Publicado</span><span class="ads-prop__v">${_fmtDDMMYY(doc.fecha_inicio)}</span></div>
					${doc.fecha_fin ? `<div class="ads-prop"><span class="ads-prop__k">Fin (Meta)</span><span class="ads-prop__v">${_fmtDDMMYY(doc.fecha_fin)}</span></div>` : ''}
					<div class="ads-prop"><span class="ads-prop__k">Formato</span><span class="ads-prop__v">${_esc(doc.formato || '—')}</span></div>
					<div class="ads-prop"><span class="ads-prop__k">CTA</span><span class="ads-prop__v">${_esc(doc.cta_text || doc.cta_type || '—')}${doc.cta_text && doc.cta_type ? ` <span style="color:var(--faint);font-size:11px;">[${_esc(doc.cta_type)}]</span>` : ''}</span></div>
					<div class="ads-prop"><span class="ads-prop__k">Plataformas</span><span class="ads-prop__v">${_esc((doc.plataformas || '').split(',').join(' · ') || '—')}</span></div>
					${doc.landing_url ? `<div class="ads-prop"><span class="ads-prop__k">Landing</span><span class="ads-prop__v"><a href="${_esc(doc.landing_url)}" target="_blank" style="color:var(--accent);">Ver landing</a></span></div>` : ''}
				</div>
				<div style="margin-top:16px;display:flex;gap:8px;flex-wrap:wrap;">
					${dlUrl ? `<a class="rd-btn rd-btn-secondary" href="${_esc(dlUrl)}" target="_blank" download>Descargar media</a>` : ''}
					<a class="rd-btn rd-btn-secondary" href="https://www.facebook.com/ads/library/?id=${_esc(doc.ad_archive_id)}" target="_blank">Ver en Ad Library</a>
				</div>
			`;
			Radar.modal({
				title: `Anuncio · ${doc.competidor || ''}`,
				bodyHtml: bodyHtml,
				confirmText: CAN_EDIT ? 'Crear guion' : 'Cerrar',
				cancelText: 'Cerrar',
				onConfirm: async () => {
					if (!CAN_EDIT) return true;
					await hacerGuion(doc.name);
					return true;
				},
			});
		} catch (e) {
			Radar.toast('Error abriendo ad: ' + e.message, 'error');
		}
	}

	async function hacerGuion(name) {
		try {
			const r = await Radar.api('marketinghub.www.radar.ads.index.crear_guion_desde_ad', {ad_name: name});
			Radar.toast('Guión creado', 'success');
			window.location.href = r.url;
		} catch (e) {
			Radar.toast(e.message || 'Error', 'error');
		}
	}

	// ---------- Actualizar (scrape) ----------
	async function actualizar() {
		if (!CAN_EDIT) { Radar.toast('Sin permisos', 'error'); return; }
		const btn = document.getElementById('ads-refresh');
		const orig = btn.innerHTML;
		btn.disabled = true; btn.innerHTML = '<span>Actualizando…</span>';
		try {
			const r = await Radar.api('marketinghub.api.radar_ads_scraper.ejecutar_scrape_ads_ahora');
			const s = r.stats || {};
			Radar.toast(`${s.insert || 0} nuevos · ${s.update || 0} actualizados · ${s.pausados || 0} pausados`, 'success');
			await cargar();
		} catch (e) {
			Radar.toast('Error: ' + e.message, 'error');
		} finally {
			btn.disabled = false; btn.innerHTML = orig;
		}
	}

	// ---------- CSV ----------
	function csv() {
		const lista = filtrar();
		if (!lista.length) { Radar.toast('Sin data', 'error'); return; }
		const cols = [
			['dias_activo','Dias activo'], ['etiqueta_ganador','Etiqueta'],
			['esta_activo','Activo'], ['competidor','Competidor'],
			['fecha_inicio','Inicio'], ['fecha_pausado','Pausado'],
			['formato','Formato'], ['cta_type','CTA'],
			['copy_texto','Copy'], ['landing_url','Landing'],
			['plataformas','Plataformas'], ['n_variantes','Variantes'],
			['ad_archive_id','Ad ID'],
		];
		const esc = v => `"${String(v ?? '').replace(/"/g,'""').replace(/\n/g,' ')}"`;
		const header = cols.map(c => esc(c[1])).join(',');
		const rows = lista.map(a => cols.map(c => esc(a[c[0]])).join(','));
		const stamp = new Date().toISOString().slice(0,10);
		const blob = new Blob(['﻿' + header + '\n' + rows.join('\n')], {type: 'text/csv;charset=utf-8'});
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url; a.download = `radar-ads-${stamp}.csv`;
		document.body.appendChild(a); a.click(); a.remove();
		URL.revokeObjectURL(url);
		Radar.toast(`${lista.length} ads exportados`, 'success');
	}

	// ---------- Limpiar filtros ----------
	function limpiar() {
		FILTROS = { q: '', competidor: '', formato: '', etiqueta: '', activos: true, dias_min: null };
		document.getElementById('ads-f-search').value = '';
		document.getElementById('ads-f-comp').value = '';
		document.getElementById('ads-f-formato').value = '';
		document.getElementById('ads-f-etiqueta').value = '';
		document.getElementById('ads-t-30d').classList.remove('is-on');
		document.getElementById('ads-t-activos').classList.add('is-on');
		renderKPIs();
		renderTabla();
	}

	// ---------- Wire ----------
	function wire() {
		document.getElementById('ads-f-search').addEventListener('input', function () {
			FILTROS.q = this.value.trim(); renderTabla();
		});
		document.getElementById('ads-f-comp').addEventListener('change', function () {
			FILTROS.competidor = this.value; renderKPIs(); renderTabla();
		});
		document.getElementById('ads-f-formato').addEventListener('change', function () {
			FILTROS.formato = this.value; renderTabla();
		});
		document.getElementById('ads-f-etiqueta').addEventListener('change', function () {
			FILTROS.etiqueta = this.value; renderKPIs(); renderTabla();
		});
		document.getElementById('ads-t-30d').addEventListener('click', function () {
			this.classList.toggle('is-on');
			FILTROS.dias_min = this.classList.contains('is-on') ? 30 : null;
			renderKPIs(); renderTabla();
		});
		document.getElementById('ads-t-activos').addEventListener('click', function () {
			this.classList.toggle('is-on');
			FILTROS.activos = this.classList.contains('is-on');
			renderTabla();
		});
		document.getElementById('ads-limpiar').addEventListener('click', limpiar);
		document.getElementById('ads-csv').addEventListener('click', csv);
		document.getElementById('ads-refresh').addEventListener('click', actualizar);
		// Sort clicks
		document.querySelectorAll('.ads-head__cell--sortable').forEach(el => {
			el.addEventListener('click', function () {
				const c = el.dataset.sort;
				if (SORT.campo === c) SORT.dir = SORT.dir === 'asc' ? 'desc' : 'asc';
				else { SORT.campo = c; SORT.dir = 'desc'; }
				renderTabla();
			});
		});
		// Delegación en body: ver + guion
		document.getElementById('ads-body').addEventListener('click', function (e) {
			const el = e.target.closest('[data-act]');
			if (!el) return;
			e.preventDefault();
			const act = el.dataset.act;
			const name = el.dataset.name;
			if (act === 'ver') abrirDetalle(name);
			else if (act === 'guion') hacerGuion(name);
		});
	}

	// ---------- Namespace ----------
	window.RadarAds = {
		init(canEdit) {
			CAN_EDIT = !!canEdit;
			wire();
			cargar();
		},
		abrir: abrirDetalle,
		hacerGuion: hacerGuion,
		limpiar: limpiar,
	};
})();
