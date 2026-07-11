// ─────────────────────────────────────────────
// Estado global
// ─────────────────────────────────────────────
let _campanas      = [];
let _conjuntosData = [];   // [{ci, nombre, valor, name, anunciosData:[...]}]
let _conjuntoIdx   = 0;    // contador auto-incremental de IDs de conjunto
let _conjuntoActivo = null; // ci del conjunto actualmente visible en panel derecho
let _etiquetasLead = [];   // [{name, palabras_clave}]
let _etiquetaModoEdicion = false;
let _etiquetaEditandoNombre = null;
let _campanasFiltradas = [];
let _quickFilter = "all";
let _etiquetaFiltro = "";
let _estadoFiltro = "";
let _cuentaFiltro = "";

document.addEventListener("DOMContentLoaded", function () {
    cargarCampanas();
    cargarEtiquetasLead();
    inyectarModalEtiqueta();
});

// ─────────────────────────────────────────────
// CARGAR Y RENDERIZAR TABLA
// ─────────────────────────────────────────────
function cargarCampanas() {
    frappe.call({
        method: "marketinghub.www.campanas_meta.index.obtener_campanas",
        callback: function (r) {
            _campanas = r.message || [];
            poblarFiltroCuentas();
            renderTabla();
        },
        error: function () {
            mostrarToast("Error al cargar campañas", "error");
        }
    });
}

function renderTabla() {
    const tbody = document.getElementById("tabla-campanas");
    const empty = document.getElementById("empty-state");
    const card  = document.querySelector(".cm-card");
    const badge = document.getElementById("badge-total");
    let campanasBase = _campanasFiltradas.length ? _campanasFiltradas : _campanas;
    if (_estadoFiltro) {
        campanasBase = campanasBase.filter(c => c.estado === _estadoFiltro);
    }
    if (_cuentaFiltro) {
        campanasBase = campanasBase.filter(c => c.cuenta_publicitaria === _cuentaFiltro);
    }
    if (_etiquetaFiltro) {
        campanasBase = campanasBase.filter(c =>
            (c.conjuntos || []).some(conj =>
                (conj.anuncios || []).some(a => a.etiqueta === _etiquetaFiltro)
            )
        );
    }
    const campanas = aplicarQuickFilter(campanasBase);

    badge.textContent = campanas.length;
    const btnAll = document.querySelector('.cm-chip[data-filter="all"]');
    const btnAds = document.querySelector('.cm-chip[data-filter="with-ads"]');
    const btnEmpty = document.querySelector('.cm-chip[data-filter="empty"]');
    if (btnAll && btnAds && btnEmpty) {
        [btnAll, btnAds, btnEmpty].forEach(b => b.classList.remove('active'));
        ( _quickFilter === "with-ads" ? btnAds : _quickFilter === "empty" ? btnEmpty : btnAll ).classList.add('active');
    }

    const totalConjuntos = campanas.reduce((acc, c) => acc + (c.conjuntos || []).length, 0);
    const totalAnuncios = campanas.reduce((acc, c) => acc + (c.conjuntos || []).reduce((a, conj) => a + (conj.anuncios || []).length, 0), 0);
    document.getElementById("stat-campanas").textContent = _campanas.length;
    document.getElementById("stat-conjuntos").textContent = totalConjuntos;
    document.getElementById("stat-anuncios").textContent = totalAnuncios;

    const etiquetasPorCampana = (c) => {
        const etiquetas = new Set();
        (c.conjuntos || []).forEach(conj => {
            (conj.anuncios || []).forEach(a => {
                if (a.etiqueta) etiquetas.add(a.etiqueta);
            });
        });
        const arr = [...etiquetas];
        if (!arr.length) return '<span class="cm-subtext">—</span>';
        const visibles = arr.slice(0, 3).map(et => `<span class="cm-etiqueta-chip" title="${escHtml(et)}">${escHtml(et)}</span>`).join('');
        const extra = arr.length > 3 ? `<span class="cm-etiqueta-more">+${arr.length - 3}</span>` : '';
        return `<div class="cm-etiquetas-wrap">${visibles}${extra}</div>`;
    };

    if (!campanas.length) {
        card.style.display = "none";
        empty.style.display = "block";
        document.getElementById("empty-title").textContent = _campanas.length ? "No hay resultados" : "Sin campañas registradas";
        document.getElementById("empty-copy").textContent = _campanas.length ? "Prueba con otro término de búsqueda." : "Crea tu primera campaña Meta para comenzar.";
        lucide.createIcons();
        return;
    }

    card.style.display = "block";
    empty.style.display = "none";

    tbody.innerHTML = campanas.map(c => {
        const numConjuntos = (c.conjuntos || []).length;
        const numAnuncios = (c.conjuntos || []).reduce((acc, conj) => acc + (conj.anuncios || []).length, 0);
        const nombreEnc = encodeURIComponent(c.nombre);
        const nameEnc = encodeURIComponent(c.name);
    return `
        <tr>
            <td class="cm-name-cell">
                <div class="cm-name-wrap">
                    <span class="cm-row-dot"></span>
                    <div>
                        <div>${escHtml(c.nombre)}</div>
                        <div class="cm-subtext">${numConjuntos} conjunto${numConjuntos !== 1 ? "s" : ""} · ${numAnuncios} anuncio${numAnuncios !== 1 ? "s" : ""}</div>
                    </div>
                </div>
            </td>
            <td>
                <span class="cm-subtext">${escHtml(c.cuenta_publicitaria || "—")}</span>
            </td>
            <td>
                ${etiquetasPorCampana(c)}
            </td>
            <td class="cm-center">
                ${_estadoBadge(c.estado)}
            </td>
            <td class="cm-center">
                <span class="cm-badge-conjuntos">${numConjuntos}</span>
            </td>
            <td class="cm-center">
                <span class="cm-badge-anuncios">${numAnuncios}</span>
            </td>
            <td>
                <div class="cm-actions">
                    <button class="cm-btn cm-btn-blue-sm" onclick="verFicha('${nombreEnc}')">
                        <i data-lucide="eye"></i> Ver
                    </button>
                    ${window.can_edit ? `
                    <button class="cm-btn cm-btn-ghost" style="padding:6px 10px;font-size:13px"
                            onclick="abrirModalEditar('${nombreEnc}')">
                        <i data-lucide="pencil"></i> Editar
                    </button>
                    <button class="cm-btn cm-btn-danger-sm" onclick="eliminarCampana('${nameEnc}')">
                        <i data-lucide="trash-2"></i>
                    </button>
                    ` : ""}
                </div>
            </td>
        </tr>`;
    }).join("");

    if (window.innerWidth <= 768) {
        document.querySelectorAll('.cm-table td:nth-child(2)').forEach(td => td.setAttribute('data-label', 'Cuenta'));
        document.querySelectorAll('.cm-table td:nth-child(3)').forEach(td => td.setAttribute('data-label', 'Etiquetas'));
        document.querySelectorAll('.cm-table td:nth-child(4)').forEach(td => td.setAttribute('data-label', 'Estado'));
        document.querySelectorAll('.cm-table td:nth-child(5)').forEach(td => td.setAttribute('data-label', 'Conjuntos'));
        document.querySelectorAll('.cm-table td:nth-child(6)').forEach(td => td.setAttribute('data-label', 'Anuncios'));
        document.querySelectorAll('.cm-table td:nth-child(7)').forEach(td => td.setAttribute('data-label', 'Acciones'));
    }

    lucide.createIcons();
}

function aplicarQuickFilter(lista) {
    if (_quickFilter === "with-ads") {
        return lista.filter(c => (c.conjuntos || []).some(conj => (conj.anuncios || []).length > 0));
    }
    if (_quickFilter === "empty") {
        return lista.filter(c => !(c.conjuntos || []).some(conj => (conj.anuncios || []).length > 0));
    }
    return lista;
}

function setQuickFilter(filter, btn) {
    _quickFilter = filter;
    document.querySelectorAll('.cm-chip[data-filter]').forEach(el => el.classList.remove('active'));
    if (btn) btn.classList.add('active');
    renderTabla();
}

function filtrarCampanas(query) {
    const q = (query || "").trim().toLowerCase();
    if (!q) {
        _campanasFiltradas = [];
        renderTabla();
        return;
    }

    _quickFilter = "all";

    _campanasFiltradas = _campanas.filter(c => {
        const nombre = (c.nombre || "").toLowerCase();
        const conjuntos = (c.conjuntos || []).some(conj => {
            const n = (conj.nombre || "").toLowerCase();
            const an = (conj.anuncios || []).some(a =>
                (a.nombre || "").toLowerCase().includes(q) ||
                (a.etiqueta || "").toLowerCase().includes(q)
            );
            return n.includes(q) || an;
        });
        return nombre.includes(q) || conjuntos;
    });
    renderTabla();
}

// ─────────────────────────────────────────────
// MODALES
// ─────────────────────────────────────────────
function abrirModal(id) {
    document.getElementById(id).classList.add("open");
    document.body.style.overflow = "hidden";
    lucide.createIcons();
}

function cerrarModal(id) {
    document.querySelectorAll(".cm-tag-dropdown").forEach(d => d.remove());
    document.getElementById(id).classList.remove("open");
    // Restaurar scroll solo si no hay otros modales abiertos
    if (!document.querySelector(".cm-modal-overlay.open")) {
        document.body.style.overflow = "";
    }
}

function cerrarOverlay(event, id) {
    if (event.target === document.getElementById(id)) cerrarModal(id);
}

// ─────────────────────────────────────────────
// MODAL NUEVA CAMPAÑA
// ─────────────────────────────────────────────
function abrirModalNuevo() {
    document.getElementById("modal-titulo").innerHTML = '<i data-lucide="megaphone"></i> Nueva Campaña';
    document.getElementById("input-nombre-campana").value = "";
    document.getElementById("input-campana-original").value = "";
    document.getElementById("input-objetivo-campana").value = "";
    document.getElementById("input-objetivo-campana").disabled = !window.can_edit;

    _conjuntosData  = [];
    _conjuntoIdx    = 0;
    _conjuntoActivo = null;

    renderConjuntosList();
    mostrarPanelDerecho(null);
    document.getElementById("input-nombre-campana").disabled = !window.can_edit;
    abrirModal("modal-campana");
}

// ─────────────────────────────────────────────
// MODAL EDITAR CAMPAÑA
// ─────────────────────────────────────────────
function abrirModalEditar(nombreEncoded) {
    const nombre = decodeURIComponent(nombreEncoded);
    const campana = _campanas.find(c => c.nombre === nombre);
    if (!campana) return mostrarToast("Campaña no encontrada", "error");

    document.getElementById("modal-titulo").innerHTML = '<i data-lucide="pencil"></i> Editar Campaña';
    document.getElementById("input-nombre-campana").value = campana.nombre;
    document.getElementById("input-campana-original").value = campana.name;
    document.getElementById("input-objetivo-campana").value = campana.objetivo || "";
    document.getElementById("input-objetivo-campana").disabled = !window.can_edit;

    _conjuntoIdx    = 0;
    _conjuntoActivo = null;
    _conjuntosData  = (campana.conjuntos || []).map(conj => {
        const ci = _conjuntoIdx++;
        return {
            ci,
            name    : conj.name || "",
            nombre  : conj.nombre || "",
            valor   : conj.valor || 0,
            anunciosData: (conj.anuncios || []).map((a, ai) => ({
                ai,
                name    : a.name || "",
                nombre  : a.nombre || "",
                etiqueta: a.etiqueta || ""
            }))
        };
    });

    renderConjuntosList();
    mostrarPanelDerecho(null);
    document.getElementById("input-nombre-campana").disabled = !window.can_edit;
    abrirModal("modal-campana");
    lucide.createIcons();
}

// ─────────────────────────────────────────────
// LISTA DE CONJUNTOS (columna izquierda)
// ─────────────────────────────────────────────
function renderConjuntosList() {
    const list  = document.getElementById("conjuntos-list");
    const vacio = document.getElementById("conjuntos-vacio");

    list.innerHTML = _conjuntosData.map((conj, i) => {
        const isActive = _conjuntoActivo === conj.ci;
        const nAnuncios = conj.anunciosData.length;
        return `
        <div class="cm-tree-conj-item ${isActive ? "active" : ""}"
             id="conj-item-${conj.ci}"
             onclick="seleccionarConjunto(${conj.ci})">
            <div class="cm-conjunto-idx">${i + 1}</div>
            <div class="cm-tree-conj-item-info">
                <div class="cm-tree-conj-item-name">${conj.nombre ? escHtml(conj.nombre) : `Conjunto ${i + 1}`}</div>
                <div class="cm-tree-conj-item-sub">${nAnuncios} anuncio${nAnuncios !== 1 ? "s" : ""}</div>
            </div>
            ${window.can_edit ? `
            <button class="cm-remove-btn" onclick="event.stopPropagation(); eliminarConjunto(${conj.ci})" title="Eliminar">
                <i data-lucide="x"></i>
            </button>
            ` : ""}
        </div>`;
    }).join("");

    vacio.style.display = _conjuntosData.length === 0 ? "flex" : "none";
    lucide.createIcons();
}

function seleccionarConjunto(ci) {
    // Guardar cambios del conjunto activo antes de cambiar
    if (_conjuntoActivo !== null) guardarCambiosPanelActivo();

    _conjuntoActivo = ci;
    renderConjuntosList();
    mostrarPanelDerecho(ci);
}

// ─────────────────────────────────────────────
// PANEL DERECHO (detalle del conjunto activo)
// ─────────────────────────────────────────────
function mostrarPanelDerecho(ci) {
    document.querySelectorAll(".cm-tag-dropdown").forEach(d => d.remove());
    const panel = document.getElementById("tree-right-panel");

    if (ci === null) {
        panel.innerHTML = `
        <div class="cm-tree-right-empty" id="tree-right-empty">
            <i data-lucide="mouse-pointer-click"></i>
            <p>Selecciona o crea un conjunto<br>para editar sus datos y anuncios.</p>
        </div>`;
        lucide.createIcons();
        return;
    }

    const conj = _conjuntosData.find(c => c.ci === ci);
    if (!conj) return;

    const i = _conjuntosData.indexOf(conj);

    const anunciosHtml = conj.anunciosData.map((a, ai) => buildAnuncioTreeHtml(ci, ai, a)).join("");

    panel.innerHTML = `
    <div class="cm-tree-right-header">
        <div class="cm-conjunto-idx">${i + 1}</div>
        <h4>Conjunto ${i + 1}</h4>
    </div>
    <div class="cm-tree-right-body" id="tree-right-body-${ci}">
        <input type="hidden" id="tree-conj-name-${ci}" value="${escHtml(conj.name)}">

        <!-- Campos del conjunto -->
        <div class="cm-tree-conj-fields">
            <div class="cm-conjunto-row">
                <div class="cm-field">
                    <label class="cm-label">NOMBRE DEL CONJUNTO</label>
                    <input type="text" class="cm-input" id="tree-conj-nombre-${ci}"
                           placeholder="Ej: Conjunto Retargeting" value="${escHtml(conj.nombre)}"
                           oninput="onConjuntoNombreInput(${ci})" ${window.can_edit ? "" : "disabled"}>
                </div>
                <div class="cm-field">
                    <label class="cm-label">PRESUPUESTO (S/)</label>
                    <div class="cm-input-currency">
                        <span>S/</span>
                        <input type="number" class="cm-input" id="tree-conj-valor-${ci}"
                               placeholder="0.00" min="0" step="0.01" value="${conj.valor || ""}"
                               ${window.can_edit ? "" : "disabled"}>
                    </div>
                </div>
            </div>
        </div>

        <!-- Sección anuncios -->
        <div class="cm-tree-ads-section">
            <div class="cm-tree-ads-header">
                <span><i data-lucide="image" style="width:13px;height:13px;margin-right:4px"></i>Anuncios</span>
                ${window.can_edit ? `
                <button class="cm-btn cm-btn-green-sm" onclick="agregarAnuncio(${ci})">
                    <i data-lucide="plus"></i> Agregar Anuncio
                </button>
                ` : ""}
            </div>
            <div class="cm-tree-ads-list" id="tree-anuncios-list-${ci}">
                ${anunciosHtml || `<p style="font-size:13px;color:var(--muted);padding:8px 4px">Sin anuncios. Agrega uno arriba.</p>`}
            </div>
        </div>
    </div>`;

    lucide.createIcons();
}

function buildAnuncioTreeHtml(ci, ai, anuncio) {
    const nombre   = anuncio ? escHtml(anuncio.nombre   || "") : "";
    const etiqueta = anuncio ? (anuncio.etiqueta || "") : "";
    const name     = anuncio ? escHtml(anuncio.name     || "") : "";
    const tagSelId = `tag-sel-${ci}-${ai}`;

    return `
    <div class="cm-anuncio" id="tree-anuncio-${ci}-${ai}" data-ci="${ci}" data-ai="${ai}">
        <div class="cm-anuncio-header">
            <div class="cm-anuncio-idx">${ai + 1}</div>
            <span style="font-size:12px;font-weight:600;color:var(--green);flex:1">Anuncio ${ai + 1}</span>
            ${window.can_edit ? `
            <button class="cm-remove-btn" onclick="eliminarAnuncio(${ci},${ai})" title="Eliminar anuncio">
                <i data-lucide="x"></i>
            </button>
            ` : ""}
        </div>
        <input type="hidden" class="tree-an-name" value="${name}">
        <div class="cm-anuncio-row">
            <div class="cm-field">
                <label class="cm-label">NOMBRE</label>
                <input type="text" class="cm-input tree-an-nombre" placeholder="Ej: Anuncio Carrusel" 
                       value="${nombre}" ${window.can_edit ? "" : "disabled"}>
            </div>
            <div class="cm-field">
                <label class="cm-label">ETIQUETA LEAD</label>
                ${buildTagSelectorHtml(tagSelId, etiqueta)}
            </div>
        </div>
    </div>`;
}

// Sincroniza el nombre del conjunto activo en la lista de la izquierda mientras escribe
function onConjuntoNombreInput(ci) {
    const input = document.getElementById(`tree-conj-nombre-${ci}`);
    if (!input) return;
    const conj = _conjuntosData.find(c => c.ci === ci);
    if (conj) conj.nombre = input.value;
    const item = document.getElementById(`conj-item-${ci}`);
    if (item) {
        const nameEl = item.querySelector(".cm-tree-conj-item-name");
        if (nameEl) nameEl.textContent = input.value || `Conjunto ${_conjuntosData.indexOf(conj) + 1}`;
    }
}

// ─────────────────────────────────────────────
// ETIQUETAS LEAD — carga y selector
// ─────────────────────────────────────────────

function cargarEtiquetasLead() {
    frappe.call({
        method: "marketinghub.www.campanas_meta.index.obtener_etiquetas_lead",
        callback: function (r) {
            _etiquetasLead = r.message || [];
            const sel = document.getElementById("etiqueta-filter-campanas");
            if (sel && _etiquetasLead.length) {
                sel.innerHTML = '<option value="">Todas las etiquetas</option>' +
                    _etiquetasLead.map(t => `<option value="${escHtml(t.name)}">${escHtml(t.name)}</option>`).join('');
            }
        }
    });
}

function setEtiquetaFiltro(etiqueta) {
    _etiquetaFiltro = etiqueta || "";
    renderTabla();
}

function setEstadoFiltro(estado) {
    _estadoFiltro = estado || "";
    renderTabla();
}

function setCuentaFiltro(cuenta) {
    _cuentaFiltro = cuenta || "";
    renderTabla();
}

function poblarFiltroCuentas() {
    const sel = document.getElementById("cuenta-filter-campanas");
    if (!sel) return;
    const cuentas = [...new Set(_campanas.map(c => c.cuenta_publicitaria).filter(Boolean))].sort();
    sel.innerHTML = '<option value="">Todas las cuentas</option>' +
        cuentas.map(c => `<option value="${escHtml(c)}">${escHtml(c)}</option>`).join("");
}

function limpiarTodosFiltros() {
    document.getElementById('search-campanas').value = '';
    document.getElementById('etiqueta-filter-campanas').value = '';
    document.getElementById('estado-filter-campanas').value = '';
    document.getElementById('cuenta-filter-campanas').value = '';
    _etiquetaFiltro = '';
    _estadoFiltro = '';
    _cuentaFiltro = '';
    filtrarCampanas('');
    setQuickFilter('all', document.querySelector('.cm-chip[data-filter="all"]'));
}

function ejecutarDiagnostico() {
    mostrarToast("Ejecutando diagnóstico... esto puede tardar unos segundos", "info");
    frappe.call({
        method: "marketinghub.www.campanas_meta.index.diagnosticar_renombrado",
        callback: function(r) {
            const data = r.message || [];
            if (data.error) {
                mostrarToast(data.error, "error");
                return;
            }
            let html = `<table style="width:100%;border-collapse:collapse;font-size:13px;">
                <thead>
                    <tr style="background:#f8fafc;text-align:left;">
                        <th style="padding:8px 10px;border-bottom:2px solid #e2e8f0;">Campaña</th>
                        <th style="padding:8px 10px;border-bottom:2px solid #e2e8f0;">Tipo Budget</th>
                        <th style="padding:8px 10px;border-bottom:2px solid #e2e8f0;">Objetivo</th>
                        <th style="padding:8px 10px;border-bottom:2px solid #e2e8f0;">Bid Strategy</th>
                        <th style="padding:8px 10px;border-bottom:2px solid #e2e8f0;">Renombrar</th>
                    </tr>
                </thead>
                <tbody>`;
            data.forEach(d => {
                const color = d.puede_renombrar ? '#f0fdf4' : '#fef2f2';
                const icon = d.puede_renombrar ? 'check-circle' : 'x-circle';
                const iconColor = d.puede_renombrar ? '#16a34a' : '#dc2626';
                html += `<tr style="background:${color};">
                    <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">
                        <strong>${escHtml(d.campana)}</strong>
                        <div style="font-size:11px;color:#6b7280;">Anuncio test: ${escHtml(d.anuncio_test)}</div>
                    </td>
                    <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-weight:600;">${escHtml(d.tipo_budget)}</td>
                    <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">${escHtml(d.objetivo)}</td>
                    <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">${escHtml(d.bid_strategy)}</td>
                    <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;">
                        <i data-lucide="${icon}" style="width:16px;height:16px;color:${iconColor};vertical-align:-3px;"></i>
                        ${d.puede_renombrar ? 'Sí' : 'No'}
                        ${d.error ? '<div style="font-size:11px;color:#dc2626;margin-top:2px;">' + escHtml(d.error) + '</div>' : ''}
                    </td>
                </tr>`;
            });
            html += '</tbody></table>';

            if (!data.length) {
                html = '<p style="color:var(--text-muted);text-align:center;padding:20px;">No se encontraron campañas con meta_id para diagnosticar.</p>';
            }

            document.getElementById("modal-log-contenido").innerHTML = html;
            document.getElementById("modal-log-titulo").innerHTML = '<i data-lucide="stethoscope"></i> Diagnóstico de renombrado';
            abrirModal("modal-log");
        },
        error: function() {
            mostrarToast("Error al ejecutar diagnóstico", "error");
        }
    });
}

/**
 * Genera el HTML del selector de Etiqueta Lead
 * @param {string} selId - ID único del contenedor
 * @param {string} valorActual - Etiqueta seleccionada actualmente
 */
function buildTagSelectorHtml(selId, valorActual) {
    const tag = _etiquetasLead.find(t => t.name === valorActual);
    const kw  = tag ? (tag.palabras_clave || "") : "";
    const hasTag = !!valorActual;

    return `
    <div class="cm-tag-selector" id="${selId}" data-value="${escHtml(valorActual)}">
        <input type="hidden" class="tree-an-etiqueta" value="${escHtml(valorActual)}">
        <div class="cm-tag-sel-trigger" onclick="abrirTagDropdown('${selId}')">
            ${hasTag
                ? `<span class="cm-tag-badge">${escHtml(valorActual)}</span>`
                : `<span class="cm-tag-placeholder"><i data-lucide="tag" style="width:13px;height:13px"></i> Seleccionar etiqueta...</span>`
            }
            ${hasTag && window.can_edit ? `<button class="cm-tag-clear" onclick="event.stopPropagation(); abrirModalEditarEtiqueta('${escHtml(valorActual)}', '${selId}')" title="Editar activadores"><i data-lucide="pencil"></i></button>` : ""}
            ${hasTag && window.can_edit ? `<button class="cm-tag-clear" onclick="event.stopPropagation(); limpiarEtiqueta('${selId}')" title="Quitar etiqueta"><i data-lucide="x"></i></button>` : ""}
            <i data-lucide="chevron-down" style="width:14px;height:14px;color:var(--muted);flex-shrink:0"></i>
        </div>
        ${hasTag && kw ? `<div class="cm-tag-kw-preview"><i data-lucide="zap" style="width:11px;height:11px"></i> ${escHtml(kw)}</div>` : ""}
    </div>`;
}

function abrirTagDropdown(selId) {
    // Cerrar otros dropdowns abiertos
    document.querySelectorAll(".cm-tag-dropdown").forEach(d => d.remove());

    const selector = document.getElementById(selId);
    if (!selector) return;

    const valorActual = selector.dataset.value;
    const dropdown    = document.createElement("div");
    dropdown.className = "cm-tag-dropdown";
    dropdown.id = `${selId}-dropdown`;

    // Buscador + lista + crear nueva
    dropdown.innerHTML = `
    <div class="cm-tag-dd-search">
        <i data-lucide="search" style="width:13px;height:13px;flex-shrink:0;color:var(--muted)"></i>
        <input type="text" class="cm-tag-dd-input" placeholder="Buscar etiqueta..."
               oninput="filtrarTagDropdown('${selId}', this.value)"
               autocomplete="off">
    </div>
    <div class="cm-tag-dd-list" id="${selId}-dd-list">
        ${renderTagOptions(selId, "", valorActual)}
    </div>
    ${window.can_edit ? `
    <div class="cm-tag-dd-footer">
        <button class="cm-json-add-btn" style="width:100%;justify-content:center" onclick="abrirModalCrearEtiqueta('${selId}')">
            <i data-lucide="plus"></i> Nueva etiqueta
        </button>
    </div>
    ` : ""}
`;

    document.body.appendChild(dropdown);
    lucide.createIcons();

    // Posicionar el dropdown debajo del trigger usando fixed
    const trigger = selector.querySelector(".cm-tag-sel-trigger");
    const rect = (trigger || selector).getBoundingClientRect();
    dropdown.style.top  = (rect.bottom + 4) + "px";
    dropdown.style.left = rect.left + "px";
    dropdown.style.width = rect.width + "px";

    // Focus al buscador
    setTimeout(() => dropdown.querySelector(".cm-tag-dd-input")?.focus(), 50);

    // Cerrar al hacer click fuera
    setTimeout(() => {
        document.addEventListener("click", function _cerrar(e) {
            if (!selector.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.remove();
                document.removeEventListener("click", _cerrar);
            }
        });
    }, 10);
}

function renderTagOptions(selId, query, valorActual) {
    const q = (query || "").toLowerCase().trim();
    const tags = q
        ? _etiquetasLead.filter(t => t.name.toLowerCase().includes(q) || (t.palabras_clave || "").toLowerCase().includes(q))
        : _etiquetasLead;

    if (!tags.length) {
        return `<div class="cm-tag-dd-empty">Sin resultados</div>`;
    }

    return tags.map(t => {
        const isActive = t.name === valorActual;
        const kw = t.palabras_clave ? `<div class="cm-tag-dd-kw"><i data-lucide="zap" style="width:10px;height:10px"></i> ${escHtml(t.palabras_clave)}</div>` : "";
        const editBtn = window.can_edit
            ? `<button class="cm-tag-dd-edit" onclick="event.stopPropagation(); abrirModalEditarEtiqueta('${escHtml(t.name)}', '${selId}')" title="Editar activadores"><i data-lucide="pencil" style="width:12px;height:12px"></i></button>`
            : "";
        return `
        <div class="cm-tag-dd-option ${isActive ? "active" : ""}">
            <div class="cm-tag-dd-option-main" onclick="seleccionarEtiqueta('${selId}', '${escHtml(t.name)}')">
                <div class="cm-tag-dd-name">${escHtml(t.name)}</div>
                ${kw}
            </div>
            ${editBtn}
        </div>`;
    }).join("");
}

function filtrarTagDropdown(selId, query) {
    const selector   = document.getElementById(selId);
    const listEl     = document.getElementById(`${selId}-dd-list`);
    if (!listEl) return;
    listEl.innerHTML = renderTagOptions(selId, query, selector?.dataset.value || "");
    lucide.createIcons();
}

function seleccionarEtiqueta(selId, tagName) {
    const selector = document.getElementById(selId);
    if (!selector) return;

    // Cerrar dropdown
    document.getElementById(`${selId}-dropdown`)?.remove();

    // Actualizar estado
    selector.dataset.value = tagName;
    const hidden = selector.querySelector(".tree-an-etiqueta");
    if (hidden) hidden.value = tagName;

    // Re-renderizar el selector completo
    const tag = _etiquetasLead.find(t => t.name === tagName);
    const kw  = tag ? (tag.palabras_clave || "") : "";
    const trigger = selector.querySelector(".cm-tag-sel-trigger");
    if (trigger) {
        const editHtml = window.can_edit
            ? `<button class="cm-tag-clear" onclick="event.stopPropagation(); abrirModalEditarEtiqueta('${escHtml(tagName)}', '${selId}')" title="Editar activadores"><i data-lucide="pencil"></i></button>`
            : "";
        const clearHtml = window.can_edit
            ? `<button class="cm-tag-clear" onclick="event.stopPropagation(); limpiarEtiqueta('${selId}')" title="Quitar etiqueta"><i data-lucide="x"></i></button>`
            : "";
        trigger.innerHTML = `<span class="cm-tag-badge">${escHtml(tagName)}</span>
            ${editHtml}
            ${clearHtml}
            <i data-lucide="chevron-down" style="width:14px;height:14px;color:var(--muted);flex-shrink:0"></i>`;
    }
    // Actualizar preview de palabras clave
    let kwEl = selector.querySelector(".cm-tag-kw-preview");
    if (kw) {
        if (!kwEl) {
            kwEl = document.createElement("div");
            kwEl.className = "cm-tag-kw-preview";
            trigger?.after(kwEl);
        }
        kwEl.innerHTML = `<i data-lucide="zap" style="width:11px;height:11px"></i> ${escHtml(kw)}`;
    } else if (kwEl) {
        kwEl.remove();
    }
    lucide.createIcons();
}

function limpiarEtiqueta(selId) {
    const selector = document.getElementById(selId);
    if (!selector) return;
    selector.dataset.value = "";
    const hidden = selector.querySelector(".tree-an-etiqueta");
    if (hidden) hidden.value = "";

    const trigger = selector.querySelector(".cm-tag-sel-trigger");
    if (trigger) {
        trigger.innerHTML = `<span class="cm-tag-placeholder"><i data-lucide="tag" style="width:13px;height:13px"></i> Seleccionar etiqueta...</span>
            <i data-lucide="chevron-down" style="width:14px;height:14px;color:var(--muted);flex-shrink:0"></i>`;
    }
    selector.querySelector(".cm-tag-kw-preview")?.remove();
    selector.querySelector(".cm-tag-clear")?.remove();
    lucide.createIcons();
}

/** Inyecta el modal de crear etiqueta al body (una sola vez) */
function inyectarModalEtiqueta() {
    if (document.getElementById("modal-nueva-etiqueta")) return;
    const div = document.createElement("div");
    div.innerHTML = `
    <div class="cm-modal-overlay" id="modal-nueva-etiqueta" onclick="cerrarOverlay(event,'modal-nueva-etiqueta')">
        <div class="cm-modal" style="max-width:480px" onclick="event.stopPropagation()">
            <div class="cm-modal-header">
                <h3><i data-lucide="tag"></i> Nueva Etiqueta Lead</h3>
                <button class="cm-btn-icon" onclick="cerrarModal('modal-nueva-etiqueta')"><i data-lucide="x"></i></button>
            </div>
            <div class="cm-modal-body" style="gap:14px">
                <div class="cm-field">
                    <label class="cm-label">NOMBRE DE LA ETIQUETA</label>
                    <input type="text" class="cm-input" id="nueva-etiqueta-nombre"
                           placeholder="Ej: Interesado Calzado" autocomplete="off"
                           onkeydown="if(event.key==='Enter') crearNuevaEtiqueta()">
                </div>
                <div class="cm-field">
                    <label class="cm-label">ACTIVADORES (palabras clave, separadas por coma)</label>
                    <textarea class="cm-textarea" id="nueva-etiqueta-palabras"
                              placeholder="Ej: zapatos, calzado, sandalias, botas" rows="3"></textarea>
                    <span style="font-size:11px;color:var(--muted)">
                        Cuando el chatbot detecte estas palabras en la conversación asignará esta etiqueta al lead automáticamente.
                    </span>
                </div>
            </div>
            <div class="cm-modal-footer">
                <button class="cm-btn cm-btn-ghost" onclick="cerrarModal('modal-nueva-etiqueta')">Cancelar</button>
                <button class="cm-btn cm-btn-primary" id="btn-crear-etiqueta" onclick="crearNuevaEtiqueta()">
                    <i data-lucide="plus"></i> Crear Etiqueta
                </button>
            </div>
        </div>
    </div>`;
    document.body.appendChild(div.firstElementChild);
    lucide.createIcons();
}

let _pendingTagSelId = null; // guarda qué selector disparó el modal

function abrirModalCrearEtiqueta(selId) {
    _pendingTagSelId = selId;
    _etiquetaModoEdicion = false;
    _etiquetaEditandoNombre = null;
    document.querySelectorAll(".cm-tag-dropdown").forEach(d => d.remove());

    const modal = document.getElementById("modal-nueva-etiqueta");
    const titleEl = modal?.querySelector("h3");
    if (titleEl) titleEl.innerHTML = '<i data-lucide="tag"></i> Nueva Etiqueta Lead';
    const nombreInput = document.getElementById("nueva-etiqueta-nombre");
    if (nombreInput) { nombreInput.value = ""; nombreInput.disabled = false; }
    document.getElementById("nueva-etiqueta-palabras").value = "";
    const btn = document.getElementById("btn-crear-etiqueta");
    if (btn) btn.innerHTML = '<i data-lucide="plus"></i> Crear Etiqueta';

    abrirModal("modal-nueva-etiqueta");
    lucide.createIcons();
    setTimeout(() => document.getElementById("nueva-etiqueta-nombre")?.focus(), 200);
}

function abrirModalEditarEtiqueta(tagName, selId) {
    _pendingTagSelId = selId;
    _etiquetaModoEdicion = true;
    _etiquetaEditandoNombre = tagName;
    document.querySelectorAll(".cm-tag-dropdown").forEach(d => d.remove());

    const tag = _etiquetasLead.find(t => t.name === tagName);
    const modal = document.getElementById("modal-nueva-etiqueta");
    const titleEl = modal?.querySelector("h3");
    if (titleEl) titleEl.innerHTML = '<i data-lucide="pencil"></i> Editar Etiqueta Lead';
    const nombreInput = document.getElementById("nueva-etiqueta-nombre");
    if (nombreInput) { nombreInput.value = tagName; nombreInput.disabled = true; }
    const palabrasInput = document.getElementById("nueva-etiqueta-palabras");
    if (palabrasInput) palabrasInput.value = tag?.palabras_clave || "";
    const btn = document.getElementById("btn-crear-etiqueta");
    if (btn) btn.innerHTML = '<i data-lucide="save"></i> Guardar Cambios';

    abrirModal("modal-nueva-etiqueta");
    lucide.createIcons();
    setTimeout(() => document.getElementById("nueva-etiqueta-palabras")?.focus(), 200);
}

function crearNuevaEtiqueta() {
    if (_etiquetaModoEdicion) { guardarEdicionEtiqueta(); return; }

    const nombre  = document.getElementById("nueva-etiqueta-nombre")?.value?.trim();
    const palabras = document.getElementById("nueva-etiqueta-palabras")?.value?.trim();

    if (!nombre) {
        mostrarToast("Ingresa el nombre de la etiqueta", "error");
        return;
    }

    const btn = document.getElementById("btn-crear-etiqueta");
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="cm-spin"></i> Creando...';
    lucide.createIcons();

    frappe.call({
        method: "marketinghub.www.campanas_meta.index.crear_etiqueta_lead",
        args: { nombre, palabras_clave: palabras || "" },
        callback: function (r) {
            if (r.message && r.message.status === "ok") {
                // Agregar a lista local
                _etiquetasLead.push({ name: r.message.name, palabras_clave: r.message.palabras_clave });
                _etiquetasLead.sort((a, b) => a.name.localeCompare(b.name));

                cerrarModal("modal-nueva-etiqueta");
                mostrarToast(`Etiqueta "${r.message.name}" creada`, "success");

                // Seleccionarla en el selector que la llamó
                if (_pendingTagSelId) {
                    seleccionarEtiqueta(_pendingTagSelId, r.message.name);
                    _pendingTagSelId = null;
                }
            } else {
                mostrarToast("Error al crear la etiqueta", "error");
            }
        },
        error: function (err) {
            mostrarToast(err?.message || "Error al crear", "error");
        },
        always: function () {
            btn.disabled = false;
            btn.innerHTML = '<i data-lucide="plus"></i> Crear Etiqueta';
            lucide.createIcons();
        }
    });
}

function guardarEdicionEtiqueta() {
    const palabras = document.getElementById("nueva-etiqueta-palabras")?.value?.trim() || "";
    const tagName  = _etiquetaEditandoNombre;

    const btn = document.getElementById("btn-crear-etiqueta");
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="cm-spin"></i> Guardando...';
    lucide.createIcons();

    frappe.call({
        method: "marketinghub.www.campanas_meta.index.actualizar_palabras_clave_etiqueta",
        args: { nombre: tagName, palabras_clave: palabras },
        callback: function (r) {
            if (r.message && r.message.status === "ok") {
                const tag = _etiquetasLead.find(t => t.name === tagName);
                if (tag) tag.palabras_clave = palabras;

                cerrarModal("modal-nueva-etiqueta");
                mostrarToast(`Etiqueta "${tagName}" actualizada`, "success");

                // Refrescar preview si este selector tiene la etiqueta seleccionada
                if (_pendingTagSelId) {
                    const selector = document.getElementById(_pendingTagSelId);
                    if (selector && selector.dataset.value === tagName) {
                        let kwEl = selector.querySelector(".cm-tag-kw-preview");
                        if (palabras) {
                            if (!kwEl) {
                                kwEl = document.createElement("div");
                                kwEl.className = "cm-tag-kw-preview";
                                selector.querySelector(".cm-tag-sel-trigger")?.after(kwEl);
                            }
                            kwEl.innerHTML = `<i data-lucide="zap" style="width:11px;height:11px"></i> ${escHtml(palabras)}`;
                            lucide.createIcons();
                        } else if (kwEl) {
                            kwEl.remove();
                        }
                    }
                    _pendingTagSelId = null;
                }
            } else {
                mostrarToast("Error al actualizar la etiqueta", "error");
            }
        },
        error: function (err) {
            mostrarToast(err?.message || "Error al actualizar", "error");
        },
        always: function () {
            btn.disabled = false;
            btn.innerHTML = '<i data-lucide="save"></i> Guardar Cambios';
            lucide.createIcons();
        }
    });
}

// Lee los datos del panel derecho y los sincroniza en _conjuntosData
function guardarCambiosPanelActivo() {
    const ci = _conjuntoActivo;
    if (ci === null) return;
    const conj = _conjuntosData.find(c => c.ci === ci);
    if (!conj) return;

    const nombreEl = document.getElementById(`tree-conj-nombre-${ci}`);
    const valorEl  = document.getElementById(`tree-conj-valor-${ci}`);
    if (nombreEl) conj.nombre = nombreEl.value.trim();
    if (valorEl)  conj.valor  = parseFloat(valorEl.value || 0);

    const list = document.getElementById(`tree-anuncios-list-${ci}`);
    if (list) {
        conj.anunciosData = [];
        list.querySelectorAll(".cm-anuncio").forEach((anEl, ai) => {
            conj.anunciosData.push({
                ai,
                name    : anEl.querySelector(".tree-an-name")?.value     || "",
                nombre  : anEl.querySelector(".tree-an-nombre")?.value   || "",
                etiqueta: anEl.querySelector(".tree-an-etiqueta")?.value || ""
            });
        });
    }
}

// ─────────────────────────────────────────────
// AGREGAR / ELIMINAR CONJUNTOS
// ─────────────────────────────────────────────
function agregarConjunto() {
    // Guardar panel activo antes de cambiar
    if (_conjuntoActivo !== null) guardarCambiosPanelActivo();

    const ci = _conjuntoIdx++;
    _conjuntosData.push({ ci, name: "", nombre: "", valor: 0, anunciosData: [] });
    _conjuntoActivo = ci;

    renderConjuntosList();
    mostrarPanelDerecho(ci);
}

function eliminarConjunto(ci) {
    const idx = _conjuntosData.findIndex(c => c.ci === ci);
    if (idx === -1) return;
    _conjuntosData.splice(idx, 1);

    if (_conjuntoActivo === ci) {
        _conjuntoActivo = null;
    }

    renderConjuntosList();

    // Si había uno activo diferente sigue mostrándolo, si no limpiamos
    if (_conjuntoActivo !== null) {
        mostrarPanelDerecho(_conjuntoActivo);
    } else {
        mostrarPanelDerecho(null);
    }
}

// ─────────────────────────────────────────────
// AGREGAR / ELIMINAR ANUNCIOS
// ─────────────────────────────────────────────
function agregarAnuncio(ci) {
    const list = document.getElementById(`tree-anuncios-list-${ci}`);
    if (!list) return;

    // Limpiar el aviso de "sin anuncios" si existe
    const emptyMsg = list.querySelector("p");
    if (emptyMsg) emptyMsg.remove();

    const ai = list.querySelectorAll(".cm-anuncio").length;
    list.insertAdjacentHTML("beforeend", buildAnuncioTreeHtml(ci, ai, null));

    // Actualizar contador en lista izquierda
    const conj = _conjuntosData.find(c => c.ci === ci);
    if (conj) {
        const item = document.getElementById(`conj-item-${ci}`);
        if (item) {
            const sub = item.querySelector(".cm-tree-conj-item-sub");
            const n = list.querySelectorAll(".cm-anuncio").length;
            if (sub) sub.textContent = `${n} anuncio${n !== 1 ? "s" : ""}`;
        }
    }

    lucide.createIcons();
}

function eliminarAnuncio(ci, ai) {
    const el = document.getElementById(`tree-anuncio-${ci}-${ai}`);
    if (el) {
        el.remove();
        renumerarAnunciosTree(ci);
    }
}

function renumerarAnunciosTree(ci) {
    const list = document.getElementById(`tree-anuncios-list-${ci}`);
    if (!list) return;
    const anuncios = list.querySelectorAll(".cm-anuncio");
    if (anuncios.length === 0) {
        list.innerHTML = `<p style="font-size:13px;color:var(--muted);padding:8px 4px">Sin anuncios. Agrega uno arriba.</p>`;
    } else {
        anuncios.forEach((el, i) => {
            el.id = `tree-anuncio-${ci}-${i}`;
            el.dataset.ai = i;
            const idx = el.querySelector(".cm-anuncio-idx");
            if (idx) idx.textContent = i + 1;
            const lbl = el.querySelector("span[style*='green']");
            if (lbl) lbl.textContent = `Anuncio ${i + 1}`;
            const removeBtn = el.querySelector(".cm-remove-btn");
            if (removeBtn) removeBtn.setAttribute("onclick", `eliminarAnuncio(${ci},${i})`);
        });
    }

    // Actualizar contador en lista izquierda
    const item = document.getElementById(`conj-item-${ci}`);
    if (item) {
        const sub = item.querySelector(".cm-tree-conj-item-sub");
        const n = anuncios.length;
        if (sub) sub.textContent = `${n} anuncio${n !== 1 ? "s" : ""}`;
    }
}

// ─────────────────────────────────────────────
// GUARDAR CAMPAÑA
// ─────────────────────────────────────────────
function guardarCampana() {
    // Sincronizar panel activo antes de leer
    if (_conjuntoActivo !== null) guardarCambiosPanelActivo();

    const nombre = document.getElementById("input-nombre-campana").value.trim();
    if (!nombre) return mostrarToast("Ingresa el nombre de la campaña", "error");

    const conjuntos = [];
    let valido = true;

    _conjuntosData.forEach((conj, i) => {
        if (!conj.nombre) {
            mostrarToast(`El conjunto ${i + 1} no tiene nombre`, "error");
            valido = false;
            return;
        }

        // Leer anuncios del DOM si es el activo, sino usar los guardados en memoria
        let anunciosData = conj.anunciosData;
        if (_conjuntoActivo === conj.ci) {
            const list = document.getElementById(`tree-anuncios-list-${conj.ci}`);
            if (list) {
                anunciosData = [];
                list.querySelectorAll(".cm-anuncio").forEach((anEl) => {
                    anunciosData.push({
                        name    : anEl.querySelector(".tree-an-name")?.value     || "",
                        nombre  : anEl.querySelector(".tree-an-nombre")?.value   || "",
                        etiqueta: anEl.querySelector(".tree-an-etiqueta")?.value || ""
                    });
                });
            }
        }

        conjuntos.push({
            name   : conj.name,
            nombre : conj.nombre,
            valor  : conj.valor || 0,
            anuncios: anunciosData.map(a => ({
                name    : a.name,
                nombre  : a.nombre,
                etiqueta: a.etiqueta
            }))
        });
    });

    if (!valido) return;

    const btnGuardar = document.querySelector("#modal-campana .cm-btn-primary");
    btnGuardar.disabled = true;
    btnGuardar.innerHTML = '<i data-lucide="loader-2" class="cm-spin"></i> Guardando...';
    lucide.createIcons();

    const objetivo = document.getElementById("input-objetivo-campana").value;

    const nombreOriginal = document.getElementById("input-campana-original").value.trim();

    frappe.call({
        method: "marketinghub.www.campanas_meta.index.guardar_campana",
        args: {
            nombre: nombre,
            objetivo: objetivo,
            conjuntos_json: JSON.stringify(conjuntos),
            nombre_original: nombreOriginal
        },
        callback: function (r) {
            if (r.message && r.message.status === "ok") {
                cerrarModal("modal-campana");
                mostrarLogGuardado(r.message.log || []);
                cargarCampanas();
            } else if (r.message && r.message.status === "error") {
                cerrarModal("modal-campana");
                mostrarLogGuardado(r.message.log || []);
            } else {
                mostrarToast("Error al guardar la campaña", "error");
            }
        },
        error: function (err) {
            mostrarToast(err?.message || "Error al guardar", "error");
        },
        always: function () {
            btnGuardar.disabled = false;
            btnGuardar.innerHTML = '<i data-lucide="save"></i> Guardar Campaña';
            lucide.createIcons();
        }
    });
}

// ─────────────────────────────────────────────
// ELIMINAR CAMPAÑA
// ─────────────────────────────────────────────
function eliminarCampana(nombreEncoded) {
    const nombre = decodeURIComponent(nombreEncoded);
    if (!confirm(`¿Eliminar la campaña "${nombre}"? Esta acción no se puede deshacer.`)) return;

    frappe.call({
        method: "marketinghub.www.campanas_meta.index.eliminar_campana",
        args: { nombre: nombre },
        callback: function (r) {
            if (r.message && r.message.status === "ok") {
                mostrarToast("Campaña eliminada", "success");
                cargarCampanas();
            } else {
                mostrarToast("Error al eliminar", "error");
            }
        },
        error: function () {
            mostrarToast("Error al eliminar la campaña", "error");
        }
    });
}

// ─────────────────────────────────────────────
// VER FICHA (solo lectura)
// ─────────────────────────────────────────────
function verFicha(nombreEncoded) {
    const nombre = decodeURIComponent(nombreEncoded);
    const campana = _campanas.find(c => c.nombre === nombre);
    if (!campana) return mostrarToast("Campaña no encontrada", "error");

    const contenido = document.getElementById("ficha-contenido");

    // Recopilar etiquetas únicas de todos los anuncios
    const etiquetasSet = new Set();
    (campana.conjuntos || []).forEach(conj => {
        (conj.anuncios || []).forEach(a => { if (a.etiqueta) etiquetasSet.add(a.etiqueta); });
    });
    const etiquetas = [...etiquetasSet];

    const conjuntosHtml = (campana.conjuntos || []).length
        ? campana.conjuntos.map((conj, ci) => {
            const anunciosHtml = (conj.anuncios || []).length
                ? conj.anuncios.map(a => `
                    <div class="cm-ficha-anuncio">
                        <h5>${escHtml(a.nombre || "(sin nombre)")}</h5>
                        ${a.etiqueta ? `<span class="cm-tag"><i data-lucide="tag"></i> ${escHtml(a.etiqueta)}</span>` : ""}
                        ${a.etiqueta ? `<div class="cm-ficha-leads" data-etiqueta="${escHtml(a.etiqueta)}">
                            <div class="cm-ficha-leads-loading"><i data-lucide="loader-2" class="cm-spin"></i> Cargando leads...</div>
                        </div>` : ""}
                    </div>`).join("")
                : `<p style="font-size:13px;color:var(--muted);padding:8px 0">Sin anuncios</p>`;

            return `
            <div class="cm-ficha-conjunto">
                <div class="cm-ficha-conjunto-header">
                    <div class="cm-conjunto-idx">${ci + 1}</div>
                    <h4>${escHtml(conj.nombre || "(sin nombre)")}</h4>
                    ${conj.valor ? `<span class="cm-ficha-valor">Presupuesto: <strong>S/ ${Number(conj.valor).toFixed(2)}</strong></span>` : ""}
                </div>
                <div class="cm-ficha-conjunto-body">
                    ${anunciosHtml}
                </div>
            </div>`;
        }).join("")
        : `<p style="font-size:14px;color:var(--muted)">Sin conjuntos de anuncios</p>`;

    contenido.innerHTML = `
    <div class="cm-ficha-campana">
        <div class="cm-ficha-titulo">${escHtml(campana.nombre)}</div>
        ${conjuntosHtml}
    </div>`;

    abrirModal("modal-ficha");
    lucide.createIcons();

    // Cargar leads por etiqueta si hay etiquetas en la campaña
    if (etiquetas.length === 0) return;
    frappe.call({
        method: "marketinghub.www.campanas_meta.index.obtener_leads_por_etiquetas",
        args: { etiquetas_json: JSON.stringify(etiquetas) },
        callback: function(r) {
            const leadsData = r.message || {};
            contenido.querySelectorAll(".cm-ficha-leads").forEach(el => {
                const etiqueta = el.dataset.etiqueta;
                const leads = leadsData[etiqueta] || [];
                if (leads.length === 0) {
                    el.innerHTML = `<p class="cm-ficha-leads-empty"><i data-lucide="inbox"></i> Sin leads con esta etiqueta</p>`;
                } else {
                    el.innerHTML = `
                    <button class="cm-ficha-leads-header" onclick="toggleLeadsList(this)" type="button">
                        <i data-lucide="users"></i>
                        <span>${leads.length} lead${leads.length !== 1 ? "s" : ""} con esta etiqueta</span>
                        <i data-lucide="chevron-down" class="cm-leads-chevron"></i>
                    </button>
                    <div class="cm-ficha-leads-list">
                        ${leads.map(l => `
                        <div class="cm-ficha-lead-item">
                            <div class="cm-ficha-lead-avatar">${escHtml((l.lead_name || "?")[0].toUpperCase())}</div>
                            <div class="cm-ficha-lead-info">
                                <span class="cm-ficha-lead-name">${escHtml(l.lead_name || "(sin nombre)")}</span>
                                ${l.mobile_no ? `<span class="cm-ficha-lead-phone"><i data-lucide="phone"></i> ${escHtml(l.mobile_no)}</span>` : ""}
                            </div>
                            <span class="cm-ficha-lead-date">${_formatLeadDate(l.creation)}</span>
                        </div>`).join("")}
                    </div>`;
                }
                lucide.createIcons({ nodes: [el] });
            });
        }
    });
}

function toggleLeadsList(header) {
    const list = header.nextElementSibling;
    const chevron = header.querySelector(".cm-leads-chevron");
    const isOpen = list.classList.contains("open");
    list.classList.toggle("open", !isOpen);
    if (chevron) chevron.style.transform = isOpen ? "" : "rotate(180deg)";
}

function _formatLeadDate(creation) {
    if (!creation) return "";
    const d = new Date(creation);
    return d.toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" });
}

// ─────────────────────────────────────────────
// SINCRONIZACIÓN DESDE META
// ─────────────────────────────────────────────
async function abrirModalSincronizar() {
    const sel = document.getElementById("sync-account-select");
    const result = document.getElementById("sync-result");
    if (result) { result.style.display = "none"; result.textContent = ""; }
    sel.innerHTML = '<option value="">Cargando cuentas...</option>';
    sel.disabled = true;
    abrirModal("modal-sincronizar");

    try {
        const data = await new Promise((resolve, reject) => {
            frappe.call({
                method: "marketinghub.api.meta_ads.get_ad_accounts",
                callback: r => r.exc ? reject(r.exc) : resolve(r.message || [])
            });
        });
        if (!data.length) {
            sel.innerHTML = '<option value="">Sin cuentas disponibles</option>';
        } else {
            sel.innerHTML = data.map(a =>
                `<option value="${escHtml(a.account_id)}">${escHtml(a.name)} (${escHtml(a.account_id)})</option>`
            ).join("");
        }
    } catch (e) {
        sel.innerHTML = '<option value="">Error al cargar cuentas</option>';
    } finally {
        sel.disabled = false;
    }
}

async function ejecutarSincronizacion() {
    const sel = document.getElementById("sync-account-select");
    const btn = document.getElementById("sync-btn");
    const result = document.getElementById("sync-result");
    const accountId = sel.value;
    if (!accountId) { mostrarToast("Selecciona una cuenta primero", "error"); return; }

    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="cm-spin"></i> Sincronizando...';
    lucide.createIcons({ nodes: [btn] });
    result.style.display = "none";

    try {
        const data = await new Promise((resolve, reject) => {
            frappe.call({
                method: "marketinghub.api.meta_ads.sincronizar_campanas",
                args: { account_id: accountId },
                callback: r => r.exc ? reject(r.exc) : resolve(r.message || {})
            });
        });

        const { creadas = 0, actualizadas = 0, omitidas = 0, errores = [] } = data;
        const hasErrors = errores.length > 0;

        result.style.display = "block";
        result.style.background = hasErrors ? "var(--warning-bg, #fff8e1)" : "var(--success-bg, #e8f5e9)";
        result.style.border = `1px solid ${hasErrors ? "#ffc107" : "#4caf50"}`;
        result.style.color = hasErrors ? "#5f4500" : "#1b5e20";
        result.innerHTML = `
            <strong>${creadas} creadas · ${actualizadas} actualizadas · ${omitidas} omitidas</strong>
            ${errores.length ? `<ul style="margin:8px 0 0; padding-left:18px;">${errores.map(e => `<li>${escHtml(e)}</li>`).join("")}</ul>` : ""}
        `;

        mostrarToast(`Sincronización completa: ${creadas} creadas, ${actualizadas} actualizadas`, hasErrors ? "warning" : "success");
        cargarCampanas();
    } catch (e) {
        result.style.display = "block";
        result.style.background = "#fdecea";
        result.style.border = "1px solid #ef5350";
        result.style.color = "#7f0000";
        result.textContent = `Error: ${typeof e === "string" ? e : JSON.stringify(e)}`;
        mostrarToast("Error al sincronizar", "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="refresh-cw"></i> Sincronizar';
        lucide.createIcons({ nodes: [btn] });
    }
}

// ─────────────────────────────────────────────
// UTILIDADES
// ─────────────────────────────────────────────
const _ESTADO_LABEL = {
    ACTIVE: "Activa", PAUSED: "Pausada", CAMPAIGN_PAUSED: "Pausada (campaña)",
    ADSET_PAUSED: "Pausada (conjunto)", DELETED: "Eliminada", ARCHIVED: "Archivada",
    IN_PROCESS: "En proceso", WITH_ISSUES: "Con problemas", DISAPPROVED: "Desaprobada"
};
const _ESTADO_CLASS = {
    ACTIVE: "cm-estado-active", PAUSED: "cm-estado-paused",
    CAMPAIGN_PAUSED: "cm-estado-paused", ADSET_PAUSED: "cm-estado-paused",
    DELETED: "cm-estado-deleted", ARCHIVED: "cm-estado-deleted",
    WITH_ISSUES: "cm-estado-warning", DISAPPROVED: "cm-estado-warning",
    IN_PROCESS: "cm-estado-info"
};
function _estadoBadge(estado) {
    if (!estado) return '<span style="color:var(--text-muted);font-size:12px;">—</span>';
    const label = _ESTADO_LABEL[estado] || estado;
    const cls = _ESTADO_CLASS[estado] || "";
    return `<span class="cm-estado-badge ${cls}">${escHtml(label)}</span>`;
}

function escHtml(str) {
    if (str == null) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function mostrarLogGuardado(log) {
    if (!log || !log.length) {
        mostrarToast("Campaña guardada correctamente", "success");
        return;
    }
    const errores = log.filter(l => l.tipo === "error").length;
    const warns = log.filter(l => l.tipo === "warn").length;
    const oks = log.filter(l => l.tipo === "ok").length;

    const iconMap = { ok: "check-circle", error: "x-circle", warn: "alert-triangle" };
    const colorMap = { ok: "#16a34a", error: "#dc2626", warn: "#d97706" };

    let html = `<div style="display:flex;gap:12px;margin-bottom:14px;">
        <span style="color:#16a34a;font-size:13px;font-weight:600;"><i data-lucide="check-circle" style="width:14px;height:14px;vertical-align:-2px;margin-right:3px;"></i>${oks} OK</span>
        <span style="color:#d97706;font-size:13px;font-weight:600;"><i data-lucide="alert-triangle" style="width:14px;height:14px;vertical-align:-2px;margin-right:3px;"></i>${warns} Avisos</span>
        <span style="color:#dc2626;font-size:13px;font-weight:600;"><i data-lucide="x-circle" style="width:14px;height:14px;vertical-align:-2px;margin-right:3px;"></i>${errores} Errores</span>
    </div>`;

    html += '<div style="display:flex;flex-direction:column;gap:6px;">';
    log.forEach(l => {
        const icon = iconMap[l.tipo] || "info";
        const color = colorMap[l.tipo] || "#6b7280";
        const urlLink = l.url ? ` <a href="${escHtml(l.url)}" target="_blank" style="color:#2563eb;text-decoration:underline;white-space:nowrap;"><i data-lucide="external-link" style="width:12px;height:12px;vertical-align:-1px;"></i> Editar en Meta</a>` : '';
        html += `<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 10px;border-radius:6px;background:${l.tipo === 'error' ? '#fef2f2' : l.tipo === 'warn' ? '#fffbeb' : '#f0fdf4'};font-size:13px;">
            <i data-lucide="${icon}" style="width:15px;height:15px;color:${color};flex-shrink:0;margin-top:1px;"></i>
            <span style="color:#1f2937;">${escHtml(l.msg)}${urlLink}</span>
        </div>`;
    });
    html += '</div>';

    document.getElementById("modal-log-contenido").innerHTML = html;
    const titulo = document.getElementById("modal-log-titulo");
    if (errores > 0) {
        titulo.innerHTML = '<i data-lucide="alert-triangle"></i> Guardado con errores';
    } else if (warns > 0) {
        titulo.innerHTML = '<i data-lucide="clipboard-list"></i> Guardado con avisos';
    } else {
        titulo.innerHTML = '<i data-lucide="check-circle"></i> Guardado correctamente';
    }
    abrirModal("modal-log");
}

function mostrarToast(msg, tipo) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.className = "cm-toast show" + (tipo ? " " + tipo : "");
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => {
        toast.classList.remove("show");
    }, 3200);
}
