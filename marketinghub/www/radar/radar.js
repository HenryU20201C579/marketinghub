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
		}
	};
})();
