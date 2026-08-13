/* ============================================
   Radar de Competencia — Editor Guion (simple, 5 campos)
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
	// Estado interno del DocType tiene 5 valores. La UI simple usa 2.
	function _estadoSimple(estadoInterno) {
		return estadoInterno === 'Publicado' ? 'Publicado' : 'Pendiente';
	}
	// Cuando el user clickea la UI, mapeamos al valor interno
	function _estadoInterno(uiValor) {
		if (uiValor === 'Publicado') return 'Publicado';
		// Si estaba en algún estado avanzado (Guión, Grabar, Editar), preservarlo si el usuario NO quiere revertir todo a "Idea"
		return DOC && ['Guión','Grabar','Editar'].includes(DOC.estado) ? DOC.estado : 'Idea';
	}

	// ---- Cargar ----
	async function cargar() {
		try {
			DOC = await Radar.api('marketinghub.www.radar.guion.index.obtener', { name: NAME });
			// Si guion_texto está vacío pero hay campos AIDA viejos, concatenar como fallback
			if (!DOC.guion_texto) {
				const parts = [];
				if (DOC.hook)     parts.push('HOOK (0-3s):\n' + DOC.hook);
				if (DOC.setup)    parts.push('SETUP:\n' + DOC.setup);
				if (DOC.producto) parts.push('PRODUCTO:\n' + DOC.producto);
				if (DOC.prueba)   parts.push('PRUEBA:\n' + DOC.prueba);
				if (DOC.cta)      parts.push('CTA:\n' + DOC.cta);
				if (parts.length) DOC.guion_texto = parts.join('\n\n');
			}
			pintar();
		} catch (e) {
			Radar.toast('Error cargando guión: ' + e.message, 'error');
		}
	}

	function pintar() {
		pintarRef();

		// Campos simples
		document.querySelectorAll('[data-field]').forEach(el => {
			const f = el.dataset.field;
			const v = DOC[f];
			el.value = v == null ? '' : v;
			el.disabled = !CAN_EDIT;
		});

		// Estado (mapear interno → UI)
		marcarEstado(_estadoSimple(DOC.estado));

		// Resultado visible solo si publicado
		toggleResultado(DOC.estado === 'Publicado');
		actualizarRatio();

		wireCambios();
		wireEstadoToggle();
		wireEliminar();
		wireAvanzado();
	}

	function pintarRef() {
		const cont = document.getElementById('ge-ref-box');
		if (!DOC._ref) {
			cont.innerHTML = `<div class="ge-ref-empty">Sin referencia · <a href="/radar/publicaciones">vincular desde publicaciones</a></div>`;
			return;
		}
		const r = DOC._ref;
		const partes = [];
		if (r.competidor)    partes.push(_escape(r.competidor));
		if (r.plataforma)    partes.push(_escape(r.plataforma));
		if (r.vistas_actual) partes.push(_fmtNum(r.vistas_actual) + ' vistas');
		const linkHtml = r.url_publicacion
			? `<a class="link" href="${_escape(r.url_publicacion)}" target="_blank" rel="noopener">Ver post</a>`
			: '';
		cont.innerHTML = `
			<div class="ge-ref">
				<span class="lbl">Basado en:</span>
				<span title="${_escape(r.titulo_hook || '')}">${_escape((r.titulo_hook || 'Post viral').substring(0, 60))}</span>
				<span style="color:#a16207;">· ${partes.join(' · ')}</span>
				${linkHtml}
			</div>
		`;
	}

	// ---- Guardado debounce ----
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
			if (res && res.estado) { DOC.estado = res.estado; }
			if (res && res.ratio_vs_referente != null) {
				DOC.ratio_vs_referente = res.ratio_vs_referente; actualizarRatio();
			}
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
		else if (estado === 'error') { el.textContent = 'Error: ' + (msg || ''); }
		else el.textContent = '·';
	}

	function wireCambios() {
		document.querySelectorAll('[data-field]').forEach(el => {
			const evt = (el.type === 'date' || el.type === 'time' || el.tagName === 'SELECT') ? 'change' : 'input';
			el.addEventListener(evt, function () {
				if (!CAN_EDIT) return;
				let v = el.value;
				if (el.type === 'number') v = v === '' ? null : Number(v);
				marcarPendiente(el.dataset.field, v);
			});
		});
	}

	function wireEstadoToggle() {
		document.querySelectorAll('#ge-estado-toggle button').forEach(btn => {
			btn.addEventListener('click', function () {
				if (!CAN_EDIT) return;
				const ui = btn.dataset.estado;
				const interno = _estadoInterno(ui);
				marcarEstado(ui);
				toggleResultado(ui === 'Publicado');
				marcarPendiente('estado', interno);
			});
		});
	}

	function marcarEstado(ui) {
		document.querySelectorAll('#ge-estado-toggle button').forEach(btn => {
			btn.classList.remove('on', 'on-pub');
			if (btn.dataset.estado === ui) {
				btn.classList.add(ui === 'Publicado' ? 'on-pub' : 'on');
			}
		});
	}

	function toggleResultado(show) {
		const box = document.getElementById('ge-resultado');
		if (box) box.classList.toggle('show', !!show);
	}

	function actualizarRatio() {
		const el = document.getElementById('ge-ratio');
		if (!el) return;
		const r = DOC.ratio_vs_referente || 0;
		el.classList.remove('win','mid','low');
		if (!r) { el.textContent = 'Sin datos'; return; }
		let cls = 'low';
		if (r >= 1) cls = 'win';
		else if (r >= 0.5) cls = 'mid';
		el.classList.add(cls);
		const suf = r >= 1 ? ' 🎉' : '';
		el.textContent = r.toFixed(2) + '× vs referente' + suf;
	}

	function wireEliminar() {
		const btn = document.getElementById('ge-del');
		if (!btn) return;
		btn.addEventListener('click', function () {
			if (!CAN_EDIT) return;
			Radar.modal({
				title: 'Eliminar guión',
				bodyHtml: '<p>¿Eliminar este guión? Esta acción no se puede deshacer.</p>',
				confirmText: 'Eliminar', danger: true,
				onConfirm: async () => {
					await Radar.api('marketinghub.www.radar.guion.index.eliminar', { name: NAME });
					Radar.toast('Guión eliminado', 'success');
					window.location.href = '/radar';
				},
			});
		});
	}

	function wireAvanzado() {
		const btn = document.getElementById('ge-avanzado');
		if (!btn) return;
		btn.addEventListener('click', function () {
			// Abrir la vista clásica del DocType para editar campos avanzados
			window.open(`/app/guion/${encodeURIComponent(NAME)}`, '_blank');
		});
	}

	// ---- Namespace ----
	window.RadarGuion = {
		init(canEdit) {
			CAN_EDIT = !!canEdit;
			NAME = _getNameFromUrl();
			if (!NAME) {
				const box = document.querySelector('.ge-wrap');
				if (box) box.innerHTML =
					'<div style="padding:40px;text-align:center;color:#9ca3af;">Falta el parámetro <code>?name=</code> en la URL.</div>';
				return;
			}
			cargar();
		},
	};
})();
