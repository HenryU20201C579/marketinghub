/* ============================================
   Radar de Competencia — Guiones (Google Tasks style)
   ============================================ */
(function () {
	'use strict';

	const STAGE_CLASS = {
		'Idea':      'st-idea',
		'Guión':     'st-guion',
		'Grabar':    'st-grabar',
		'Editar':    'st-editar',
		'Publicado': 'st-pub',
	};
	const CHECK_POR_ESTADO = {
		'Idea': null,
		'Guión': 'check_guion',
		'Grabar': 'check_grabado',
		'Editar': 'check_editado',
		'Publicado': 'check_publicado',
	};

	let CAN_EDIT = false;
	let GUIONES = [];
	let VISTA_ACTUAL = { tipo: 'todos', valor: null };

	// ---- fechas helpers ----
	function _hoy() { const d = new Date(); d.setHours(0,0,0,0); return d; }
	function _parseISO(s) {
		if (!s) return null;
		const p = s.split('-').map(Number);
		if (p.length !== 3) return null;
		return new Date(p[0], p[1]-1, p[2]);
	}
	function _fmtDDMM(d) {
		if (!d) return '';
		return String(d.getDate()).padStart(2,'0') + '/' + String(d.getMonth()+1).padStart(2,'0');
	}
	function _diffDias(a, b) { return Math.round((a - b) / 86400000); }
	function _fmtVistas(n) {
		n = n || 0;
		if (n >= 1000000) return (n/1000000).toFixed(1).replace(/\.0$/,'') + 'M';
		if (n >= 1000)    return (n/1000).toFixed(1).replace(/\.0$/,'') + 'k';
		return n.toLocaleString('es-PE');
	}

	// ---- Agrupacion ----
	function agrupar(guiones) {
		const hoy = _hoy();
		const finSemana = new Date(hoy); finSemana.setDate(finSemana.getDate() + 6);
		const grupos = {
			'atrasado': { titulo: '🔴 Atrasados', items: [] },
			'hoy':      { titulo: '📅 Hoy', items: [] },
			'semana':   { titulo: '📅 Esta semana', items: [] },
			'futuro':   { titulo: '📆 Más adelante', items: [] },
			'sinFecha': { titulo: '💡 Sin fecha', items: [] },
			'publicado':{ titulo: '✅ Publicados este mes', items: [] },
		};
		const haceMes = new Date(hoy); haceMes.setDate(haceMes.getDate() - 30);
		guiones.forEach(g => {
			if (g.estado === 'Publicado') {
				const fp = _parseISO(g.fecha_publicacion);
				if (!fp || fp >= haceMes) grupos.publicado.items.push(g);
				return;
			}
			const fp = _parseISO(g.fecha_publicacion);
			if (!fp) { grupos.sinFecha.items.push(g); return; }
			const dif = _diffDias(fp, hoy);
			if (dif < 0)  grupos.atrasado.items.push(g);
			else if (dif === 0) grupos.hoy.items.push(g);
			else if (dif <= 6)  grupos.semana.items.push(g);
			else grupos.futuro.items.push(g);
		});
		return grupos;
	}

	// ---- Render ----
	function render() {
		const cont = document.getElementById('gt-lista');
		if (!cont) return;

		// aplicar filtro (vista)
		let lista = GUIONES.slice();
		const hoy = _hoy();
		if (VISTA_ACTUAL.tipo === 'semana') {
			const fin = new Date(hoy); fin.setDate(fin.getDate() + 6);
			lista = lista.filter(g => {
				const fp = _parseISO(g.fecha_publicacion);
				return fp && fp >= hoy && fp <= fin;
			});
		} else if (VISTA_ACTUAL.tipo === 'mios' && window.RadarUser) {
			lista = lista.filter(g => g.asignado_a === window.RadarUser);
		} else if (VISTA_ACTUAL.tipo === 'estado' && VISTA_ACTUAL.valor) {
			lista = lista.filter(g => g.estado === VISTA_ACTUAL.valor);
		}

		if (!lista.length) {
			cont.innerHTML = '<div class="gt-loading">Sin guiones para esta vista. Crea uno con el botón "+ Nuevo guión" o desde la lista de publicaciones virales.</div>';
			return;
		}

		const grupos = agrupar(lista);
		const orden = ['atrasado','hoy','semana','futuro','sinFecha','publicado'];
		let html = '';
		orden.forEach(k => {
			const grp = grupos[k];
			if (!grp.items.length) return;
			html += `
				<section class="gt-group">
					<div class="gt-group-head">
						<span class="gt-group-title">${grp.titulo}</span>
						<span class="gt-group-cnt">${grp.items.length}</span>
					</div>
					${grp.items.map(renderTask).join('')}
				</section>
			`;
		});
		cont.innerHTML = html;
		if (window.lucide) lucide.createIcons();
		wireTasks();
	}

	function renderTask(g) {
		const clsEstado = STAGE_CLASS[g.estado] || 'st-idea';
		const done = g.estado === 'Publicado';
		const check = done ? '✓' : '';
		const fpTxt = g.fecha_publicacion ? _fmtDDMM(_parseISO(g.fecha_publicacion)) : 'sin fecha';
		const hora = g.hora_publicacion ? ' · ' + g.hora_publicacion.slice(0,5) : '';
		const plat = g.plataforma ? plataformaIco(g.plataforma) : '';
		const ref = g.referencia_publicacion
			? `<span class="ref">🔥 ${escapeHtml(g.ref_competidor || 'Ref')} ${_fmtVistas(g.ref_vistas)}</span>`
			: '';
		let ratio = '';
		if (g.estado === 'Publicado' && g.mi_vistas) {
			const rat = g.ratio_vs_referente || 0;
			const cls = rat >= 1 ? 'ratio-win' : (rat >= 0.5 ? 'ratio-mid' : 'ratio-low');
			ratio = ` · <span class="${cls}">${_fmtVistas(g.mi_vistas)} · ${rat.toFixed(1)}× ref${rat >= 1 ? ' 🎉' : ''}</span>`;
		}
		return `
			<a class="gt-task ${done ? 'done' : ''}"
			   data-name="${escapeHtml(g.name)}"
			   href="/radar/guion?name=${encodeURIComponent(g.name)}">
				<span class="check" data-check title="${done ? 'Publicado' : 'Marcar como publicado'}">${check}</span>
				<span class="stage-dot ${clsEstado}" title="${escapeHtml(g.estado)}"></span>
				<div class="body">
					<div class="t">${escapeHtml(g.titulo)}</div>
					<div class="meta">
						${plat ? `<span>${plat}</span><span class="sep">·</span>` : ''}
						<span>${fpTxt}${hora}</span>
						${ref ? `<span class="sep">·</span>${ref}` : ''}
						${ratio}
					</div>
				</div>
				<div class="actions">
					<button data-del title="Eliminar"><i data-lucide="trash-2" style="width:14px;height:14px;"></i></button>
				</div>
			</a>
		`;
	}

	function plataformaIco(p) {
		if (p === 'TikTok')    return '📱 TikTok';
		if (p === 'Instagram') return '📷 IG';
		if (p === 'Facebook')  return '📘 FB';
		if (p === 'YouTube')   return '▶️ YT';
		if (p === 'Ambas')     return '📱📷 Ambas';
		return escapeHtml(p);
	}

	function escapeHtml(s) {
		if (s == null) return '';
		return String(s).replace(/[&<>"']/g, c => ({
			'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;',
		})[c]);
	}

	// ---- Interacciones ----
	function wireTasks() {
		document.querySelectorAll('.gt-task').forEach(el => {
			const check = el.querySelector('[data-check]');
			if (check) {
				check.addEventListener('click', async function (e) {
					e.preventDefault(); e.stopPropagation();
					if (!CAN_EDIT) {
						Radar.toast('No tienes permisos de edición', 'error'); return;
					}
					const name = el.dataset.name;
					const done = el.classList.contains('done');
					try {
						await Radar.api('marketinghub.www.radar.guiones.index.toggle_check', {
							name: name, campo: 'check_publicado', valor: done ? 0 : 1,
						});
						Radar.toast(done ? 'Marcado como no publicado' : '✅ Publicado', 'success');
						await cargar();
					} catch (err) {
						Radar.toast(err.message || 'Error', 'error');
					}
				});
			}
			const del = el.querySelector('[data-del]');
			if (del) {
				del.addEventListener('click', function (e) {
					e.preventDefault(); e.stopPropagation();
					if (!CAN_EDIT) { Radar.toast('Sin permisos', 'error'); return; }
					const name = el.dataset.name;
					const titulo = el.querySelector('.t').textContent;
					Radar.modal({
						title: 'Eliminar guión',
						bodyHtml: `<p>¿Eliminar el guión <b>${escapeHtml(titulo)}</b>? Esta acción no se puede deshacer.</p>`,
						confirmText: 'Eliminar', danger: true,
						onConfirm: async () => {
							await Radar.api('marketinghub.www.radar.guiones.index.eliminar', { name });
							Radar.toast('Guión eliminado', 'success');
							await cargar();
						},
					});
				});
			}
		});
	}

	// ---- Data loading ----
	async function cargar() {
		try {
			const [lista, cnt] = await Promise.all([
				Radar.api('marketinghub.www.radar.guiones.index.listar'),
				Radar.api('marketinghub.www.radar.guiones.index.contadores'),
			]);
			GUIONES = lista || [];
			// contadores
			document.querySelectorAll('[data-cnt]').forEach(el => {
				const k = el.dataset.cnt;
				if (k === 'total') el.textContent = cnt.total;
				else if (k === 'esta_semana') el.textContent = cnt.esta_semana;
				else if (k === 'mios') el.textContent = cnt.mios;
				else if (cnt.por_estado[k] != null) el.textContent = cnt.por_estado[k];
			});
			render();
		} catch (e) {
			Radar.toast('Error cargando guiones: ' + e.message, 'error');
			console.error(e);
		}
	}

	function wireSidebar() {
		document.querySelectorAll('.gt-fil').forEach(el => {
			el.addEventListener('click', function () {
				document.querySelectorAll('.gt-fil').forEach(x => x.classList.remove('on'));
				el.classList.add('on');
				VISTA_ACTUAL = {
					tipo: el.dataset.vista,
					valor: el.dataset.val || null,
				};
				const titles = {
					'todos':  '📋 Todos los guiones',
					'semana': '📅 Guiones de esta semana',
					'mios':   '👤 Mis guiones',
					'estado': el.dataset.val ? `${el.textContent.trim().split('\n')[0]}` : '📋 Todos',
				};
				document.getElementById('gt-title').textContent =
					VISTA_ACTUAL.tipo === 'estado'
						? `Estado: ${VISTA_ACTUAL.valor}`
						: (titles[VISTA_ACTUAL.tipo] || '📋 Todos');
				render();
			});
		});
	}

	function wireNuevo() {
		const btn = document.getElementById('gt-nuevo');
		if (!btn) return;
		btn.addEventListener('click', function () {
			if (!CAN_EDIT) { Radar.toast('Sin permisos para crear', 'error'); return; }
			Radar.modal({
				title: 'Nuevo guión',
				bodyHtml: `
					<div style="display:flex;flex-direction:column;gap:10px;">
						<label style="font-size:12px;font-weight:600;">Título</label>
						<input type="text" id="ng-titulo" class="rd-input"
						       placeholder="Ej: Unboxing billetera Perseo — 15 seg" autofocus>
						<label style="font-size:12px;font-weight:600;margin-top:6px;">Fecha planificada (opcional)</label>
						<input type="date" id="ng-fecha" class="rd-input">
					</div>
				`,
				confirmText: 'Crear',
				onConfirm: async (root) => {
					const titulo = (root.querySelector('#ng-titulo').value || '').trim();
					const fecha = root.querySelector('#ng-fecha').value || null;
					if (!titulo) { Radar.toast('El título es obligatorio', 'error'); return false; }
					// Crear via /api/resource
					const csrf = document.querySelector('meta[name="csrf_token"]')?.content
					          || (window.frappe && frappe.csrf_token) || '';
					const res = await fetch('/api/resource/Guion', {
						method: 'POST', credentials: 'same-origin',
						headers: {
							'X-Frappe-CSRF-Token': csrf,
							'Content-Type': 'application/json',
							'X-Requested-With': 'XMLHttpRequest',
						},
						body: JSON.stringify({
							titulo: titulo,
							estado: 'Idea',
							fecha_publicacion: fecha,
						}),
					});
					const data = await res.json();
					if (!res.ok) throw new Error(data.exception || 'Error creando');
					Radar.toast('Guión creado', 'success');
					window.location.href = '/radar/guion?name=' + encodeURIComponent(data.data.name);
					return true;
				},
			});
		});
	}

	// ---- Namespace ----
	window.RadarGuiones = {
		init(canEdit) {
			CAN_EDIT = !!canEdit;
			window.RadarUser = document.querySelector('.rd-user')?.textContent.trim() || '';
			wireSidebar();
			wireNuevo();
			cargar();
		},
	};
})();
