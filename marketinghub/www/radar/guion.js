/* ============================================
   Radar de Competencia — Editor de Guion
   ============================================ */
(function () {
	'use strict';

	let CAN_EDIT = false;
	let NAME = null;
	let DOC = null;
	let SAVE_TIMEOUT = null;
	let PENDING = {};

	function _getNameFromUrl() {
		const p = new URLSearchParams(window.location.search);
		return p.get('name');
	}

	function _fmtNum(n) {
		n = n || 0;
		if (n >= 1000000) return (n/1000000).toFixed(1).replace(/\.0$/,'') + 'M';
		if (n >= 1000)    return (n/1000).toFixed(1).replace(/\.0$/,'') + 'k';
		return n.toLocaleString('es-PE');
	}

	function _escape(s) {
		if (s == null) return '';
		return String(s).replace(/[&<>"']/g, c => ({
			'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
		})[c]);
	}

	// ---- Cargar ----
	async function cargar() {
		try {
			DOC = await Radar.api('marketinghub.www.radar.guion.index.obtener', { name: NAME });
			pintar();
		} catch (e) {
			Radar.toast('Error cargando guión: ' + e.message, 'error');
		}
	}

	function pintar() {
		document.getElementById('ge-title').textContent = DOC.titulo || NAME;

		// Referencia
		pintarRef();

		// Usuarios asignables
		const selAsig = document.getElementById('f-asignado');
		selAsig.innerHTML = '<option value="">— sin asignar —</option>';
		(DOC._usuarios || []).forEach(u => {
			const opt = document.createElement('option');
			opt.value = u.name;
			opt.textContent = u.full_name || u.name;
			selAsig.appendChild(opt);
		});

		// Rellenar campos por data-field
		document.querySelectorAll('[data-field]').forEach(el => {
			const f = el.dataset.field;
			const v = DOC[f];
			if (el.tagName === 'INPUT' && el.type === 'checkbox') {
				el.checked = !!v;
			} else {
				el.value = v == null ? '' : v;
			}
			el.disabled = !CAN_EDIT;
		});

		// Checkboxes
		document.querySelectorAll('[data-check]').forEach(el => {
			const f = el.dataset.check;
			el.checked = !!DOC[f];
			el.disabled = !CAN_EDIT;
			el.parentElement.classList.toggle('done', !!DOC[f]);
		});

		// Estado activo
		marcarEstado(DOC.estado);
		actualizarProgreso();
		actualizarRatio();

		wireCambios();
		wireEstadoPills();
	}

	function pintarRef() {
		const cont = document.getElementById('ge-ref-body');
		if (!DOC._ref) {
			cont.innerHTML = `
				<div class="ref-empty">
					Este guión no tiene referencia viral vinculada.<br>
					<span style="font-size:11px;">Vincúlala desde <a href="/radar/publicaciones" style="color:var(--brand);">/radar/publicaciones</a> con el botón "Hacer guión".</span>
				</div>
			`;
			return;
		}
		const r = DOC._ref;
		const fecha = r.fecha_publicacion
			? r.fecha_publicacion.split('-').reverse().slice(0,2).join('/')
			: '';
		cont.innerHTML = `
			<div class="ref-thumb">🎬</div>
			<div class="ref-hook">${_escape(r.titulo_hook || '(sin título)')}</div>
			<div class="ref-meta">🎵 ${_escape(r.competidor)} · ${_escape(r.plataforma)} · ${fecha}</div>
			<div class="ref-metrics">
				<div><div class="ref-metric-num">${_fmtNum(r.vistas_actual)}</div><div class="ref-metric-lbl">Vistas</div></div>
				<div><div class="ref-metric-num">${(r.engagement_pct || 0).toFixed(1)}%</div><div class="ref-metric-lbl">Engagement</div></div>
				<div><div class="ref-metric-num">${_fmtNum(r.likes_actual)}</div><div class="ref-metric-lbl">Likes</div></div>
				<div><div class="ref-metric-num">${_fmtNum(r.comentarios_actual)}</div><div class="ref-metric-lbl">Coment</div></div>
			</div>
			${r.url_publicacion
				? `<a href="${_escape(r.url_publicacion)}" target="_blank" rel="noopener" class="ref-link">↗ Ver post original</a>`
				: ''}
			${r.tier ? `<div style="margin-top:12px;padding:6px 10px;background:var(--bg-soft);border-radius:6px;font-size:12px;text-align:center;">🏆 Tier: <b>${_escape(r.tier)}</b></div>` : ''}
			${r.elementos_a_copiar
				? `<h4>🔥 Elementos a copiar</h4><div style="font-size:12.5px;color:var(--text-2);line-height:1.5;">${_escape(r.elementos_a_copiar)}</div>`
				: ''}
		`;
	}

	// ---- Guardado con debounce ----
	function marcarPendiente(campo, valor) {
		PENDING[campo] = valor;
		mostrarEstado('saving');
		clearTimeout(SAVE_TIMEOUT);
		SAVE_TIMEOUT = setTimeout(flush, 600);
	}

	async function flush() {
		if (!Object.keys(PENDING).length) return;
		const cambios = PENDING; PENDING = {};
		try {
			const res = await Radar.api('marketinghub.www.radar.guion.index.guardar', {
				name: NAME, cambios: cambios,
			});
			// Actualizar DOC en memoria con lo enviado
			Object.assign(DOC, cambios);
			if (res && res.estado) { DOC.estado = res.estado; marcarEstado(res.estado); }
			if (res && res.ratio_vs_referente != null) {
				DOC.ratio_vs_referente = res.ratio_vs_referente; actualizarRatio();
			}
			actualizarProgreso();
			// Reflejar cambios provocados por sync (ej: check_publicado → estado Publicado)
			document.querySelectorAll('[data-check]').forEach(el => {
				el.parentElement.classList.toggle('done', !!DOC[el.dataset.check]);
			});
			mostrarEstado('saved');
		} catch (e) {
			mostrarEstado('error', e.message);
			// re-encolar para reintento manual
			Object.assign(PENDING, cambios);
		}
	}

	function mostrarEstado(estado, msg) {
		const el = document.getElementById('ge-save-status');
		el.classList.remove('saving','saved');
		if (estado === 'saving') { el.classList.add('saving'); el.textContent = '· Guardando…'; }
		else if (estado === 'saved') { el.classList.add('saved'); el.textContent = '✓ Guardado'; }
		else if (estado === 'error') { el.textContent = '⚠ ' + (msg || 'Error'); }
		else el.textContent = '·';
	}

	function wireCambios() {
		document.querySelectorAll('[data-field]').forEach(el => {
			const evt = (el.tagName === 'SELECT' || el.type === 'date' || el.type === 'time') ? 'change' : 'input';
			el.addEventListener(evt, function () {
				if (!CAN_EDIT) return;
				let v = el.value;
				if (el.type === 'number') v = v === '' ? null : Number(v);
				marcarPendiente(el.dataset.field, v);
				if (el.dataset.field === 'titulo') {
					document.getElementById('ge-title').textContent = v || NAME;
				}
			});
		});
		document.querySelectorAll('[data-check]').forEach(el => {
			el.addEventListener('change', function () {
				if (!CAN_EDIT) { el.checked = !el.checked; return; }
				marcarPendiente(el.dataset.check, el.checked ? 1 : 0);
				el.parentElement.classList.toggle('done', el.checked);
				actualizarProgreso();
			});
		});
	}

	function wireEstadoPills() {
		document.querySelectorAll('.estados-pills .pill').forEach(el => {
			el.addEventListener('click', function () {
				if (!CAN_EDIT) return;
				const est = el.dataset.estado;
				marcarEstado(est);
				marcarPendiente('estado', est);
			});
		});
	}

	function marcarEstado(estado) {
		document.querySelectorAll('.estados-pills .pill').forEach(el => {
			const on = el.dataset.estado === estado;
			el.classList.toggle('on', on && estado !== 'Publicado');
			el.classList.toggle('on-pub', on && estado === 'Publicado');
		});
	}

	function actualizarProgreso() {
		const checks = document.querySelectorAll('[data-check]');
		const done = Array.from(checks).filter(c => c.checked).length;
		const total = checks.length;
		const pct = total ? Math.round(done / total * 100) : 0;
		document.getElementById('ge-progress-fill').style.width = pct + '%';
		document.getElementById('ge-progress-txt').textContent = `${done}/${total}`;
	}

	function actualizarRatio() {
		const el = document.getElementById('ge-ratio');
		const r = DOC.ratio_vs_referente || 0;
		if (!r) { el.textContent = '–'; el.className = 'ratio-badge'; return; }
		let cls = 'ratio-low';
		let emoji = '';
		if (r >= 1) { cls = 'ratio-win'; emoji = ' 🎉'; }
		else if (r >= 0.5) { cls = 'ratio-mid'; }
		el.className = 'ratio-badge ' + cls;
		el.textContent = r.toFixed(2) + '×' + emoji;
	}

	// ---- Namespace ----
	window.RadarGuion = {
		init(canEdit) {
			CAN_EDIT = !!canEdit;
			NAME = _getNameFromUrl();
			if (!NAME) {
				document.querySelector('.ge-layout').innerHTML =
					'<div style="padding:40px;text-align:center;color:var(--muted);">Falta el parámetro <code>?name=</code> en la URL.</div>';
				return;
			}
			cargar();
		},
	};
})();
