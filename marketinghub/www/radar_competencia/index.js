/* /radar_competencia/index.js — Herramienta tipo Excel para inteligencia competitiva.
 *
 * Estado persistido en localStorage bajo la clave `radar-competencia`.
 * Estructura: { competidores: [...], radar: [...], version: 1 }
 */

(function () {
	"use strict";

	const STORAGE_KEY = "radar-competencia";
	const VERSION = 1;

	const PLATAFORMAS = ["Instagram", "TikTok", "Facebook", "YouTube", "X", "Otro"];
	const PRIORIDADES = ["", "Alta", "Media", "Baja"];
	const FORMATOS = ["", "Reel", "Post", "Story", "Carousel", "Video", "Live", "Short"];
	const ESTADOS_IDEA = ["", "Por revisar", "En idea", "En produccion", "Publicado", "Descartado"];

	const SCHEMA = {
		competidores: {
			label: "competidor",
			fields: [
				{ key: "marca", type: "text", placeholder: "Nombre de la marca" },
				{ key: "plataforma", type: "select", options: PLATAFORMAS },
				{ key: "url", type: "url", placeholder: "https://..." },
				{ key: "seguidores", type: "text", placeholder: "12.4K" },
				{ key: "nicho", type: "text", placeholder: "Ropa deportiva" },
				{ key: "prioridad", type: "select", options: PRIORIDADES },
				{ key: "notas", type: "textarea", placeholder: "Observaciones..." }
			]
		},
		radar: {
			label: "publicacion",
			fields: [
				{ key: "competidor", type: "text", placeholder: "Marca" },
				{ key: "plataforma", type: "select", options: PLATAFORMAS },
				{ key: "url", type: "url", placeholder: "https://..." },
				{ key: "fecha", type: "date" },
				{ key: "formato", type: "select", options: FORMATOS },
				{ key: "metrica", type: "text", placeholder: "1.2M views" },
				{ key: "viral", type: "viral" },
				{ key: "idea", type: "textarea", placeholder: "Como replicarlo..." },
				{ key: "estado", type: "select", options: ESTADOS_IDEA }
			]
		}
	};

	/* ---------- Estado ---------- */
	let state = load();
	let currentTab = "competidores";
	let filters = { plataforma: "", q: "", viral: false };

	function load() {
		try {
			const raw = localStorage.getItem(STORAGE_KEY);
			if (!raw) return { competidores: [], radar: [], version: VERSION };
			const parsed = JSON.parse(raw);
			return {
				competidores: Array.isArray(parsed.competidores) ? parsed.competidores : [],
				radar: Array.isArray(parsed.radar) ? parsed.radar : [],
				version: parsed.version || VERSION
			};
		} catch (e) {
			console.error("[radar] no se pudo leer localStorage:", e);
			return { competidores: [], radar: [], version: VERSION };
		}
	}

	function save() {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
			updateStorageSize();
		} catch (e) {
			alert("No se pudo guardar en localStorage: " + e.message);
		}
	}

	function updateStorageSize() {
		const bytes = new Blob([JSON.stringify(state)]).size;
		const kb = (bytes / 1024).toFixed(1);
		const el = document.getElementById("rc-storage-size");
		if (el) el.textContent = kb + " KB";
	}

	function uid() {
		return "r_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
	}

	function emptyRow(sheet) {
		const row = { _id: uid() };
		SCHEMA[sheet].fields.forEach((f) => {
			row[f.key] = f.type === "viral" ? false : "";
		});
		return row;
	}

	/* ---------- Render ---------- */
	function render() {
		document.querySelectorAll(".rc-tab").forEach((t) => {
			t.classList.toggle("is-active", t.dataset.tab === currentTab);
		});
		document.getElementById("rc-sheet-competidores").hidden = currentTab !== "competidores";
		document.getElementById("rc-sheet-radar").hidden = currentTab !== "radar";

		document.getElementById("rc-add-label").textContent =
			currentTab === "competidores" ? "Agregar competidor" : "Agregar publicacion";

		document.querySelectorAll("[data-tab-only]").forEach((el) => {
			el.hidden = el.dataset.tabOnly !== currentTab;
		});

		document.getElementById("rc-count-comp").textContent = state.competidores.length;
		document.getElementById("rc-count-rad").textContent = state.radar.length;

		renderTable(currentTab);
		updateStorageSize();
	}

	function matchesFilters(row, sheet) {
		if (filters.plataforma && row.plataforma !== filters.plataforma) return false;
		if (sheet === "radar" && filters.viral && !row.viral) return false;
		if (filters.q) {
			const q = filters.q.toLowerCase();
			const hay = Object.values(row).some((v) =>
				String(v || "").toLowerCase().includes(q)
			);
			if (!hay) return false;
		}
		return true;
	}

	function renderTable(sheet) {
		const tbody = document.getElementById("rc-tbody-" + sheet);
		const empty = document.getElementById("rc-empty-" + sheet);
		const rows = state[sheet];
		const visible = rows.filter((r) => matchesFilters(r, sheet));

		tbody.innerHTML = "";

		if (rows.length === 0) {
			empty.hidden = false;
			return;
		}
		empty.hidden = true;

		if (visible.length === 0) {
			const tr = document.createElement("tr");
			const colspan = SCHEMA[sheet].fields.length + 2;
			tr.innerHTML = `<td colspan="${colspan}" style="padding:24px;text-align:center;color:var(--rc-muted);font-size:13px;">Ninguna fila coincide con los filtros.</td>`;
			tbody.appendChild(tr);
			return;
		}

		visible.forEach((row, idx) => {
			tbody.appendChild(buildRow(sheet, row, idx));
		});
	}

	function buildRow(sheet, row, idx) {
		const tr = document.createElement("tr");
		tr.dataset.id = row._id;
		if (sheet === "radar" && row.viral) tr.classList.add("is-viral");

		// Index cell
		const tdIdx = document.createElement("td");
		tdIdx.className = "rc-row-index";
		tdIdx.textContent = idx + 1;
		tr.appendChild(tdIdx);

		// Field cells
		SCHEMA[sheet].fields.forEach((f) => {
			tr.appendChild(buildCell(sheet, row, f));
		});

		// Delete
		const tdDel = document.createElement("td");
		tdDel.style.textAlign = "center";
		const btn = document.createElement("button");
		btn.className = "rc-btn-icon";
		btn.title = "Eliminar";
		btn.innerHTML = '<i class="fas fa-trash-alt"></i>';
		btn.addEventListener("click", () => {
			const label = SCHEMA[sheet].label;
			if (confirm(`Eliminar este ${label}?`)) {
				state[sheet] = state[sheet].filter((r) => r._id !== row._id);
				save();
				render();
			}
		});
		tdDel.appendChild(btn);
		tr.appendChild(tdDel);

		return tr;
	}

	function buildCell(sheet, row, field) {
		const td = document.createElement("td");
		const val = row[field.key];

		if (field.type === "select") {
			const sel = document.createElement("select");
			sel.className = "rc-cell-select";
			field.options.forEach((opt) => {
				const o = document.createElement("option");
				o.value = opt;
				o.textContent = opt || "—";
				if (opt === val) o.selected = true;
				sel.appendChild(o);
			});
			sel.addEventListener("change", (e) => {
				updateField(sheet, row._id, field.key, e.target.value);
				if (field.key === "plataforma") renderTable(sheet); // re-render por si filtro cambia
			});

			// Wrap con badge si es plataforma
			if (field.key === "plataforma" && val) {
				const wrap = document.createElement("div");
				wrap.style.display = "flex";
				wrap.style.alignItems = "center";
				wrap.style.gap = "6px";
				wrap.style.padding = "4px 8px";
				const badge = document.createElement("span");
				badge.className = "rc-badge plat-" + val;
				badge.textContent = val;
				wrap.appendChild(badge);
				wrap.appendChild(sel);
				sel.style.width = "auto";
				sel.style.flex = "1";
				td.appendChild(wrap);
			} else {
				td.appendChild(sel);
			}
			return td;
		}

		if (field.type === "textarea") {
			const ta = document.createElement("textarea");
			ta.className = "rc-cell-textarea";
			ta.placeholder = field.placeholder || "";
			ta.value = val || "";
			ta.rows = 1;
			ta.addEventListener("input", (e) => {
				autosize(e.target);
				updateField(sheet, row._id, field.key, e.target.value);
			});
			ta.addEventListener("focus", (e) => autosize(e.target));
			td.appendChild(ta);
			setTimeout(() => autosize(ta), 0);
			return td;
		}

		if (field.type === "viral") {
			const btn = document.createElement("button");
			btn.className = "rc-viral-toggle" + (val ? " is-on" : "");
			btn.innerHTML = val
				? '<i class="fas fa-fire"></i> Viral'
				: '<i class="far fa-circle"></i> No';
			btn.style.marginLeft = "10px";
			btn.addEventListener("click", () => {
				updateField(sheet, row._id, field.key, !val);
				renderTable(sheet);
			});
			td.appendChild(btn);
			return td;
		}

		if (field.type === "url") {
			const wrap = document.createElement("div");
			wrap.className = "rc-cell-url-wrap";
			const inp = document.createElement("input");
			inp.type = "text";
			inp.className = "rc-cell-input";
			inp.placeholder = field.placeholder || "";
			inp.value = val || "";
			inp.addEventListener("input", (e) => {
				updateField(sheet, row._id, field.key, e.target.value);
				updateLinkIcon(link, e.target.value);
			});
			const link = document.createElement("a");
			link.className = "rc-link-icon";
			link.target = "_blank";
			link.rel = "noopener noreferrer";
			link.innerHTML = '<i class="fas fa-external-link-alt"></i>';
			updateLinkIcon(link, val);
			wrap.appendChild(inp);
			wrap.appendChild(link);
			td.appendChild(wrap);
			return td;
		}

		// text / date
		const inp = document.createElement("input");
		inp.type = field.type === "date" ? "date" : "text";
		inp.className = "rc-cell-input";
		inp.placeholder = field.placeholder || "";
		inp.value = val || "";
		inp.addEventListener("input", (e) => {
			updateField(sheet, row._id, field.key, e.target.value);
		});
		td.appendChild(inp);
		return td;
	}

	function updateLinkIcon(link, url) {
		const safe = normalizeUrl(url);
		if (safe) {
			link.href = safe;
			link.classList.remove("is-disabled");
		} else {
			link.removeAttribute("href");
			link.classList.add("is-disabled");
		}
	}

	function normalizeUrl(url) {
		if (!url) return "";
		const trimmed = String(url).trim();
		if (!trimmed) return "";
		if (/^https?:\/\//i.test(trimmed)) return trimmed;
		if (/^[\w.-]+\.[a-z]{2,}/i.test(trimmed)) return "https://" + trimmed;
		return "";
	}

	function autosize(ta) {
		ta.style.height = "auto";
		ta.style.height = Math.min(ta.scrollHeight, 100) + "px";
	}

	function updateField(sheet, id, key, value) {
		const row = state[sheet].find((r) => r._id === id);
		if (!row) return;
		row[key] = value;
		save();
	}

	/* ---------- Acciones ---------- */
	function addRow() {
		const row = emptyRow(currentTab);
		state[currentTab].push(row);
		save();
		render();
		// enfocar la primera celda de la nueva fila
		setTimeout(() => {
			const tr = document.querySelector(`tr[data-id="${row._id}"]`);
			const first = tr && tr.querySelector("input, select, textarea");
			if (first) first.focus();
		}, 20);
	}

	function clearAll() {
		if (!confirm("Esto borrara TODOS los competidores y publicaciones guardadas. Continuar?")) return;
		state = { competidores: [], radar: [], version: VERSION };
		save();
		render();
	}

	/* ---------- CSV ---------- */
	function csvEscape(v) {
		if (v === null || v === undefined) return "";
		const s = String(v);
		if (/[",\n\r]/.test(s)) return '"' + s.replace(/"/g, '""') + '"';
		return s;
	}

	function exportCSV() {
		const sheet = currentTab;
		const fields = SCHEMA[sheet].fields.map((f) => f.key);
		const headers = fields;
		const lines = [headers.map(csvEscape).join(",")];
		state[sheet].forEach((row) => {
			lines.push(fields.map((k) => csvEscape(row[k])).join(","));
		});
		const csv = lines.join("\r\n");
		const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
		const url = URL.createObjectURL(blob);
		const a = document.createElement("a");
		const today = new Date().toISOString().slice(0, 10);
		a.href = url;
		a.download = `radar-${sheet}-${today}.csv`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	}

	function parseCSV(text) {
		const rows = [];
		let cur = [];
		let field = "";
		let inQuotes = false;
		for (let i = 0; i < text.length; i++) {
			const c = text[i];
			if (inQuotes) {
				if (c === '"') {
					if (text[i + 1] === '"') { field += '"'; i++; }
					else inQuotes = false;
				} else {
					field += c;
				}
			} else {
				if (c === '"') inQuotes = true;
				else if (c === ",") { cur.push(field); field = ""; }
				else if (c === "\r") { /* skip */ }
				else if (c === "\n") { cur.push(field); rows.push(cur); cur = []; field = ""; }
				else field += c;
			}
		}
		if (field !== "" || cur.length) { cur.push(field); rows.push(cur); }
		return rows;
	}

	function importCSV(text) {
		let clean = text.replace(/^﻿/, "");
		const rows = parseCSV(clean).filter((r) => r.length && r.some((c) => c !== ""));
		if (rows.length < 2) {
			alert("El CSV esta vacio o solo contiene la cabecera.");
			return;
		}
		const headers = rows.shift().map((h) => h.trim());
		const sheet = currentTab;
		const validKeys = SCHEMA[sheet].fields.map((f) => f.key);
		const known = headers.map((h) => validKeys.includes(h) ? h : null);

		if (!known.some(Boolean)) {
			alert("Las columnas del CSV no coinciden con la hoja actual (" + sheet + ").\n\nColumnas esperadas: " + validKeys.join(", "));
			return;
		}

		const imported = rows.map((r) => {
			const obj = emptyRow(sheet);
			known.forEach((k, i) => {
				if (!k) return;
				const val = r[i] !== undefined ? r[i] : "";
				const fieldDef = SCHEMA[sheet].fields.find((f) => f.key === k);
				if (fieldDef && fieldDef.type === "viral") {
					obj[k] = /^(true|1|si|sí|viral|x)$/i.test(String(val).trim());
				} else {
					obj[k] = val;
				}
			});
			return obj;
		});

		if (!confirm(`Se importaran ${imported.length} filas a la hoja "${sheet}". Se agregaran a las existentes. Continuar?`)) return;
		state[sheet] = state[sheet].concat(imported);
		save();
		render();
	}

	/* ---------- Eventos ---------- */
	function bind() {
		document.querySelectorAll(".rc-tab").forEach((tab) => {
			tab.addEventListener("click", () => {
				currentTab = tab.dataset.tab;
				render();
			});
		});

		document.getElementById("rc-add").addEventListener("click", addRow);
		document.getElementById("rc-clear").addEventListener("click", clearAll);
		document.getElementById("rc-export").addEventListener("click", exportCSV);

		const importBtn = document.getElementById("rc-import");
		const importInput = document.getElementById("rc-import-file");
		importBtn.addEventListener("click", () => importInput.click());
		importInput.addEventListener("change", (e) => {
			const file = e.target.files[0];
			if (!file) return;
			const reader = new FileReader();
			reader.onload = (ev) => importCSV(ev.target.result);
			reader.readAsText(file, "utf-8");
			importInput.value = "";
		});

		document.getElementById("rc-filter-plataforma").addEventListener("change", (e) => {
			filters.plataforma = e.target.value;
			renderTable(currentTab);
		});
		document.getElementById("rc-filter-q").addEventListener("input", (e) => {
			filters.q = e.target.value.trim();
			renderTable(currentTab);
		});
		document.getElementById("rc-filter-viral").addEventListener("change", (e) => {
			filters.viral = e.target.checked;
			renderTable(currentTab);
		});
	}

	document.addEventListener("DOMContentLoaded", () => {
		bind();
		render();
	});
})();
