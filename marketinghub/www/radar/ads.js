/* ============================================
   Radar de Competencia — Ads Library
   ============================================ */
(function () {
	'use strict';

	let CAN_EDIT = false;
	let ADS = [];
	let SORT = { campo: 'dias_activo', dir: 'desc' };
	let FILTROS = {
		q: '', competidor: '', formato: '', etiqueta: '',
		activos: true, dias_min: null,
	};

	const BADGE_CLS = {
		'Nuevo':       'b-nuevo',
		'Fresco':      'b-fresco',
		'Test scale':  'b-test',
		'Ganador':     'b-ganador',
		'Ganador top': 'b-top',
		'Pausado':     'b-pausado',
	};
	const BADGE_LBL = {
		'Nuevo':       '🆕 Nuevo',
		'Fresco':      '🔥 Fresco',
		'Test scale':  '🔥🔥 Test scale',
		'Ganador':     '🔥🔥 Ganador',
		'Ganador top': '🔥🔥🔥 Ganador top',
		'Pausado':     '⛔ Pausado',
	};

	function _escape(s) {
		if (s == null) return '';
		return String(s).replace(/[&<>"']/g, c => ({
			'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
		})[c]);
	}
	function _fmtFecha(iso) {
		if (!iso) return '';
		return iso.split('-').reverse().slice(0,2).join('/') + '/' + iso.substr(2,2);
	}
	function _fmtDDMMYY(iso) {
		if (!iso) return '';
		const p = iso.split('-');
		return `${p[2]}/${p[1]}/${p[0].slice(2)}`;
	}
	function _abbrev(url) {
		if (!url) return '';
		try {
			const u = new URL(url);
			const path = u.pathname.replace(/\/$/, '');
			const parts = path.split('/').filter(Boolean);
			return parts[parts.length - 1] || u.hostname;
		} catch { return url.substring(0, 20); }
	}
	function _abbrevPlats(csv) {
		if (!csv) return '';
		return csv.split(',').map(p => p.trim().substring(0,3)).join('·');
	}
	function _formato_ico(f) {
		if (f === 'Video')    return '🎥';
		if (f === 'Imagen')   return '🖼';
		if (f === 'Carrusel') return '🎠';
		return '?';
	}

	// ---------- Cargar data ----------
	async function cargar() {
		try {
			const [ads, presion, comps] = await Promise.all([
				Radar.api('marketinghub.www.radar.ads.index.listar'),
				Radar.api('marketinghub.www.radar.ads.index.obtener_presion'),
				Radar.api('marketinghub.www.radar.ads.index.obtener_competidores'),
			]);
			ADS = ads || [];
			renderPresion(presion);
			llenarFiltroCompetidores(comps);
			renderTabla();
		} catch (e) {
			Radar.toast('Error cargando ads: ' + e.message, 'error');
			document.getElementById('rd-tbody').innerHTML =
				`<tr><td colspan="11" class="empty">Error: ${_escape(e.message)}</td></tr>`;
		}
	}

	function llenarFiltroCompetidores(comps) {
		const sel = document.getElementById('f-comp');
		if (!sel) return;
		sel.innerHTML = '<option value="">Todos los competidores</option>' +
			(comps || []).map(c =>
				`<option value="${_escape(c.name)}">${_escape(c.nombre_comercial || c.name)}</option>`
			).join('');
	}

	// ---------- Presión publicitaria ----------
	function renderPresion(data) {
		const box = document.getElementById('rd-pressure');
		if (!box) return;
		if (!data || !data.por_competidor || !data.por_competidor.length) {
			box.innerHTML = `<div class="card"><h4>Sin ads aún</h4><div class="sub">Corre "🔄 Actualizar" para traerlos de Meta Ad Library.</div></div>`;
			return;
		}
		const t = data.totales || {};
		let html = '';
		data.por_competidor.forEach(c => {
			html += `
				<div class="card">
					<h4><span class="dot" style="background:${_escape(c.color)};"></span> ${_escape(c.competidor)}</h4>
					<div class="n">${c.activos}</div>
					<div class="sub">ads activos · ${c.ganadores} ganadores · ${c.nuevos} nuevos</div>
				</div>
			`;
		});
		html += `
			<div class="card">
				<h4>🏆 Ganadores (30d+)</h4>
				<div class="n">${t.ganadores || 0}</div>
				<div class="sub">de ${t.activos || 0} activos</div>
			</div>
			<div class="card">
				<h4>🆕 Nuevos esta semana</h4>
				<div class="n">${t.nuevos || 0}</div>
				<div class="sub">creados hace menos de 7 días</div>
			</div>
		`;
		box.innerHTML = html;
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
		const tb = document.getElementById('rd-tbody');
		if (!tb) return;
		const lista = filtrar();
		document.getElementById('rd-count').textContent =
			`${lista.length} ${lista.length === 1 ? 'ad' : 'ads'} · ` +
			(lista.length
				? `${Math.round(lista.reduce((s,x)=>s+(x.dias_activo||0),0)/lista.length)}d promedio`
				: '');

		// Actualizar sort icons
		document.querySelectorAll('.ads-tbl th.sort').forEach(th => {
			th.classList.remove('sort-asc', 'sort-desc');
			if (th.dataset.sort === SORT.campo) {
				th.classList.add(SORT.dir === 'asc' ? 'sort-asc' : 'sort-desc');
			}
		});

		if (!lista.length) {
			tb.innerHTML = `<tr><td colspan="11" class="empty">
				<b>Sin ads con estos filtros.</b><br>
				<span style="font-size:11.5px;">Prueba quitar filtros o corre "🔄 Actualizar" arriba a la derecha.</span>
			</td></tr>`;
			return;
		}

		tb.innerHTML = lista.map(a => {
			const cls = (a.dias_activo || 0) >= 30 && a.esta_activo ? 'long-runner' : (a.esta_activo ? '' : 'pausado');
			const cls_badge = BADGE_CLS[a.etiqueta_ganador] || 'b-nuevo';
			const lbl_badge = BADGE_LBL[a.etiqueta_ganador] || a.etiqueta_ganador || '';
			const activo_dot = a.esta_activo ? '<span class="badge badge-active">●</span>' : '';
			const thumbCls = a.formato === 'Imagen' ? 'img' : (a.formato === 'Carrusel' ? 'car' : '');
			const thumbIco = a.formato === 'Imagen' ? '🖼' : (a.formato === 'Carrusel' ? '🎠' : '▶');
			const copy = (a.copy_texto || '').replace(/\n/g, ' ').substring(0, 200);
			return `
				<tr class="${cls}" data-name="${_escape(a.name)}">
					<td><span class="thumb ${thumbCls}" onclick="RadarAds.abrir('${_escape(a.name)}')">${thumbIco}</span></td>
					<td><span class="dias">${a.dias_activo || 0}d</span></td>
					<td><span class="badge ${cls_badge}">${lbl_badge}</span> ${activo_dot}</td>
					<td><span class="comp-tag"><span class="dot" style="background:${_escape(a.color)};"></span>${_escape(a.competidor || '')}</span></td>
					<td class="fmt">${thumbIco}</td>
					<td><span class="fecha">${_fmtDDMMYY(a.fecha_inicio)}</span></td>
					<td class="copy-cell" title="${_escape(a.copy_texto || '')}">${_escape(copy)}</td>
					<td>${a.cta_type ? `<span class="cta-pill">${_escape(a.cta_type)}</span>` : ''}</td>
					<td>${a.landing_url ? `<a class="landing" href="${_escape(a.landing_url)}" target="_blank" rel="noopener" title="${_escape(a.landing_url)}">${_escape(_abbrev(a.landing_url))}</a>` : ''}</td>
					<td><span class="plats">${_escape(_abbrevPlats(a.plataformas))}</span></td>
					<td class="row-actions">
						<button onclick="RadarAds.abrir('${_escape(a.name)}')">Ver</button>
						${CAN_EDIT ? `<button onclick="RadarAds.hacerGuion('${_escape(a.name)}')" title="Hacer guión de este ad">📝</button>` : ''}
					</td>
				</tr>
			`;
		}).join('');
	}

	// ---------- Modal detalle ----------
	async function abrirDetalle(name) {
		try {
			const doc = await Radar.api('marketinghub.www.radar.ads.index.obtener_ad', {name});
			const media = doc.video_hd_url || doc.video_sd_url
				? `<video controls playsinline poster="${_escape(doc.imagen_preview_url || '')}">
					<source src="${_escape(doc.video_hd_url || doc.video_sd_url)}">
				</video>`
				: (doc.imagen_preview_url
					? `<img src="${_escape(doc.imagen_preview_url)}" alt="ad">`
					: `<div class="noplay">Sin media disponible</div>`);
			const dlUrl = doc.video_hd_url || doc.video_sd_url || doc.imagen_preview_url;
			const bodyHtml = `
				<div class="adm-body">
					<div class="adm-media">${media}</div>
					<div class="adm-info">
						<h4>Copy completo</h4>
						<div class="copy-full">${_escape(doc.copy_texto || '(sin texto)')}</div>

						<h4>Metadatos</h4>
						<div class="kv"><span class="k">Marca</span><span class="v">${_escape(doc.competidor || '—')}</span></div>
						<div class="kv"><span class="k">Página FB</span><span class="v">${_escape(doc.page_name || '—')}</span></div>
						<div class="kv"><span class="k">Activo desde</span><span class="v">${_fmtDDMMYY(doc.fecha_inicio)}</span></div>
						<div class="kv"><span class="k">Días activo</span><span class="v"><b>${doc.dias_activo || 0}d</b></span></div>
						<div class="kv"><span class="k">Estado</span><span class="v">${doc.esta_activo ? '🟢 Activo' : '⛔ Pausado' + (doc.fecha_pausado ? ' desde ' + _fmtDDMMYY(doc.fecha_pausado) : '')}</span></div>
						<div class="kv"><span class="k">Etiqueta</span><span class="v">${BADGE_LBL[doc.etiqueta_ganador] || '—'}</span></div>
						<div class="kv"><span class="k">Formato</span><span class="v">${_formato_ico(doc.formato)} ${_escape(doc.formato || '—')}</span></div>
						<div class="kv"><span class="k">CTA</span><span class="v">${_escape(doc.cta_type || '—')}</span></div>
						<div class="kv"><span class="k">Variantes</span><span class="v">${doc.n_variantes || 1}</span></div>
						<div class="kv"><span class="k">Plataformas</span><span class="v">${_escape((doc.plataformas || '').split(',').join(' · ') || '—')}</span></div>
						${doc.landing_url ? `<div class="kv"><span class="k">Landing</span><span class="v"><a href="${_escape(doc.landing_url)}" target="_blank" style="color:#1f5eff;">Ver landing ↗</a></span></div>` : ''}
						${doc.hashtags ? `<div class="kv"><span class="k">Hashtags</span><span class="v" style="font-size:11px;">${_escape(doc.hashtags)}</span></div>` : ''}

						<div class="adm-actions">
							${dlUrl ? `<a href="${_escape(dlUrl)}" target="_blank" download>⬇ Descargar</a>` : ''}
							${doc.landing_url ? `<a href="${_escape(doc.landing_url)}" target="_blank">🔗 Landing</a>` : ''}
							<a href="https://www.facebook.com/ads/library/?id=${_escape(doc.ad_archive_id)}" target="_blank">📢 Ver en Ad Library</a>
							${CAN_EDIT ? `<button class="prim" onclick="RadarAds.hacerGuion('${_escape(doc.name)}')">📝 Hacer guión de este ad</button>` : ''}
						</div>
					</div>
				</div>
			`;
			Radar.modal({
				title: `Ad · ${doc.competidor || ''}`,
				bodyHtml: bodyHtml,
				confirmText: 'Cerrar',
				cancelText: '',
				onConfirm: () => true,
			});
		} catch (e) {
			Radar.toast('Error abriendo ad: ' + e.message, 'error');
		}
	}

	// ---------- Actualizar ----------
	async function actualizar() {
		if (!CAN_EDIT) { Radar.toast('Sin permisos', 'error'); return; }
		const btn = document.getElementById('btn-refresh');
		const orig = btn.textContent;
		btn.disabled = true; btn.textContent = '⏳ Scrapeando…';
		try {
			const r = await Radar.api('marketinghub.api.radar_ads_scraper.ejecutar_scrape_ads_ahora');
			const s = r.stats || {};
			Radar.toast(`✅ ${s.insert || 0} nuevos · ${s.update || 0} actualizados · ${s.pausados || 0} pausados`, 'success');
			await cargar();
		} catch (e) {
			Radar.toast('Error: ' + e.message, 'error');
		} finally {
			btn.disabled = false; btn.textContent = orig;
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

	// ---------- CSV ----------
	function csv() {
		const lista = filtrar();
		if (!lista.length) { Radar.toast('Sin data', 'error'); return; }
		const cols = [
			['dias_activo','Días activo'], ['etiqueta_ganador','Etiqueta'],
			['esta_activo','Activo'], ['competidor','Competidor'],
			['fecha_inicio','Inicio'], ['fecha_pausado','Pausado'],
			['formato','Formato'], ['cta_type','CTA'],
			['copy_texto','Copy'], ['landing_url','Landing'],
			['plataformas','Plataformas'], ['n_variantes','Variantes'],
			['ad_archive_id','Ad ID'], ['video_hd_url','Video HD'],
			['imagen_preview_url','Preview'],
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
	}

	// ---------- Wire ----------
	function wire() {
		document.getElementById('f-search').addEventListener('input', function () {
			FILTROS.q = this.value.trim(); renderTabla();
		});
		document.getElementById('f-comp').addEventListener('change', function () {
			FILTROS.competidor = this.value; renderTabla();
		});
		document.getElementById('f-formato').addEventListener('change', function () {
			FILTROS.formato = this.value; renderTabla();
		});
		document.getElementById('f-etiqueta').addEventListener('change', function () {
			FILTROS.etiqueta = this.value; renderTabla();
		});
		document.getElementById('f-30d').addEventListener('click', function () {
			this.classList.toggle('on');
			FILTROS.dias_min = this.classList.contains('on') ? 30 : null;
			renderTabla();
		});
		document.getElementById('f-activos').addEventListener('click', function () {
			this.classList.toggle('on');
			FILTROS.activos = this.classList.contains('on');
			renderTabla();
		});
		document.querySelectorAll('.ads-tbl th.sort').forEach(th => {
			th.addEventListener('click', function () {
				const c = th.dataset.sort;
				if (SORT.campo === c) SORT.dir = SORT.dir === 'asc' ? 'desc' : 'asc';
				else { SORT.campo = c; SORT.dir = c === 'dias_activo' ? 'desc' : 'desc'; }
				renderTabla();
			});
		});
		document.getElementById('btn-refresh').addEventListener('click', actualizar);
		document.getElementById('btn-csv').addEventListener('click', csv);
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
	};
})();
