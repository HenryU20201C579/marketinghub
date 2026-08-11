/* ============================================
   Radar de Competencia — Editor de Guion (minimal)
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
		// Referencia compacta arriba
		pintarRef();

		// Usuarios asignables
		const selAsig = document.getElementById('f-asignado');
		selAsig.innerHTML = '<option value="">—</option>';
		(DOC._usuarios || []).forEach(u => {
			const opt = document.createElement('option');
			opt.value = u.name;
			opt.textContent = u.full_name || u.name;
			selAsig.appendChild(opt);
		});

		// Rellenar campos
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

		// Autoresize textareas del guión
		document.querySelectorAll('.ge-sec textarea').forEach(autoresize);

		// Checkboxes
		document.querySelectorAll('[data-check]').forEach(el => {
			const f = el.dataset.check;
			el.checked = !!DOC[f];
			el.disabled = !CAN_EDIT;
			el.parentElement.classList.toggle('done', !!DOC[f]);
		});

		marcarEstado(DOC.estado);
		actualizarProgreso();
		actualizarRatio();

		wireCambios();
		wireEstadoPills();
	}

	function pintarRef() {
		const cont = document.getElementById('ge-ref-box');
		if (!DOC._ref) {
			cont.innerHTML = `<div class="ge-ref-empty">Sin referencia · <a href="/radar/publicaciones">vincular desde publicaciones</a></div>`;
			return;
		}
		const r = DOC._ref;
		const fecha = r.fecha_publicacion
			? r.fecha_publicacion.split('-').reverse().slice(0,2).join('/')
			: '';
		const partes = [];
		if (r.competidor) partes.push(_escape(r.competidor));
		if (r.plataforma) partes.push(_escape(r.plataforma));
		if (r.vistas_actual) partes.push('<span class="mono">' + _fmtNum(r.vistas_actual) + '</span>');
		if (fecha) partes.push('<span class="mono">' + fecha + '</span>');
		const linkHtml = r.url_publicacion
			? `<a class="lk" href="${_escape(r.url_publicacion)}" target="_blank" rel="noopener">↗ ver</a>`
			: '';
		cont.innerHTML = `
			<div class="ge-ref">
				<span class="dot"></span>
				<span>Referencia:</span>
				<b>${_escape(r.titulo_hook || 'Sin título')}</b>
				<span>· ${partes.join(' · ')}</span>
				${linkHtml}
			</div>
		`;
	}

	function autoresize(ta) {
		if (!ta) return;
		ta.style.height = 'auto';
		ta.style.height = (ta.scrollHeight + 2) + 'px';
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
			Object.assign(DOC, cambios);
			if (res && res.estado) { DOC.estado = res.estado; marcarEstado(res.estado); }
			if (res && res.ratio_vs_referente != null) {
				DOC.ratio_vs_referente = res.ratio_vs_referente; actualizarRatio();
			}
			actualizarProgreso();
			document.querySelectorAll('[data-check]').forEach(el => {
				el.parentElement.classList.toggle('done', !!DOC[el.dataset.check]);
			});
			mostrarEstado('saved');
		} catch (e) {
			mostrarEstado('error', e.message);
			Object.assign(PENDING, cambios);
		}
	}

	function mostrarEstado(estado, msg) {
		const el = document.getElementById('ge-save-status');
		el.classList.remove('saving','saved');
		if (estado === 'saving') { el.classList.add('saving'); el.textContent = 'Guardando…'; }
		else if (estado === 'saved') { el.classList.add('saved'); el.textContent = 'Guardado'; }
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
				if (el.classList.contains('ge-title-input')) {
					// nada, el input ya se ve
				}
				if (el.tagName === 'TEXTAREA') autoresize(el);
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
		document.querySelectorAll('#ge-estados .p, .ge-estados .p').forEach(el => {
			el.addEventListener('click', function () {
				if (!CAN_EDIT) return;
				const est = el.dataset.estado;
				marcarEstado(est);
				marcarPendiente('estado', est);
			});
		});
	}

	function marcarEstado(estado) {
		document.querySelectorAll('#ge-estados .p, .ge-estados .p').forEach(el => {
			el.classList.toggle('on', el.dataset.estado === estado);
		});
	}

	function actualizarProgreso() {
		const checks = document.querySelectorAll('[data-check]');
		const done = Array.from(checks).filter(c => c.checked).length;
		const total = checks.length;
		const pct = total ? Math.round(done / total * 100) : 0;
		const fill = document.getElementById('ge-progress-fill');
		const txt = document.getElementById('ge-progress-txt');
		if (fill) fill.style.width = pct + '%';
		if (txt) txt.textContent = `${done}/${total}`;
	}

	function actualizarRatio() {
		const el = document.getElementById('ge-ratio');
		if (!el) return;
		const r = DOC.ratio_vs_referente || 0;
		el.classList.remove('win','mid','low');
		if (!r) { el.textContent = '—'; return; }
		let cls = 'low';
		if (r >= 1) cls = 'win';
		else if (r >= 0.5) cls = 'mid';
		el.classList.add(cls);
		el.textContent = r.toFixed(2) + '×' + (r >= 1 ? ' 🎉' : '');
	}

	// ---- Namespace ----
	window.RadarGuion = {
		init(canEdit) {
			CAN_EDIT = !!canEdit;
			NAME = _getNameFromUrl();
			if (!NAME) {
				const box = document.querySelector('.ge-layout') || document.querySelector('.ge-wrap');
				if (box) box.innerHTML =
					'<div style="padding:40px;text-align:center;color:#9ca3af;">Falta el parámetro <code>?name=</code> en la URL.</div>';
				return;
			}
			cargar();
		},
	};
})();
