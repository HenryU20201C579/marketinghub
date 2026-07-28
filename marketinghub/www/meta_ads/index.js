// Global elements and state
let els = {};
const state = {
  token: '',
  accounts: [],
  rows: [],
  activeRow: null,
  chart: null,
  mChart: null,
  sort: { key: 'ventas', dir: -1 },
  onlyActive: false,
  statusFilter: '',
  nameSearch: '',
  drillCampaign: null,
  drillAdset: null,
  drillAd: null,
  activeTab: 'campaign',
  selectedCampaigns: [], // [{ id, name }, ...]
  selectedAdsets: [],    // [{ id, name }, ...]
  etiquetaFilter: '',
  mainEtiquetasSelected: [],
  mainFilterMode: 'OR',
  leadEtiquetasSelected: [],
  leadFilterMode: 'OR',
  erpMapping: { adMap: {}, adsetMap: {}, campMap: {} },
  leadCountByRow: { adLeadCount: {}, adsetLeadCount: {}, campLeadCount: {} },
  leadCountTotalByRow: null,
  filteredLeadCountByRow: {},
  salesDataByRow: { adSales: {}, adsetSales: {}, campSales: {} },
  rowEtiquetas: {},
  leadsData: null,
  // Stored for sales reload
  _salesEtiquetas: new Set(),
  _salesAdMap: {},
  _salesAdsetEtiquetas: {},
  _salesCampEtiquetas: {},
  campanasData: [],     // Full hierarchy from obtener_campanas
  etiquetasLead: []     // Available lead tags
};

function money(n) { return new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(n || 0); }
function integer(n) { return new Intl.NumberFormat('es-PE').format(Math.round(n || 0)); }
function float(n) { return new Intl.NumberFormat('es-PE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(n || 0); }
const STATUS_LABEL = { ACTIVE: 'Activa', PAUSED: 'Pausada', DELETED: 'Eliminada', ARCHIVED: 'Archivada', IN_PROCESS: 'En proceso', WITH_ISSUES: 'Con problemas' };
const STATUS_CLASS = { ACTIVE: 'status-success', PAUSED: 'status-paused', WITH_ISSUES: 'status-warning' };
function statusBadge(s) { return `<span class="status-badge ${STATUS_CLASS[s] || ''}">${STATUS_LABEL[s] || s}</span>`; }

// ── Floating tooltip system ──
const floatingTooltip = (() => {
  let el = null;
  function ensure() {
    if (el) return el;
    el = document.createElement('div');
    el.className = 'floating-tooltip';
    document.body.appendChild(el);
    return el;
  }
  function show(anchor, html) {
    const tt = ensure();
    tt.innerHTML = html;
    tt.classList.remove('arrow-top', 'arrow-bottom');
    tt.classList.add('visible');
    // position after content is set so we get correct dimensions
    requestAnimationFrame(() => position(anchor, tt));
  }
  function position(anchor, tt) {
    const r = anchor.getBoundingClientRect();
    const tw = tt.offsetWidth, th = tt.offsetHeight;
    const gap = 8;
    let top, left;
    // prefer below
    if (r.bottom + gap + th < window.innerHeight) {
      top = r.bottom + gap;
      tt.classList.add('arrow-top');
    } else {
      top = r.top - gap - th;
      tt.classList.add('arrow-bottom');
    }
    left = r.left + r.width / 2 - tw / 2;
    // clamp horizontal
    if (left < 8) left = 8;
    if (left + tw > window.innerWidth - 8) left = window.innerWidth - 8 - tw;
    // arrow position relative to tooltip
    const arrowX = Math.max(12, Math.min(tw - 12, r.left + r.width / 2 - left));
    tt.style.left = left + 'px';
    tt.style.top = top + 'px';
    tt.style.setProperty('--arrow-x', arrowX + 'px');
  }
  function hide() {
    if (el) el.classList.remove('visible');
  }
  return { show, hide };
})();

// Bind tooltip triggers (call after DOM updates)
function bindTooltips(container) {
  container = container || document;
  // Header & stat tooltips (? triggers)
  container.querySelectorAll('.th-tooltip-trigger, .stat-tooltip-trigger').forEach(trigger => {
    const tooltipEl = trigger.nextElementSibling;
    if (!tooltipEl) return;
    const html = tooltipEl.innerHTML;
    // hide the old inline tooltip
    tooltipEl.style.display = 'none';
    trigger.addEventListener('mouseenter', () => floatingTooltip.show(trigger, html));
    trigger.addEventListener('mouseleave', () => floatingTooltip.hide());
  });
  // Value tooltips
  container.querySelectorAll('[data-vtooltip]').forEach(el => {
    el.addEventListener('mouseenter', () => floatingTooltip.show(el, el.getAttribute('data-vtooltip')));
    el.addEventListener('mouseleave', () => floatingTooltip.hide());
  });
}

// Generate value tooltip HTML for metrics
function buildValueTooltip(type, data) {
  if (!data) return '';
  switch (type) {
    case 'roas': {
      const { ingresos, spend, value } = data;
      const ratio = value;
      const profit = ingresos - spend;
      const isProfit = profit >= 0;
      let verdictClass = 'bad', verdictText = 'Bajo: estás perdiendo dinero en publicidad';
      if (ratio >= 3) { verdictClass = 'good'; verdictText = 'Excelente: alta rentabilidad publicitaria'; }
      else if (ratio >= 1) { verdictClass = 'neutral'; verdictText = 'Moderado: cubre costos pero el margen es bajo'; }
      return `<div class="tt-label">ROAS — Retorno de Inversión Publicitaria</div>`
        + `<div class="tt-formula">${money(ingresos)} ingresos ÷ ${money(spend)} invertido = <strong>${float(ratio)}x</strong></div>`
        + `<div style="margin:6px 0;font-size:0.72rem;">Por cada <strong>S/ 1</strong> invertido, se generaron <strong>S/ ${float(ratio)}</strong> en ventas.</div>`
        + `<div style="margin:4px 0;padding:6px 10px;border-radius:6px;font-size:0.74rem;font-weight:600;background:${isProfit ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'};border:1px solid ${isProfit ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'};color:${isProfit ? '#6ee7b7' : '#fca5a5'};">`
        + `${isProfit ? '📈 Ganancia' : '📉 Pérdida'}: <strong>${money(Math.abs(profit))}</strong>`
        + `<div style="font-weight:400;font-size:0.68rem;margin-top:2px;opacity:0.85;">${money(ingresos)} ingresos − ${money(spend)} inversión</div></div>`
        + `<div class="tt-verdict ${verdictClass}">${verdictText}</div>`;
    }
    case 'cpa': {
      const { spend, ventas, ingresos, value } = data;
      const profit = (ingresos || 0) - spend;
      const isProfit = profit >= 0;
      const ticketPromedio = (ingresos && ventas > 0) ? ingresos / ventas : 0;
      let verdictClass = 'neutral', verdictText = 'Valor referencial — compara con tu ticket promedio';
      if (ticketPromedio > 0 && value < ticketPromedio * 0.3) { verdictClass = 'good'; verdictText = 'Eficiente: el costo de adquisición es bajo vs. el ticket promedio'; }
      else if (ticketPromedio > 0 && value > ticketPromedio) { verdictClass = 'bad'; verdictText = 'Costoso: el costo de adquisición supera el ticket promedio'; }
      else if (value < 50) { verdictClass = 'good'; verdictText = 'Muy eficiente: bajo costo por conversión'; }
      else if (value > 200) { verdictClass = 'bad'; verdictText = 'Costoso: cada venta requiere mucha inversión'; }
      let html = `<div class="tt-label">Costo por Venta</div>`
        + `<div class="tt-formula">${money(spend)} ÷ ${ventas} venta${ventas !== 1 ? 's' : ''} = <strong>${money(value)}</strong></div>`
        + `<div style="margin:4px 0;font-size:0.72rem;">Se gastaron <strong>${money(spend)}</strong> en publicidad para conseguir <strong>${ventas}</strong> venta${ventas !== 1 ? 's' : ''}.</div>`;
      if (ticketPromedio > 0) {
        html += `<div style="margin:4px 0;font-size:0.72rem;">Ticket promedio por venta: <strong>${money(ticketPromedio)}</strong></div>`;
      }
      if (ingresos > 0) {
        html += `<div style="margin:4px 0;padding:6px 10px;border-radius:6px;font-size:0.74rem;font-weight:600;background:${isProfit ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)'};border:1px solid ${isProfit ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'};color:${isProfit ? '#6ee7b7' : '#fca5a5'};">`
          + `${isProfit ? '📈 Ganancia' : '📉 Pérdida'}: <strong>${money(Math.abs(profit))}</strong>`
          + `<div style="font-weight:400;font-size:0.68rem;margin-top:2px;opacity:0.85;">${money(ingresos || 0)} ingresos − ${money(spend)} inversión</div></div>`;
      }
      html += `<div class="tt-verdict ${verdictClass}">${verdictText}</div>`;
      return html;
    }
    case 'cpr': {
      const { spend, results, value } = data;
      return `<div class="tt-label">Costo por Resultado</div>`
        + `<div class="tt-formula">${money(spend)} ÷ ${integer(results)} resultados = <strong>${money(value)}</strong></div>`
        + `<div style="margin:4px 0;font-size:0.72rem;">Cada conversión (lead, compra, clic, etc.) costó en promedio <strong>${money(value)}</strong>.</div>`;
    }
    case 'ctr': {
      const { clicks, impressions, value } = data;
      let verdictClass = 'bad', verdictText = 'Bajo: el anuncio no genera suficientes clics';
      if (value >= 2) { verdictClass = 'good'; verdictText = 'Bueno: el anuncio atrae bien la atención'; }
      else if (value >= 1) { verdictClass = 'neutral'; verdictText = 'Moderado: hay margen de mejora en el creativo'; }
      return `<div class="tt-label">CTR — Click-Through Rate</div>`
        + `<div class="tt-formula">${integer(clicks)} clics ÷ ${integer(impressions)} impresiones × 100 = <strong>${float(value)}%</strong></div>`
        + `<div style="margin:4px 0;font-size:0.72rem;">De cada 100 veces que se mostró el anuncio, <strong>${float(value)}</strong> personas hicieron clic.</div>`
        + `<div class="tt-verdict ${verdictClass}">${verdictText}</div>`;
    }
    case 'cpc': {
      const { spend, clicks, value } = data;
      let verdictClass = 'neutral', verdictText = 'Valor referencial — depende de tu industria';
      if (value < 0.5) { verdictClass = 'good'; verdictText = 'Muy barato: tráfico a bajo costo'; }
      else if (value > 3) { verdictClass = 'bad'; verdictText = 'Costoso: cada clic sale caro'; }
      return `<div class="tt-label">CPC — Costo por Clic</div>`
        + `<div class="tt-formula">${money(spend)} ÷ ${integer(clicks)} clics = <strong>${money(value)}</strong></div>`
        + `<div style="margin:4px 0;font-size:0.72rem;">Cada clic en el anuncio costó en promedio <strong>${money(value)}</strong>.</div>`
        + `<div class="tt-verdict ${verdictClass}">${verdictText}</div>`;
    }
    default: return '';
  }
}

async function init() {
  // Initialize elements once DOM is ready
  els = {
    accountSelect: document.getElementById('accountSelect'),
    dateFrom: document.getElementById('dateFrom'),
    dateTo: document.getElementById('dateTo'),
    levelSelect: document.getElementById('levelSelect'),
    loadBtn: document.getElementById('loadBtn'),
    accountsBtn: document.getElementById('accountsBtn'),
    tableBody: document.getElementById('tableBody'),
    mobileList: document.getElementById('mobileList'),
    rowCountBadge: document.getElementById('rowCountBadge'),
    sidebarStatus: document.getElementById('sidebarStatus'),
    mSpend: document.getElementById('mSpend'),
    mImpressions: document.getElementById('mImpressions'),
    mClicks: document.getElementById('mClicks'),
    mResults: document.getElementById('mResults'),
    dName: document.getElementById('dName'),
    dStatus: document.getElementById('dStatus'),
    dObjective: document.getElementById('dObjective'),
    dRange: document.getElementById('dRange'),
    mobileModal: document.getElementById('mobileModal'),
    mDName: document.getElementById('mDName'),
    mDStatus: document.getElementById('mDStatus'),
    mDObjective: document.getElementById('mDObjective'),
    mDRange: document.getElementById('mDRange'),
    actionList: document.getElementById('actionList'),
    mActionList: document.getElementById('mActionList'),
    rawJson: document.getElementById('rawJson'),
    trendChartCtx: document.getElementById('trendChart') ? document.getElementById('trendChart').getContext('2d') : null,
    mTrendChartCtx: document.getElementById('mTrendChart') ? document.getElementById('mTrendChart').getContext('2d') : null,
    filterPanel: document.getElementById('filterPanel'),
    toggleFilters: document.getElementById('toggleFilters'),
    customToken: document.getElementById('customToken'),
    setTokenBtn: document.getElementById('setTokenBtn'),
    onlyActiveFilter: document.getElementById('onlyActiveFilter'),
    statusFilter: document.getElementById('statusFilter'),
    accountFilterInline: document.getElementById('accountFilterInline'),
    nameSearch: document.getElementById('nameSearch'),
    toggleDetailBtn: document.getElementById('toggleDetailBtn'),
    detailColumn: document.getElementById('detailColumn'),
    breadcrumb: document.getElementById('breadcrumb'),
    breadcrumbBack: document.getElementById('breadcrumbBack'),
    breadcrumbCampaigns: document.getElementById('breadcrumbCampaigns'),
    breadcrumbCampaignName: document.getElementById('breadcrumbCampaignName'),
    breadcrumbName: document.getElementById('breadcrumbName'),
    breadcrumbSep2: document.getElementById('breadcrumbSep2'),
    breadcrumbSep3: document.getElementById('breadcrumbSep3'),
    breadcrumbSep4: document.getElementById('breadcrumbSep4'),
    breadcrumbAdName: document.getElementById('breadcrumbAdName'),
    leadsTableWrap: document.getElementById('leadsTableWrap'),
    leadsTableBody: document.getElementById('leadsTableBody'),
    mainTableScroll: document.getElementById('mainTableScroll'),
  };

  // Initialize date inputs with last 7 days
  if (els.dateFrom && !els.dateFrom.value) {
    const today = new Date();
    const from = new Date(today); from.setDate(from.getDate() - 7);
    els.dateFrom.value = from.toISOString().split('T')[0];
    els.dateTo.value = today.toISOString().split('T')[0];
  }

  // Bind events
  if(els.loadBtn) els.loadBtn.onclick = loadData;
  if(els.accountSelect) els.accountSelect.onchange = () => {
    if(els.accountFilterInline) els.accountFilterInline.value = els.accountSelect.value;
  };
  if(els.accountsBtn) els.accountsBtn.onclick = loadAccounts;
  if(els.toggleFilters) els.toggleFilters.onclick = () => els.filterPanel.classList.toggle('hidden');
  if(els.toggleDetailBtn) els.toggleDetailBtn.onclick = () => {
    const nowHidden = els.detailColumn.classList.toggle('hidden');
    document.getElementById('contentGrid').classList.toggle('detail-hidden', nowHidden);
    els.toggleDetailBtn.textContent = nowHidden ? 'Ver detalle' : 'Ocultar detalle';
  };

  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.onclick = () => switchTab(btn.dataset.tab);
  });

  const clearCampaign = document.getElementById('clearCampaign');
  const clearAdset = document.getElementById('clearAdset');
  if (clearCampaign) clearCampaign.onclick = (e) => { e.stopPropagation(); state.selectedCampaigns = []; updateTabBadges(); applyFiltersAndSort(); };
  if (clearAdset) clearAdset.onclick = (e) => { e.stopPropagation(); state.selectedAdsets = []; updateTabBadges(); applyFiltersAndSort(); };

  const selectAllChk = document.getElementById('selectAllChk');
  if (selectAllChk) selectAllChk.onchange = (e) => {
    const visibleRows = state.rows.filter(r => !state.onlyActive || r.status === 'ACTIVE');
    toggleSelectAll(e.target.checked, visibleRows);
  };

  if(els.onlyActiveFilter) els.onlyActiveFilter.onchange = () => {
    state.onlyActive = els.onlyActiveFilter.checked;
    if (state.onlyActive) { state.statusFilter = 'ACTIVE'; if(els.statusFilter) els.statusFilter.value = 'ACTIVE'; }
    applyFiltersAndSort();
  };

  if(els.statusFilter) els.statusFilter.onchange = () => {
    state.statusFilter = els.statusFilter.value;
    state.onlyActive = state.statusFilter === 'ACTIVE';
    applyFiltersAndSort();
  };

  if(els.nameSearch) els.nameSearch.oninput = () => {
    state.nameSearch = els.nameSearch.value.trim().toLowerCase();
    applyFiltersAndSort();
  };

  const etiquetaFilterEl = document.getElementById('etiquetaFilter');
  if (etiquetaFilterEl) etiquetaFilterEl.onchange = () => {
    state.etiquetaFilter = etiquetaFilterEl.value;
    applyFiltersAndSort();
  };

  const btnOr = document.getElementById('leadFilterOr');
  const btnAnd = document.getElementById('leadFilterAnd');
  if (btnOr) btnOr.onclick = () => setLeadFilterMode('OR');
  if (btnAnd) btnAnd.onclick = () => setLeadFilterMode('AND');

  const mainBtnOr = document.getElementById('mainFilterOr');
  const mainBtnAnd = document.getElementById('mainFilterAnd');
  if (mainBtnOr) mainBtnOr.onclick = () => setMainFilterMode('OR');
  if (mainBtnAnd) mainBtnAnd.onclick = () => setMainFilterMode('AND');

  if(els.accountFilterInline) els.accountFilterInline.onchange = () => {
    if(els.accountSelect) els.accountSelect.value = els.accountFilterInline.value;
    loadData();
  };

  // Sorting por columna
  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.onclick = () => {
      const key = th.dataset.sort;
      if (state.sort.key === key) {
        state.sort.dir *= -1;
      } else {
        state.sort.key = key;
        state.sort.dir = -1; // primera vez: mayor a menor
      }
      applyFiltersAndSort();
    };
  });

  if(els.dateFrom) els.dateFrom.onchange = () => loadData(true);
  if(els.dateTo) els.dateTo.onchange = () => loadData(true);
  
  if(els.setTokenBtn) {
    els.setTokenBtn.onclick = () => {
      const val = els.customToken.value.trim();
      if(val) {
        state.token = val;
        loadAccounts();
        alert("Token externo activado para esta sesión");
      }
    };
  }

  try {
    const res = await fetch('/api/method/marketinghub.api.meta_ads.get_meta_token');
    const data = await res.json();
    if (data.message) {
      state.token = data.message;
      await loadAccounts();
    } else {
      setError("No se encontró token en Configuración Meta");
    }
  } catch (e) {
    setError("Error de conexión con el servidor");
  }

  loadErpMapping();
  loadAllLeadEtiquetas();

  // Bind floating tooltips for header ? icons and stat cards
  bindTooltips(document);
}

async function loadErpMapping() {
  try {
    const data = await new Promise(resolve => {
      frappe.call({
        method: 'marketinghub.www.campanas_meta.index.obtener_campanas',
        callback: r => resolve(r.message || [])
      });
    });

    state.campanasData = data; // Store full hierarchy for edit modal

    const adMap = {}, adsetMap = {}, campMap = {};
    const etiquetas = new Set();
    // etiquetas por adset/campaign para calcular conteos sin duplicar
    const adsetEtiquetas = {}, campEtiquetas = {};

    for (const camp of data) {
      for (const conj of camp.conjuntos || []) {
        for (const an of conj.anuncios || []) {
          if (an.meta_id && an.etiqueta) {
            adMap[an.meta_id] = an.etiqueta;
            etiquetas.add(an.etiqueta);
            if (!adsetMap[an.etiqueta]) adsetMap[an.etiqueta] = new Set();
            adsetMap[an.etiqueta].add(conj.meta_id);
            if (!campMap[an.etiqueta]) campMap[an.etiqueta] = new Set();
            campMap[an.etiqueta].add(camp.meta_id);
            // mapas inversos (meta_id → etiquetas únicas)
            if (conj.meta_id) {
              if (!adsetEtiquetas[conj.meta_id]) adsetEtiquetas[conj.meta_id] = new Set();
              adsetEtiquetas[conj.meta_id].add(an.etiqueta);
            }
            if (camp.meta_id) {
              if (!campEtiquetas[camp.meta_id]) campEtiquetas[camp.meta_id] = new Set();
              campEtiquetas[camp.meta_id].add(an.etiqueta);
            }
          }
        }
      }
    }

    state.erpMapping = { adMap, adsetMap, campMap };
    // Store row-level etiquetas for filtered counts
    state.rowEtiquetas = { ...adsetEtiquetas, ...campEtiquetas };
    for (const [adMetaId, etiqueta] of Object.entries(adMap)) {
      state.rowEtiquetas[adMetaId] = new Set([etiqueta]);
    }

    // Fetch conteos de leads por etiqueta y calcular por fila
    if (etiquetas.size) {
      try {
        const etiquetasJson = encodeURIComponent(JSON.stringify([...etiquetas]));
        const { from: lcFrom, to: lcTo } = getDateRange();
        const hasDateFilter = lcFrom || lcTo;

        // Fetch total (sin filtro de fecha) y filtrado en paralelo
        const totalUrl = `/api/method/marketinghub.api.meta_ads.get_lead_counts_por_etiquetas?etiquetas_json=${etiquetasJson}`;
        let filteredUrl = totalUrl;
        if (lcFrom) filteredUrl += `&date_from=${lcFrom}`;
        if (lcTo) filteredUrl += `&date_to=${lcTo}`;

        const headers = { 'X-Frappe-CSRF-Token': frappe.csrf_token };
        const [totalRes, filteredRes] = await Promise.all([
          fetch(totalUrl, { headers }),
          hasDateFilter ? fetch(filteredUrl, { headers }) : Promise.resolve(null)
        ]);
        const totalByEtiqueta = (await totalRes.json()).message || {};
        const filteredByEtiqueta = filteredRes ? ((await filteredRes.json()).message || {}) : totalByEtiqueta;

        const buildCounts = (byEtiqueta) => {
          const ad = {}, adset = {}, camp = {};
          for (const [adMetaId, etiqueta] of Object.entries(adMap)) {
            ad[adMetaId] = byEtiqueta[etiqueta] || 0;
          }
          for (const [adsetMetaId, ets] of Object.entries(adsetEtiquetas)) {
            adset[adsetMetaId] = [...ets].reduce((s, e) => s + (byEtiqueta[e] || 0), 0);
          }
          for (const [campMetaId, ets] of Object.entries(campEtiquetas)) {
            camp[campMetaId] = [...ets].reduce((s, e) => s + (byEtiqueta[e] || 0), 0);
          }
          return { adLeadCount: ad, adsetLeadCount: adset, campLeadCount: camp };
        };

        state.leadCountTotalByRow = buildCounts(totalByEtiqueta);
        state.leadCountByRow = buildCounts(filteredByEtiqueta);
        // Re-renderizar si ya hay datos cargados
        if (state.rows.length) applyFiltersAndSort();
      } catch (_) { /* silently ignore */ }

      // Store mappings for sales reload
      state._salesEtiquetas = etiquetas;
      state._salesAdMap = adMap;
      state._salesAdsetEtiquetas = adsetEtiquetas;
      state._salesCampEtiquetas = campEtiquetas;
      // Cargar datos de ventas e ingresos por etiqueta
      await fetchSalesData(etiquetas, adMap, adsetEtiquetas, campEtiquetas);
    }

    const sel = document.getElementById('etiquetaFilter');
    if (sel && etiquetas.size) {
      const sorted = [...etiquetas].sort();
      sel.innerHTML = '<option value="">Todas las etiquetas</option>' +
        sorted.map(e => `<option value="${e}">${e}</option>`).join('');
    }
  } catch (_) { /* silently ignore */ }
}

function getDateRange() {
  return { from: els.dateFrom.value || '', to: els.dateTo.value || '' };
}

async function reloadErpData() {
  if (!state._salesEtiquetas || !state._salesEtiquetas.size) return;
  // Reload lead counts (total + filtrado por fecha)
  try {
    const etiquetasJson = encodeURIComponent(JSON.stringify([...state._salesEtiquetas]));
    const { from: lcFrom, to: lcTo } = getDateRange();
    const hasDateFilter = lcFrom || lcTo;

    const totalUrl = `/api/method/marketinghub.api.meta_ads.get_lead_counts_por_etiquetas?etiquetas_json=${etiquetasJson}`;
    let filteredUrl = totalUrl;
    if (lcFrom) filteredUrl += `&date_from=${lcFrom}`;
    if (lcTo) filteredUrl += `&date_to=${lcTo}`;

    const headers = { 'X-Frappe-CSRF-Token': frappe.csrf_token };
    const [totalRes, filteredRes] = await Promise.all([
      fetch(totalUrl, { headers }),
      hasDateFilter ? fetch(filteredUrl, { headers }) : Promise.resolve(null)
    ]);
    const totalByEtiqueta = (await totalRes.json()).message || {};
    const filteredByEtiqueta = filteredRes ? ((await filteredRes.json()).message || {}) : totalByEtiqueta;

    const buildCounts = (byEtiqueta) => {
      const ad = {}, adset = {}, camp = {};
      for (const [adMetaId, etiqueta] of Object.entries(state._salesAdMap)) {
        ad[adMetaId] = byEtiqueta[etiqueta] || 0;
      }
      for (const [adsetMetaId, ets] of Object.entries(state._salesAdsetEtiquetas)) {
        adset[adsetMetaId] = [...ets].reduce((s, e) => s + (byEtiqueta[e] || 0), 0);
      }
      for (const [campMetaId, ets] of Object.entries(state._salesCampEtiquetas)) {
        camp[campMetaId] = [...ets].reduce((s, e) => s + (byEtiqueta[e] || 0), 0);
      }
      return { adLeadCount: ad, adsetLeadCount: adset, campLeadCount: camp };
    };

    state.leadCountTotalByRow = buildCounts(totalByEtiqueta);
    state.leadCountByRow = buildCounts(filteredByEtiqueta);
  } catch (_) { /* silently ignore */ }
  // Reload sales data
  await fetchSalesData(state._salesEtiquetas, state._salesAdMap, state._salesAdsetEtiquetas, state._salesCampEtiquetas);
  // Reload filtered counts if active
  if (state.mainEtiquetasSelected.length) fetchFilteredCounts();
  else if (state.rows.length) applyFiltersAndSort();
}

async function fetchSalesData(etiquetas, adMap, adsetEtiquetas, campEtiquetas) {
  try {
    let url = `/api/method/marketinghub.api.meta_ads.get_sales_data_por_etiquetas?etiquetas_json=${encodeURIComponent(JSON.stringify([...etiquetas]))}`;
    const { from: df, to: dt } = getDateRange();
    if (df) url += `&date_from=${df}`;
    if (dt) url += `&date_to=${dt}`;
    const resSales = await fetch(url, { headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token } });
    const jsonSales = await resSales.json();
    const salesByEtiqueta = jsonSales.message || {};
    const adSales = {}, adsetSales = {}, campSales = {};
    for (const [adMetaId, etiqueta] of Object.entries(adMap)) {
      adSales[adMetaId] = salesByEtiqueta[etiqueta] || { ventas: 0, ingresos: 0 };
    }
    for (const [adsetMetaId, ets] of Object.entries(adsetEtiquetas)) {
      adsetSales[adsetMetaId] = [...ets].reduce(
        (acc, e) => { const d = salesByEtiqueta[e] || {}; acc.ventas += d.ventas || 0; acc.ingresos += d.ingresos || 0; return acc; },
        { ventas: 0, ingresos: 0 }
      );
    }
    for (const [campMetaId, ets] of Object.entries(campEtiquetas)) {
      campSales[campMetaId] = [...ets].reduce(
        (acc, e) => { const d = salesByEtiqueta[e] || {}; acc.ventas += d.ventas || 0; acc.ingresos += d.ingresos || 0; return acc; },
        { ventas: 0, ingresos: 0 }
      );
    }
    state.salesDataByRow = { adSales, adsetSales, campSales };
    addGhostRowsForSales();
    if (state.rows.length) applyFiltersAndSort();
  } catch (_) { /* silently ignore */ }
}

function addGhostRowsForSales() {
  const tab = state.activeTab;
  if (tab !== 'campaign' && tab !== 'adset' && tab !== 'ad') return;
  const sd = state.salesDataByRow || {};
  let salesMap;
  if (tab === 'campaign') salesMap = sd.campSales || {};
  else if (tab === 'adset') salesMap = sd.adsetSales || {};
  else salesMap = sd.adSales || {};

  const existingIds = new Set();
  for (const r of state.rows) existingIds.add(r.id);

  const nameMap = {};
  const statusMap = {};
  const camps = state.campanasData || [];
  for (const camp of camps) {
    if (tab === 'campaign' && camp.meta_id) {
      nameMap[camp.meta_id] = camp.nombre;
      statusMap[camp.meta_id] = camp.estado || '';
    }
    const conjuntos = camp.conjuntos || [];
    for (const conj of conjuntos) {
      if (tab === 'adset' && conj.meta_id) {
        nameMap[conj.meta_id] = conj.nombre;
        statusMap[conj.meta_id] = conj.estado || '';
      }
      const anuncios = conj.anuncios || [];
      for (const an of anuncios) {
        if (tab === 'ad' && an.meta_id) {
          nameMap[an.meta_id] = an.nombre;
          statusMap[an.meta_id] = an.estado || '';
        }
      }
    }
  }

  for (const metaId in salesMap) {
    const s = salesMap[metaId] || {};
    const ventas = s.ventas || 0;
    if (ventas > 0 && !existingIds.has(metaId) && nameMap[metaId]) {
      state.rows.push({
        id: metaId,
        name: nameMap[metaId],
        status: statusMap[metaId] || 'PAUSED',
        spend: 0,
        impressions: 0,
        clicks: 0,
        results: 0,
        reach: 0,
        ctr: 0,
        cpc: 0,
        cpr: 0,
        isGhost: true
      });
    }
  }
}

async function loadAllLeadEtiquetas() {
  try {
    const res = await fetch('/api/method/marketinghub.api.meta_ads.get_all_lead_etiquetas');
    const json = await res.json();
    const etiquetas = json.message || [];
    state.etiquetasLead = etiquetas;
    if (etiquetas.length) {
      renderMainEtiquetaChips(etiquetas);
    }
  } catch (_) { /* silently ignore */ }
}

function renderMainEtiquetaChips(etiquetas) {
  const container = document.getElementById('mainEtiquetaChips');
  if (!container) return;
  const selected = new Set(state.mainEtiquetasSelected);
  container.innerHTML = etiquetas.map(e => {
    const active = selected.has(e);
    return `<button class="main-etiqueta-chip ${active ? 'chip-active' : ''}" data-etiqueta="${e}">${e}</button>`;
  }).join('');
  container.querySelectorAll('.main-etiqueta-chip').forEach(chip => {
    chip.onclick = () => {
      const et = chip.dataset.etiqueta;
      const idx = state.mainEtiquetasSelected.indexOf(et);
      if (idx >= 0) state.mainEtiquetasSelected.splice(idx, 1);
      else state.mainEtiquetasSelected.push(et);
      chip.classList.toggle('chip-active', state.mainEtiquetasSelected.includes(et));
      fetchFilteredCounts();
    };
  });
}

function setMainFilterMode(mode) {
  state.mainFilterMode = mode;
  const btnOr = document.getElementById('mainFilterOr');
  const btnAnd = document.getElementById('mainFilterAnd');
  if (btnOr) {
    btnOr.style.background = mode === 'OR' ? 'var(--primary)' : '#fff';
    btnOr.style.color = mode === 'OR' ? '#fff' : 'var(--text)';
  }
  if (btnAnd) {
    btnAnd.style.background = mode === 'AND' ? 'var(--primary)' : '#fff';
    btnAnd.style.color = mode === 'AND' ? '#fff' : 'var(--text)';
  }
  fetchFilteredCounts();
}

async function fetchFilteredCounts() {
  if (!state.mainEtiquetasSelected.length || !Object.keys(state.rowEtiquetas).length) {
    state.filteredLeadCountByRow = {};
    if (state.rows.length) applyFiltersAndSort();
    return;
  }
  const rowEts = {};
  for (const [id, ets] of Object.entries(state.rowEtiquetas)) {
    rowEts[id] = [...ets];
  }
  try {
    const { from: fcFrom, to: fcTo } = getDateRange();
    const formData = new URLSearchParams();
    formData.set('etiquetas_json', JSON.stringify(state.mainEtiquetasSelected));
    formData.set('mode', state.mainFilterMode);
    formData.set('row_etiquetas_json', JSON.stringify(rowEts));
    if (fcFrom) formData.set('date_from', fcFrom);
    if (fcTo) formData.set('date_to', fcTo);

    const res = await fetch('/api/method/marketinghub.api.meta_ads.get_filtered_lead_counts', {
      method: 'POST',
      headers: {
        'X-Frappe-CSRF-Token': frappe.csrf_token,
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
      },
      body: formData.toString()
    });
    const json = await res.json();
    state.filteredLeadCountByRow = json.message || {};
    if (state.rows.length) applyFiltersAndSort();
  } catch (_) {
    state.filteredLeadCountByRow = {};
  }
}

async function loadAccounts() {
  if (!state.token || !els.accountSelect) return;
  els.accountsBtn.disabled = true;
  els.accountSelect.innerHTML = '<option>Cargando cuentas...</option>';

  try {
    const res = await fetch(`https://graph.facebook.com/v22.0/me/adaccounts?fields=name,account_id&access_token=${state.token}`);
    const data = await res.json();
    if (data.error) throw data.error;

    state.accounts = data.data || [];
    if (!state.accounts.length) {
      showMetaError({
        message: "El token es valido pero no devuelve cuentas publicitarias. Verifica que la cuenta Meta tenga cuentas asignadas.",
        type: "NoAccounts",
      });
      els.accountSelect.innerHTML = '<option value="">-- Sin cuentas --</option>';
      return;
    }
    const accountOptions = state.accounts.map(a => `<option value="${a.account_id}">${a.name} (${a.account_id})</option>`).join('');
    els.accountSelect.innerHTML = accountOptions;
    if(els.accountFilterInline) els.accountFilterInline.innerHTML = accountOptions;

    // Default account: primera cuenta publicitaria disponible (no hardcoded).
    if (state.accounts.length > 0) {
      const def = state.accounts[0];
      els.accountSelect.value = def.account_id;
      if (els.accountFilterInline) els.accountFilterInline.value = def.account_id;
    }
    // Limpiar cualquier banner de error previo.
    hideMetaError();
  } catch (e) {
    showMetaError(e);
    els.accountSelect.innerHTML = '<option value="">-- Error al cargar --</option>';
    setError(e.message || "Error al leer cuentas de Meta");
  } finally {
    els.accountsBtn.disabled = false;
  }
}

// Banner de error visible cuando Meta rechaza el token o algo falla.
function showMetaError(err) {
  const msg = (err && err.message) || String(err) || "Error desconocido";
  const type = (err && err.type) || "";
  const code = (err && err.code) || "";
  const bannerId = 'meta-error-banner';
  let banner = document.getElementById(bannerId);
  if (!banner) {
    banner = document.createElement('div');
    banner.id = bannerId;
    banner.style.cssText = 'margin:12px 16px;padding:12px 16px;background:#fef2f2;border:1px solid #fecaca;border-left:4px solid #ef4444;border-radius:8px;color:#991b1b;font-size:13px;line-height:1.4;';
    const container = document.querySelector('.metricas-modernas, .kpis-container, main') || document.body;
    container.parentNode ? container.parentNode.insertBefore(banner, container) : container.appendChild(banner);
  }
  banner.innerHTML =
    '<div style="font-weight:600;margin-bottom:4px;">Meta API no respondio con datos</div>' +
    '<div style="font-family:monospace;white-space:pre-wrap;word-break:break-word;">' +
    _esc(msg) + (code ? ` (code ${_esc(code)})` : '') + (type ? ` [${_esc(type)}]` : '') +
    '</div>' +
    '<div style="margin-top:6px;font-size:12px;color:#7f1d1d;">' +
    'Verifica que el token no este expirado. Regeneralo desde Business Manager -> Herramientas del Sistema -> ' +
    'Tokens de Acceso y pegalo en <b>Configuracion Meta</b>.</div>';
}
function hideMetaError() {
  const b = document.getElementById('meta-error-banner');
  if (b && b.parentNode) b.parentNode.removeChild(b);
}
function _esc(s) {
  return String(s || '').replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

function switchTab(tab) {
  state.activeTab = tab;
  state.nameSearch = '';
  if(els.nameSearch) els.nameSearch.value = '';

  const tabLeads = document.getElementById('tabLeads');
  const isLeads = tab === 'leads';

  // Mostrar u ocultar el tab Leads (solo visible cuando se entra a él)
  if (tabLeads) tabLeads.style.display = isLeads ? '' : 'none';

  // Alternar entre tabla principal y tabla de leads
  if (els.leadsTableWrap) els.leadsTableWrap.style.display = isLeads ? '' : 'none';
  if (els.mainTableScroll) els.mainTableScroll.style.display = isLeads ? 'none' : '';
  const mainFilters = document.getElementById('mainTableFilters');
  if (mainFilters) mainFilters.style.display = isLeads ? 'none' : 'flex';

  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('tab-active', b.dataset.tab === tab));

  const titles = { campaign: 'Campañas', adset: 'Conjuntos de anuncios', ad: 'Anuncios', leads: 'Leads' };
  const tableTitle = document.getElementById('tableTitle');
  if (tableTitle) tableTitle.textContent = titles[tab] || tab;

  // Breadcrumb
  _updateBreadcrumb(tab);

  if (isLeads) {
    loadLeads();
  } else {
    loadData();
  }
}

function _updateBreadcrumb(tab) {
  if (!els.breadcrumb) return;
  const isDeep = tab === 'adset' || tab === 'ad' || tab === 'leads';
  els.breadcrumb.classList.toggle('hidden', !isDeep);

  // Nivel campaña
  const campName = state.selectedCampaigns[0]?.name || '';
  if (els.breadcrumbSep2) els.breadcrumbSep2.style.display = campName ? '' : 'none';
  if (els.breadcrumbCampaignName) els.breadcrumbCampaignName.textContent = campName;

  // Nivel conjunto
  const adsetName = state.selectedAdsets[0]?.name || '';
  if (els.breadcrumbSep3) els.breadcrumbSep3.style.display = adsetName ? '' : 'none';
  if (els.breadcrumbName) els.breadcrumbName.textContent = adsetName;

  // Nivel anuncio (solo en leads)
  const adName = tab === 'leads' ? (state.drillAd?.name || '') : '';
  if (els.breadcrumbSep4) els.breadcrumbSep4.style.display = adName ? '' : 'none';
  if (els.breadcrumbAdName) els.breadcrumbAdName.textContent = adName;

  // Botón Campañas (para volver desde adset a campaign)
  const breadcrumbCampaigns = document.getElementById('breadcrumbCampaigns');
  if (breadcrumbCampaigns) breadcrumbCampaigns.style.display = 'none';

  // Botón ← Volver
  if (els.breadcrumbBack) {
    els.breadcrumbBack.onclick = () => {
      if (tab === 'leads') {
        state.drillAd = null;
        switchTab('ad');
      } else if (tab === 'ad') {
        state.selectedAdsets = [];
        updateTabBadges();
        switchTab('adset');
      } else if (tab === 'adset') {
        state.selectedCampaigns = [];
        updateTabBadges();
        switchTab('campaign');
      }
    };
  }
}

function updateTabBadges() {
  const badgeCampaign = document.getElementById('badgeCampaign');
  const badgeAdset = document.getElementById('badgeAdset');
  const nc = state.selectedCampaigns.length;
  const na = state.selectedAdsets.length;
  if (badgeCampaign) {
    badgeCampaign.classList.toggle('hidden', nc === 0);
    const txt = badgeCampaign.childNodes[0];
    if (txt) txt.textContent = `${nc} seleccionado${nc > 1 ? 's' : ''} `;
  }
  if (badgeAdset) {
    badgeAdset.classList.toggle('hidden', na === 0);
    const txt = badgeAdset.childNodes[0];
    if (txt) txt.textContent = `${na} seleccionado${na > 1 ? 's' : ''} `;
  }
}

function toggleRowSelection(id, name) {
  if (state.activeTab === 'campaign') {
    const idx = state.selectedCampaigns.findIndex(r => r.id === id);
    if (idx >= 0) state.selectedCampaigns.splice(idx, 1);
    else state.selectedCampaigns.push({ id, name });
  } else if (state.activeTab === 'adset') {
    const idx = state.selectedAdsets.findIndex(r => r.id === id);
    if (idx >= 0) state.selectedAdsets.splice(idx, 1);
    else state.selectedAdsets.push({ id, name });
  }
  updateTabBadges();
  applyFiltersAndSort();
}

function toggleSelectAll(checked, rows) {
  if (state.activeTab === 'campaign') {
    state.selectedCampaigns = checked ? rows.map(r => ({ id: r.id, name: r.name })) : [];
  } else if (state.activeTab === 'adset') {
    state.selectedAdsets = checked ? rows.map(r => ({ id: r.id, name: r.name })) : [];
  }
  updateTabBadges();
  applyFiltersAndSort();
}

async function loadData(silent = false) {
  if (!els.accountSelect) return;
  if (state.activeTab === 'leads') return;
  const account_id = els.accountSelect.value;
  const level = els.levelSelect.value === 'tabs' ? state.activeTab : els.levelSelect.value;

  if (!account_id) return alert("Selecciona una cuenta");

  if (!els.dateFrom.value || !els.dateTo.value) return;
  if (els.dateFrom.value > els.dateTo.value) return;

  els.loadBtn.disabled = true;
  if (!silent) {
    if (els.tableBody) els.tableBody.innerHTML = '<tr><td colspan="10" style="padding:60px; text-align:center;">Analizando datos masivos...</td></tr>';
    if (els.mobileList) els.mobileList.innerHTML = '<p style="padding: 40px; text-align:center; color: var(--text-muted);">Sincronizando con Meta API...</p>';
  }

  try {
    let rows = [];
    if (level === 'post') {
      const res = await fetch('/api/method/marketinghub.api.meta_ads.get_page_posts');
      const data = await res.json();
      rows = (data.message || []).map(p => ({
        id: p.id,
        name: p.message || p.id,
        status: 'PUBLISHED',
        spend: 0,
        impressions: p.insights?.impressions || 0,
        clicks: p.insights?.engagement || 0,
        results: p.insights?.likes || 0,
        reach: p.insights?.reach || 0,
        ctr: 0,
        cpc: 0,
        cpr: 0,
        resultKey: 'Likes',
        raw: p
      }));
    } else {
      const fields = 'campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,spend,impressions,clicks,reach,frequency,cpc,ctr,cpp,actions,objective,inline_link_clicks,account_name';
      const dateParam = `time_range[since]=${els.dateFrom.value}&time_range[until]=${els.dateTo.value}`;
      const filterParam = (level === 'adset' && state.selectedCampaigns.length)
        ? `&filtering=${encodeURIComponent(JSON.stringify([{field:'campaign.id',operator:'IN',value:state.selectedCampaigns.map(r=>r.id)}]))}`
        : (level === 'ad' && state.selectedAdsets.length)
        ? `&filtering=${encodeURIComponent(JSON.stringify([{field:'adset.id',operator:'IN',value:state.selectedAdsets.map(r=>r.id)}]))}`
        : '';
      const url = `https://graph.facebook.com/v22.0/act_${account_id}/insights?level=${level}&${dateParam}&fields=${fields}&access_token=${state.token}&limit=500${filterParam}`;

      // Endpoint separado para obtener effective_status (no disponible en /insights)
      const effectiveLevel = level;
      const levelEndpoint = { campaign: 'campaigns', adset: 'adsets', ad: 'ads', account: 'campaigns' }[effectiveLevel] || 'campaigns';
      const statusUrl = `https://graph.facebook.com/v22.0/act_${account_id}/${levelEndpoint}?fields=id,effective_status&access_token=${state.token}&limit=500`;

      const [res, statusRes] = await Promise.all([fetch(url), fetch(statusUrl)]);
      const [data, statusData] = await Promise.all([res.json(), statusRes.json()]);
      if (data.error) throw data.error;

      const statusMap = {};
      (statusData.data || []).forEach(c => { statusMap[c.id] = c.effective_status; });
      
      const objectiveToAction = {
        // Objetivos nuevos (OUTCOME_*)
        'OUTCOME_LEADS':       'lead',
        'OUTCOME_SALES':       'purchase',
        'OUTCOME_TRAFFIC':     'link_click',
        'OUTCOME_ENGAGEMENT':  'post_engagement',
        'OUTCOME_AWARENESS':   'reach',
        'OUTCOME_APP_PROMOTION': 'app_install',
        // Objetivos legacy
        'LEAD_GENERATION':     'lead',
        'CONVERSIONS':         'offsite_conversion',
        'LINK_CLICKS':         'link_click',
        'MESSAGES':            'onsite_conversion.total_messaging_connection',
        'PAGE_LIKES':          'like',
        'POST_ENGAGEMENT':     'post_engagement',
        'VIDEO_VIEWS':         'video_view',
        'APP_INSTALLS':        'app_install',
        'REACH':               'reach',
        'BRAND_AWARENESS':     'reach',
      };

      rows = (data.data || []).map(r => {
        const actions = r.actions || [];
        const targetType = objectiveToAction[r.objective];
        // Para OUTCOME_ENGAGEMENT, muchas campañas optimizan mensajes — intentar primero
        // Priorizar _7d porque es la ventana que usa Meta Ads Manager por defecto
        const messagingAction = actions.find(a => a.action_type === 'onsite_conversion.messaging_conversation_started_7d')
          || actions.find(a => a.action_type === 'onsite_conversion.total_messaging_connection');
        const resObj = (messagingAction && r.objective === 'OUTCOME_ENGAGEMENT' ? messagingAction : null)
          || (targetType && actions.find(a => a.action_type === targetType))
          || messagingAction
          || { value: 0, action_type: r.objective || 'none' };
        return {
          id: level === 'ad' ? r.ad_id
            : level === 'adset' ? r.adset_id
            : level === 'account' ? r.account_id
            : r.campaign_id,
          name: level === 'adset' ? (r.adset_name || r.campaign_name)
              : level === 'ad'   ? (r.ad_name || r.adset_name)
              : level === 'account' ? r.account_name
              : (r.campaign_name || r.adset_name || r.ad_name || r.account_name),
          status: statusMap[level === 'ad' ? r.ad_id : level === 'adset' ? r.adset_id : r.campaign_id] || 'UNKNOWN',
          spend: parseFloat(r.spend || 0),
          impressions: parseInt(r.impressions || 0),
          clicks: parseInt(r.clicks || 0),
          results: parseInt(resObj.value || 0),
          reach: parseInt(r.reach || 0),
          cpr: r.spend && resObj.value ? (r.spend / resObj.value) : 0,
          ctr: parseFloat(r.ctr || 0),
          cpc: parseFloat(r.cpc || 0),
          objective: r.objective,
          resultKey: resObj.action_type,
          raw: r,
          date_start: r.date_start,
          date_stop: r.date_stop,
          parentName: level === 'adset' ? r.campaign_name : level === 'ad' ? r.adset_name : null
        };
      });
    }
    
    state.rows = rows;
    renderStats(rows);
    if (state.mainEtiquetasSelected.length) fetchFilteredCounts();
    else applyFiltersAndSort();

    // Refresh lead counts and sales data with the current date range
    reloadErpData();

    // Auto-hide only on mobile to save vertical space (not on silent reload)
    if (!silent && window.innerWidth <= 1024 && els.filterPanel) {
      els.filterPanel.classList.add('hidden');
    }
  } catch (e) {
    setError(e.message || "Error al cargar informes");
    showMetaError(e);
  } finally {
    els.loadBtn.disabled = false;
  }
}

function getSalesData(r) {
  const { adSales, adsetSales, campSales } = state.salesDataByRow;
  if (state.activeTab === 'ad')       return adSales[r.id];
  if (state.activeTab === 'adset')    return adsetSales[r.id];
  if (state.activeTab === 'campaign') return campSales[r.id];
  return undefined;
}

const SORT_FIELDS = {
  name: r => r.name?.toLowerCase(),
  delivery: r => r.status,
  results: r => r.results,
  reach: r => r.reach,
  cpr: r => r.cpr,
  spend: r => r.spend,
  impressions: r => r.impressions,
  clicks: r => r.clicks,
  ctr: r => r.ctr,
  cpc: r => r.cpc,
  ventas: r => { const sd = getSalesData(r); return sd ? sd.ventas : -1; },
  cpa: r => { const sd = getSalesData(r); return (sd && sd.ventas > 0) ? r.spend / sd.ventas : Infinity; },
  roas: r => { const sd = getSalesData(r); return (sd && sd.ingresos > 0 && r.spend > 0) ? sd.ingresos / r.spend : -Infinity; }
};

function applyFiltersAndSort() {
  if (state.activeTab === 'leads') {
    if (!state.leadsData) return;
    const data = state.leadsData;
    let leads = [...(data.leads || [])];
    if (state.nameSearch) leads = leads.filter(l => (l.lead_name || l.name || '').toLowerCase().includes(state.nameSearch) || (l.mobile_no || '').includes(state.nameSearch));
    if (state.statusFilter) leads = leads.filter(l => (l.status || '') === state.statusFilter);
    if (state.leadEtiquetasSelected.length > 0) {
      const sel = state.leadEtiquetasSelected;
      const mode = state.leadFilterMode;
      leads = leads.filter(l => {
        if (!l.etiquetas) return false;
        const tags = l.etiquetas.split(', ');
        if (mode === 'OR') return sel.some(s => tags.includes(s));
        return sel.every(s => tags.includes(s));
      });
    }
    renderLeadsTable({ ...data, leads, total: leads.length }, true);
    return;
  }
  let rows = [...state.rows];
  if (state.nameSearch) rows = rows.filter(r => (r.name || '').toLowerCase().includes(state.nameSearch));
  if (state.statusFilter) rows = rows.filter(r => r.status === state.statusFilter);
  else if (state.onlyActive) rows = rows.filter(r => r.status === 'ACTIVE');
  if (state.etiquetaFilter) {
    const ef = state.etiquetaFilter;
    const { adMap, adsetMap, campMap } = state.erpMapping;
    if (state.activeTab === 'ad') {
      rows = rows.filter(r => adMap[r.id] === ef);
    } else if (state.activeTab === 'adset') {
      const valid = adsetMap[ef] || new Set();
      rows = rows.filter(r => valid.has(r.id));
    } else if (state.activeTab === 'campaign') {
      const valid = campMap[ef] || new Set();
      rows = rows.filter(r => valid.has(r.id));
    }
  }
  if (state.sort.key && SORT_FIELDS[state.sort.key]) {
    const fn = SORT_FIELDS[state.sort.key];
    rows.sort((a, b) => {
      const va = fn(a), vb = fn(b);
      if (va < vb) return -1 * state.sort.dir;
      if (va > vb) return 1 * state.sort.dir;
      return 0;
    });
  }
  renderTable(rows);
  renderMobileCards(rows);
  // Actualizar indicadores visuales en headers
  document.querySelectorAll('th[data-sort]').forEach(th => {
    th.classList.toggle('sort-active', th.dataset.sort === state.sort.key);
    th.dataset.dir = (th.dataset.sort === state.sort.key) ? (state.sort.dir === -1 ? 'desc' : 'asc') : '';
  });
}

function renderTable(rows) {
  if (els.rowCountBadge) els.rowCountBadge.textContent = `${rows.length} Registros`;
  if (!els.tableBody) return;
  if (rows.length === 0) {
    els.tableBody.innerHTML = '<tr><td colspan="16" style="padding:60px; text-align:center;">No hay datos para este periodo</td></tr>';
    return;
  }
  const canSelect = state.activeTab === 'campaign' || state.activeTab === 'adset';
  const selectedIds = state.activeTab === 'campaign' ? state.selectedCampaigns.map(r=>r.id) : state.selectedAdsets.map(r=>r.id);
  const isChecked = (id) => selectedIds.includes(id);
  const allChecked = canSelect && rows.length > 0 && rows.every(r => isChecked(r.id));

  // Actualizar checkbox "seleccionar todos" en el header
  const selectAllChk = document.getElementById('selectAllChk');
  if (selectAllChk) {
    selectAllChk.checked = allChecked;
    selectAllChk.indeterminate = !allChecked && selectedIds.length > 0;
    selectAllChk.style.display = canSelect ? '' : 'none';
  }

  const { adLeadCount, adsetLeadCount, campLeadCount } = state.leadCountByRow;
  const totalCounts = state.leadCountTotalByRow || state.leadCountByRow;
  const filteredCounts = state.filteredLeadCountByRow || {};
  const hasDateFilter = !!(els.dateFrom.value || els.dateTo.value);
  const getLeadCount = (r) => {
    if (state.activeTab === 'ad') return adLeadCount[r.id];
    if (state.activeTab === 'adset') return adsetLeadCount[r.id];
    if (state.activeTab === 'campaign') return campLeadCount[r.id];
    return undefined;
  };
  const getLeadCountTotal = (r) => {
    const tc = totalCounts;
    if (state.activeTab === 'ad') return tc.adLeadCount[r.id];
    if (state.activeTab === 'adset') return tc.adsetLeadCount[r.id];
    if (state.activeTab === 'campaign') return tc.campLeadCount[r.id];
    return undefined;
  };
  const getFilteredCount = (r) => {
    if (!state.mainEtiquetasSelected.length) return undefined;
    return filteredCounts[r.id];
  };
  const badgeCellERP = (filtered, total, rowId) => {
    if (filtered === undefined || filtered === null) return `<td class="num" style="color:var(--text-muted);">-</td>`;
    const showDual = hasDateFilter && total !== undefined && total !== filtered;
    if (showDual) {
      const tt = `${integer(total)} leads totales en la campaña\n${integer(filtered)} leads creados en el rango de fecha`;
      if (filtered > 0) {
        return `<td class="num"><span class="lead-badge-click" data-id="${rowId}" onclick="event.stopPropagation(); window.openAllLeadsModal('${rowId}')" title="${tt}" style="background:#e8f5e9;color:#2e7d32;border-radius:12px;padding:2px 8px;font-size:0.78rem;font-weight:600;cursor:pointer;"><span style="opacity:0.55;font-weight:400;">${integer(total)}</span> (${integer(filtered)})</span></td>`;
      }
      return `<td class="num"><span title="${tt}" style="color:var(--text-muted);font-size:0.78rem;"><span style="opacity:0.7;">${integer(total)}</span> (0)</span></td>`;
    }
    if (filtered > 0) {
      return `<td class="num"><span class="lead-badge-click" data-id="${rowId}" onclick="event.stopPropagation(); window.openAllLeadsModal('${rowId}')" style="background:#e8f5e9;color:#2e7d32;border-radius:12px;padding:2px 8px;font-size:0.78rem;font-weight:600;cursor:pointer;">${integer(filtered)}</span></td>`;
    }
    return `<td class="num" style="color:var(--text-muted);font-size:0.82rem;">0</td>`;
  };
  const badgeCellFiltro = (count, rowId) => {
    if (count === undefined || count === null) return `<td class="num" style="color:var(--text-muted);">-</td>`;
    if (count > 0) {
      return `<td class="num"><span class="lead-badge-click" data-id="${rowId}" onclick="event.stopPropagation(); window.openFilteredLeadsModal('${rowId}')" style="background:#e3f2fd;color:#1565c0;border-radius:12px;padding:2px 8px;font-size:0.78rem;font-weight:600;cursor:pointer;">${integer(count)}</span></td>`;
    }
    return `<td class="num" style="color:var(--text-muted);font-size:0.82rem;">0</td>`;
  };
  const badgeCellCliente = (count, rowId) => {
    if (count === undefined || count === null) return `<td class="num" style="color:var(--text-muted);">-</td>`;
    if (count > 0) {
      return `<td class="num"><span class="lead-badge-click" data-id="${rowId}" onclick="event.stopPropagation(); window.openClienteLeadsModal('${rowId}')" style="background:#fce4ec;color:#c62828;border-radius:12px;padding:2px 8px;font-size:0.78rem;font-weight:600;cursor:pointer;">${integer(count)}</span></td>`;
    }
    return `<td class="num" style="color:var(--text-muted);font-size:0.82rem;">0</td>`;
  };
  els.tableBody.innerHTML = rows.map(r => {
    const lc = getLeadCount(r);
    const lcTotal = getLeadCountTotal(r);
    const fc = getFilteredCount(r);
    const sd = getSalesData(r);
    const ventas = sd ? sd.ventas : undefined;
    const ingresos = sd ? sd.ingresos : 0;
    const cpaRaw   = (ventas > 0) ? r.spend / ventas : null;
    const cpaVal   = cpaRaw !== null ? money(cpaRaw) : '-';
    const roasRaw  = (r.spend > 0 && ingresos > 0) ? ingresos / r.spend : null;
    const roasVal  = roasRaw !== null ? float(roasRaw) + 'x' : '-';
    const cprRaw   = (r.results > 0) ? r.spend / r.results : null;
    const ctrRaw   = r.ctr || 0;
    const cpcRaw   = (r.clicks > 0) ? r.spend / r.clicks : null;
    // Dynamic color based on metric quality
    const roasColor = roasRaw !== null ? (roasRaw >= 1 ? '#2e7d32' : '#c62828') : null;
    const cpaColor  = cpaRaw !== null ? (cpaRaw <= 100 ? '#2e7d32' : cpaRaw <= 200 ? '#e65100' : '#c62828') : null;
    // Build tooltip attributes (escaped for HTML attributes)
    const esc = s => s.replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const cpaTT  = cpaRaw !== null ? esc(buildValueTooltip('cpa', { spend: r.spend, ventas, ingresos, value: cpaRaw })) : '';
    const roasTT = roasRaw !== null ? esc(buildValueTooltip('roas', { ingresos, spend: r.spend, value: roasRaw })) : '';
    const cprTT  = cprRaw !== null ? esc(buildValueTooltip('cpr', { spend: r.spend, results: r.results, value: cprRaw })) : '';
    const ctrTT  = ctrRaw > 0 ? esc(buildValueTooltip('ctr', { clicks: r.clicks, impressions: r.impressions, value: ctrRaw })) : '';
    const cpcTT  = cpcRaw !== null ? esc(buildValueTooltip('cpc', { spend: r.spend, clicks: r.clicks, value: cpcRaw })) : '';
    const valCell = (val, color, tt) => {
      if (val === '-') return `<td class="num" style="color:var(--text-muted);font-size:0.82rem;">-</td>`;
      if (tt) return `<td class="num" style="font-weight:600; color:${color};"><span class="val-tt" data-vtooltip="${tt}">${val}</span></td>`;
      return `<td class="num" style="font-weight:600; color:${color};">${val}</td>`;
    };
    return `
    <tr data-id="${r.id}" class="${isChecked(r.id) ? 'row-selected' : ''}">
      <td style="padding:16px 8px 16px 24px; width:44px;" onclick="event.stopPropagation()">
        ${canSelect ? `<input type="checkbox" class="row-check" data-id="${r.id}" data-name="${r.name.replace(/"/g,'&quot;')}" ${isChecked(r.id) ? 'checked' : ''} style="accent-color:var(--primary); width:15px; height:15px; cursor:pointer;">` : ''}
      </td>
      <td title="${r.name}">
        <div style="display:flex; align-items:center; gap:4px;">
          ${state.activeTab === 'campaign' || state.activeTab === 'adset' || state.activeTab === 'ad'
            ? `<div class="name-drill" data-id="${r.id}" data-name="${r.name.replace(/"/g,'&quot;')}" style="max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:500; cursor:pointer; color:var(--primary); text-decoration:underline; text-underline-offset:2px;">${r.name}</div>`
            : `<div style="max-width:220px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-weight:500;">${r.name}</div>`
          }
          <button class="btn-edit-row" data-id="${r.id}" onclick="event.stopPropagation()" title="Editar configuración">&#9998;</button>
        </div>
        ${r.parentName ? `<div style="max-width:240px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:0.72rem; color:var(--text-muted); margin-top:2px;">${r.parentName}</div>` : ''}
      </td>
      <td>${statusBadge(r.status)}</td>
      ${badgeCellERP(lc, lcTotal, r.id)}
      ${badgeCellFiltro(fc, r.id)}
      ${badgeCellCliente(ventas !== undefined ? ventas : undefined, r.id)}
      ${valCell(cpaVal, cpaColor || '#c62828', cpaTT)}
      ${valCell(roasVal, roasColor || '#2e7d32', roasTT)}
      <td class="num">${integer(r.results)}</td>
      <td class="num">${integer(r.reach)}</td>
      <td class="num">${cprTT ? `<span class="val-tt" data-vtooltip="${cprTT}">${money(r.cpr)}</span>` : money(r.cpr)}</td>
      <td class="num">${money(r.spend)}</td>
      <td class="num">${integer(r.impressions)}</td>
      <td class="num">${integer(r.clicks)}</td>
      <td class="num">${ctrTT ? `<span class="val-tt" data-vtooltip="${ctrTT}">${float(r.ctr)}%</span>` : `${float(r.ctr)}%`}</td>
      <td class="num">${cpcTT ? `<span class="val-tt" data-vtooltip="${cpcTT}">${money(r.cpc)}</span>` : money(r.cpc)}</td>
    </tr>
  `;
  }).join('');
  
  els.tableBody.querySelectorAll('tr[data-id]').forEach(tr => {
    tr.onclick = () => {
      window.openAllLeadsModal(tr.dataset.id);
    };
  });
  els.tableBody.querySelectorAll('.row-check').forEach(chk => {
    chk.onchange = () => toggleRowSelection(chk.dataset.id, chk.dataset.name);
  });
  els.tableBody.querySelectorAll('.name-drill').forEach(el => {
    el.onclick = (e) => {
      e.stopPropagation();
      const id = el.dataset.id;
      const name = el.dataset.name;
      if (state.activeTab === 'campaign') {
        state.selectedCampaigns = [{ id, name }];
        updateTabBadges();
        switchTab('adset');
      } else if (state.activeTab === 'adset') {
        state.selectedAdsets = [{ id, name }];
        updateTabBadges();
        switchTab('ad');
      } else if (state.activeTab === 'ad') {
        state.drillAd = { id, name };
        switchTab('leads');
      }
    };
  });
  // Bind edit buttons
  els.tableBody.querySelectorAll('.btn-edit-row').forEach(btn => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const row = state.rows.find(r => r.id === btn.dataset.id);
      if (row) window.openEditCampModal(row);
    };
  });
  // Bind floating tooltips on table values
  bindTooltips(els.tableBody);
  if (window.innerWidth > 1024) {
    const prev = state.activeRow ? rows.find(r => r.id === state.activeRow.id) : null;
    if (prev) selectRow(prev);
    else if (rows[0]) selectRow(rows[0]);
  }
}

function renderMobileCards(rows) {
  if (!els.mobileList) return;
  if (rows.length === 0) {
    els.mobileList.innerHTML = '<p style="padding: 40px; text-align:center; color: var(--text-muted);">No hay campañas activas en este periodo</p>';
    return;
  }
  els.mobileList.innerHTML = rows.map(r => `
    <div class="mobile-card" onclick="window.openMobileModal('${r.id}')">
      <div class="m-card-header">
        <span class="m-card-name">${r.name}</span>
        ${statusBadge(r.status)}
      </div>
      <div class="m-card-grid">
        <div class="m-cell"><span class="m-label">Imp. Gastado</span><span class="m-value">${money(r.spend)}</span></div>
        <div class="m-cell"><span class="m-label">Resultados</span><span class="m-value">${integer(r.results)}</span></div>
      </div>
    </div>
  `).join('');
}

function renderStats(rows) {
  const t = rows.reduce((acc, r) => {
    acc.spend += r.spend;
    acc.impressions += r.impressions;
    acc.clicks += r.clicks;
    acc.results += r.results;
    return acc;
  }, { spend: 0, impressions: 0, clicks: 0, results: 0 });
  
  if (els.mSpend) els.mSpend.textContent = money(t.spend);
  if (els.mImpressions) els.mImpressions.textContent = integer(t.impressions);
  if (els.mClicks) els.mClicks.textContent = integer(t.clicks);
  if (els.mResults) els.mResults.textContent = integer(t.results);
}

function selectRow(row) {
  state.activeRow = row;
  document.querySelectorAll('tbody tr').forEach(tr => tr.classList.toggle('active', tr.dataset.id === row.id));
  if (els.dName) els.dName.textContent = row.name;
  if (els.dStatus) els.dStatus.textContent = row.status || '-';
  if (els.dObjective) els.dObjective.textContent = row.objective || '-';
  if (els.dRange) els.dRange.textContent = row.date_start ? `${row.date_start} / ${row.date_stop}` : '-';
  if (els.rawJson) els.rawJson.textContent = JSON.stringify(row.raw, null, 2);
  // Debug: mostrar todos los action_types con sus valores
  const dAllActions = document.getElementById('dAllActions');
  if (dAllActions) {
    const acts = row.raw.actions || [];
    if (acts.length === 0) {
      dAllActions.innerHTML = '<span style="color:var(--text-muted);">Sin actions</span>';
    } else {
      dAllActions.innerHTML = acts.map(a =>
        `<div style="display:flex;justify-content:space-between;gap:8px;">
          <span style="color:var(--text-muted);word-break:break-all;">${a.action_type}</span>
          <span style="font-weight:700;flex-shrink:0;">${integer(a.value)}</span>
        </div>`
      ).join('');
    }
  }
  renderActions(row, els.actionList);
  renderTrendChart(row, els.trendChartCtx, 'chart');
}

window.openMobileModal = (id) => {
  console.log("Tap detected on ID:", id);
  const row = state.rows.find(r => r.id === id);
  if (!row) {
    console.warn("Row not found for ID:", id);
    return;
  }
  
  if (els.mDName) els.mDName.textContent = row.name;
  if (els.mDStatus) els.mDStatus.textContent = row.status;
  if (els.mDObjective) els.mDObjective.textContent = row.objective || '-';
  if (els.mDRange) els.mDRange.textContent = row.date_start ? `${row.date_start} / ${row.date_stop}` : '-';
  
  renderActions(row, els.mActionList);
  
  if (els.mobileModal) {
    els.mobileModal.classList.remove('hidden');
    // Save history state to allow 'back' button to close modal
    history.pushState({ modalOpen: true }, "");
    console.log("Modal opened. State pushed to history.");
  } else {
    console.error("mobileModal element not found in DOM");
  }
  
  setTimeout(() => renderTrendChart(row, els.mTrendChartCtx, 'mChart'), 150);
};

window.closeMobileModal = (fromHistory = false) => {
    if (els.mobileModal) {
        els.mobileModal.classList.add('hidden');
        if (!fromHistory && history.state && history.state.modalOpen) {
            history.back();
        }
    }
    if (state.mChart) state.mChart.destroy();
};

window.addEventListener('popstate', (event) => {
    if (els.mobileModal && !els.mobileModal.classList.contains('hidden')) {
        window.closeMobileModal(true);
    }
});

function renderActions(row, container) {
  if (!container) return;
  const acts = row.raw.actions || [];
  container.innerHTML = acts.slice(0, 5).map(a => `
    <div>
      <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-bottom:4px;">
        <span style="color:var(--text-muted);">${a.action_type.split('_').pop()}</span>
        <span style="font-weight:700;">${integer(a.value)}</span>
      </div>
      <div class="action-bar"><div class="action-line" style="width:${Math.min(100, (a.value/row.results)*100)}%;"></div></div>
    </div>
  `).join('');
}

function renderTrendChart(row, ctx, stateKey) {
  if (state[stateKey]) state[stateKey].destroy();
  if (!ctx) return;
  const labels = ['D-6', 'D-5', 'D-4', 'D-3', 'D-2', 'D-1', 'Hoy'];
  const mockData = Array.from({length: 7}, () => row.spend * (0.8 + Math.random() * 0.4));
  state[stateKey] = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: 'Imp. Gastado',
        data: mockData,
        borderColor: '#4f46e5',
        backgroundColor: 'rgba(79, 70, 229, 0.05)',
        fill: true,
        tension: 0.4,
        borderWidth: 3,
        pointRadius: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { display: false },
        x: { grid: { display: false }, ticks: { font: { size: 10 } } }
      }
    }
  });
}

async function loadLeads() {
  if (!state.drillAd || !els.leadsTableBody) return;
  els.leadsTableBody.innerHTML = '<tr><td colspan="7" style="padding:60px; text-align:center; color:var(--text-muted);">Cargando leads...</td></tr>';
  if (els.rowCountBadge) els.rowCountBadge.textContent = '...';

  try {
    const res = await fetch(
      `/api/method/marketinghub.api.meta_ads.get_leads_por_anuncio_meta?ad_meta_id=${encodeURIComponent(state.drillAd.id)}`,
      { headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token } }
    );
    const data = await res.json();
    renderLeadsTable(data.message || data);
  } catch (e) {
    if (els.leadsTableBody) els.leadsTableBody.innerHTML = '<tr><td colspan="6" style="padding:60px; text-align:center; color:var(--danger);">Error al cargar leads</td></tr>';
  }
}

function renderLeadsTable(data, filtered) {
  if (!els.leadsTableBody) return;
  if (!filtered) state.leadsData = data;
  const badgeLeads = document.getElementById('badgeLeads');

  if (!data || data.etiqueta === null) {
    const msg = data?.anuncio_nombre
      ? `El anuncio "<b>${data.anuncio_nombre}</b>" no tiene etiqueta asignada en el ERP.`
      : 'Este anuncio no tiene etiqueta asignada en el ERP.';
    els.leadsTableBody.innerHTML = `<tr><td colspan="7" style="padding:60px; text-align:center; color:var(--text-muted);">${msg}</td></tr>`;
    if (badgeLeads) { badgeLeads.textContent = '0'; badgeLeads.classList.remove('hidden'); }
    if (els.rowCountBadge) els.rowCountBadge.textContent = '0 Leads';
    return;
  }

  const leads = data.leads || [];
  if (leads.length === 0) {
    els.leadsTableBody.innerHTML = `<tr><td colspan="7" style="padding:60px; text-align:center; color:var(--text-muted);">Sin leads con la etiqueta "<b>${data.etiqueta}</b>"</td></tr>`;
    if (badgeLeads) { badgeLeads.textContent = '0'; badgeLeads.classList.remove('hidden'); }
    if (els.rowCountBadge) els.rowCountBadge.textContent = '0 Leads';
    return;
  }

  // Recopilar todas las etiquetas únicas de los leads para el filtro
  const allEtiquetas = new Set();
  leads.forEach(l => {
    if (l.etiquetas) {
      l.etiquetas.split(', ').forEach(e => allEtiquetas.add(e));
    }
  });
  renderLeadEtiquetaChips([...allEtiquetas].sort());

  function fmtDate(dt) {
    if (!dt) return '-';
    const d = new Date(dt);
    return d.toLocaleDateString('es-PE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  }

  const etiquetasHtml = (raw) => {
    if (!raw) return '<span style="color:var(--text-muted);">-</span>';
    return raw.split(', ').map(e =>
      `<span class="status-badge status-success" style="font-size:0.72rem; display:inline-block; margin:1px 2px;">${e}</span>`
    ).join(' ');
  };

  els.leadsTableBody.innerHTML = leads.map(l => `
    <tr>
      <td style="font-weight:500;">${l.lead_name || l.name}</td>
      <td>${l.mobile_no || '-'}</td>
      <td style="max-width:220px;">${etiquetasHtml(l.etiquetas)}</td>
      <td style="color:var(--text-muted); font-size:0.82rem;">${l.lead_owner || '-'}</td>
      <td style="color:var(--text-muted); font-size:0.82rem; max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${l.custom_notas || '-'}</td>
      <td style="color:var(--text-muted); font-size:0.82rem;">${fmtDate(l.creation)}</td>
      <td><button class="btn btn-secondary" style="width:auto;padding:4px 10px;font-size:0.75rem;" onclick="verConversacionLead('${l.name.replace(/'/g,"\\'")}','${(l.lead_name||'').replace(/'/g,"\\'")}')">💬 Ver</button></td>
    </tr>
  `).join('');

  if (badgeLeads) { badgeLeads.textContent = data.total; badgeLeads.classList.remove('hidden'); }
  if (els.rowCountBadge) els.rowCountBadge.textContent = `${data.total} Leads`;
}

function renderLeadEtiquetaChips(etiquetas) {
  const container = document.getElementById('leadEtiquetaChips');
  if (!container) return;
  const selected = new Set(state.leadEtiquetasSelected);
  container.innerHTML = etiquetas.map(e => {
    const active = selected.has(e);
    return `<button class="lead-etiqueta-chip ${active ? 'chip-active' : ''}" data-etiqueta="${e}">${e}</button>`;
  }).join('');
  container.querySelectorAll('.lead-etiqueta-chip').forEach(chip => {
    chip.onclick = () => {
      const et = chip.dataset.etiqueta;
      const idx = state.leadEtiquetasSelected.indexOf(et);
      if (idx >= 0) state.leadEtiquetasSelected.splice(idx, 1);
      else state.leadEtiquetasSelected.push(et);
      chip.classList.toggle('chip-active', state.leadEtiquetasSelected.includes(et));
      applyFiltersAndSort();
    };
  });
}

function setLeadFilterMode(mode) {
  state.leadFilterMode = mode;
  const btnOr = document.getElementById('leadFilterOr');
  const btnAnd = document.getElementById('leadFilterAnd');
  if (btnOr) {
    btnOr.style.background = mode === 'OR' ? 'var(--primary)' : '#fff';
    btnOr.style.color = mode === 'OR' ? '#fff' : 'var(--text)';
  }
  if (btnAnd) {
    btnAnd.style.background = mode === 'AND' ? 'var(--primary)' : '#fff';
    btnAnd.style.color = mode === 'AND' ? '#fff' : 'var(--text)';
  }
  applyFiltersAndSort();
}

function setError(msg) {
  if (els.sidebarStatus) {
    els.sidebarStatus.textContent = msg;
    els.sidebarStatus.style.color = 'var(--danger)';
  }
}

// ─────────────────────────────────────────────
// MODAL CONVERSACIÓN (reuso lógica de log_leads)
// ─────────────────────────────────────────────
function verConversacionLead(leadName, displayName) {
  frappe.call({
    method: 'marketinghub.api.meta_ads.get_conversation',
    args: { lead_name: leadName },
    freeze: true,
    freeze_message: 'Cargando conversación...',
    callback: function(r) {
      if (!r.message) return frappe.msgprint('No se pudieron cargar los mensajes.');
      const { cuentas, mensajes } = r.message;
      if (!Object.keys(mensajes).length) return frappe.msgprint('No hay mensajes de WhatsApp para este lead.');
      _renderModalConversacion(displayName || leadName, cuentas, mensajes);
    }
  });
}

function _renderModalConversacion(leadName, cuentas, mensajes) {
  const existing = document.getElementById('ma-chat-overlay');
  if (existing) existing.remove();

  let allMsgs = [];
  Object.values(mensajes).forEach(list => allMsgs = allMsgs.concat(list));
  allMsgs.sort((a, b) => new Date(a.creation) - new Date(b.creation));

  const multiples = cuentas.length > 1;
  const tabsHtml = multiples ? `
    <div style="display:flex;gap:6px;padding:12px 16px;border-bottom:1px solid var(--border);flex-wrap:wrap;">
      <button class="ma-chat-tab active" data-panel="__todos" style="padding:4px 12px;border-radius:20px;border:1px solid var(--border);background:var(--primary);color:#fff;font-size:0.78rem;cursor:pointer;">Todos</button>
      ${cuentas.map(c => `<button class="ma-chat-tab" data-panel="${c.id}" style="padding:4px 12px;border-radius:20px;border:1px solid var(--border);background:#fff;font-size:0.78rem;cursor:pointer;">${c.label}</button>`).join('')}
    </div>` : '';

  const panelsHtml = `
    <div>
      <div class="ma-chat-panel" id="ma-panel-__todos" style="display:block;">${_renderBurbujasConversacion(allMsgs)}</div>
      ${cuentas.map(c => {
        const msgs = (mensajes[c.id] || []).slice().sort((a,b) => new Date(a.creation)-new Date(b.creation));
        return `<div class="ma-chat-panel" id="ma-panel-${c.id}" style="display:none;">${_renderBurbujasConversacion(msgs)}</div>`;
      }).join('')}
    </div>`;

  const overlay = document.createElement('div');
  overlay.id = 'ma-chat-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;';
  overlay.innerHTML = `
    <div style="background:#fff;border-radius:12px;width:100%;max-width:580px;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.3);">
      <div style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border);">
        <span style="font-weight:700;font-size:1rem;">💬 ${leadName}</span>
        <button onclick="document.getElementById('ma-chat-overlay').remove()" style="background:none;border:none;font-size:1.4rem;cursor:pointer;color:var(--text-muted);">&times;</button>
      </div>
      ${tabsHtml}
      <div style="flex:1;overflow-y:auto;padding:16px;" id="ma-chat-scroll">${panelsHtml}</div>
    </div>`;

  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  if (multiples) {
    overlay.querySelectorAll('.ma-chat-tab').forEach(tab => {
      tab.onclick = () => {
        overlay.querySelectorAll('.ma-chat-tab').forEach(t => {
          t.style.background = '#fff'; t.style.color = 'var(--text)'; t.classList.remove('active');
        });
        tab.style.background = 'var(--primary)'; tab.style.color = '#fff'; tab.classList.add('active');
        overlay.querySelectorAll('.ma-chat-panel').forEach(p => p.style.display = 'none');
        const panel = document.getElementById(`ma-panel-${tab.dataset.panel}`);
        if (panel) { panel.style.display = 'block'; panel.scrollTop = panel.scrollHeight; }
      };
    });
  }

  setTimeout(() => {
    const active = overlay.querySelector('.ma-chat-panel[style*="display:block"]');
    if (active) active.scrollTop = active.scrollHeight;
  }, 80);
}

function _renderBurbujasConversacion(msgs) {
  if (!msgs || !msgs.length) return '<div style="text-align:center;padding:20px;color:var(--text-muted);">Sin mensajes.</div>';
  return msgs.map(msg => {
    const content = msg.content || '';
    const isClient = content.includes('(Cliente)');
    let body = content.replace(/<div[^>]*>.*?WhatsApp.*?<\/div>/i, '').trim() || content;
    const time = frappe.datetime ? frappe.datetime.str_to_user(msg.creation) : msg.creation;
    const align = isClient ? 'flex-start' : 'flex-end';
    const bg    = isClient ? '#f0f0f0'   : '#dcf8c6';
    return `<div style="display:flex;justify-content:${align};margin-bottom:8px;">
      <div style="max-width:75%;background:${bg};border-radius:10px;padding:8px 12px;font-size:0.82rem;">
        ${body}
        <div style="font-size:0.68rem;color:#888;margin-top:4px;text-align:right;">${time}</div>
      </div>
    </div>`;
  }).join('');
}

// ── Row Detail Modal ──
async function openRowDetailModal(row) {
  const modal = document.getElementById('rowDetailModal');
  const titleEl = document.getElementById('rdmTitle');
  const subtitleEl = document.getElementById('rdmSubtitle');
  const statsEl = document.getElementById('rdmStats');
  const bodyEl = document.getElementById('rdmBody');
  if (!modal) return;

  // Get etiquetas for this row
  const rowEts = state.rowEtiquetas[row.id];
  if (!rowEts || rowEts.size === 0) {
    titleEl.textContent = row.name;
    subtitleEl.textContent = 'Sin etiquetas ERP asociadas';
    statsEl.innerHTML = '';
    bodyEl.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-muted);">Este elemento no tiene etiquetas ERP asignadas. No se pueden mostrar leads.</div>';
    modal.classList.remove('hidden');
    return;
  }

  titleEl.textContent = row.name;
  subtitleEl.textContent = `Etiquetas: ${[...rowEts].join(', ')}`;
  statsEl.innerHTML = '';
  bodyEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">Cargando detalle...</div>';
  modal.classList.remove('hidden');

  // Add edit config button in header if not already present
  let editBtn = modal.querySelector('.btn-edit-camp-header');
  if (!editBtn) {
    editBtn = document.createElement('button');
    editBtn.className = 'btn-edit-camp btn-edit-camp-header';
    editBtn.style.cssText = 'margin-right:12px;padding:6px 14px;font-size:0.78rem;';
    editBtn.innerHTML = '&#9998; Editar Config';
    const closeBtn = modal.querySelector('.rdm-header button:last-child');
    if (closeBtn) closeBtn.parentElement.insertBefore(editBtn, closeBtn);
  }
  editBtn.onclick = () => window.openEditCampModal(row);

  // Fetch detail data
  const { from: df, to: dt } = getDateRange();
  let url = `/api/method/marketinghub.api.meta_ads.get_row_detail?etiquetas_json=${encodeURIComponent(JSON.stringify([...rowEts]))}`;
  if (df) url += `&date_from=${df}`;
  if (dt) url += `&date_to=${dt}`;

  try {
    const res = await fetch(url, { headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token } });
    const json = await res.json();
    const leads = json.message || [];
    renderRowDetailModal(leads, row, statsEl, bodyEl);
  } catch (err) {
    bodyEl.innerHTML = `<div style="text-align:center;padding:40px;color:var(--danger);">Error al cargar: ${err.message}</div>`;
  }
}

function renderRowDetailModal(leads, row, statsEl, bodyEl) {
  // Only show leads that have invoices
  const withInvoices = leads.filter(l => l.facturas.length > 0);

  // Stats from ALL leads (for context), but detail only shows invoiced ones
  const totalLeads = leads.length;
  const totalClientes = withInvoices.length;
  const totalFacturas = withInvoices.reduce((s, l) => s + l.facturas.length, 0);
  const totalIngresos = withInvoices.reduce((s, l) => s + l.facturas.reduce((si, f) => si + f.total, 0), 0);
  const pagadas = withInvoices.reduce((s, l) => s + l.facturas.filter(f => f.pago_estado === 'Pagado').length, 0);
  const parciales = withInvoices.reduce((s, l) => s + l.facturas.filter(f => f.pago_estado === 'Parcial').length, 0);
  const pendientes = withInvoices.reduce((s, l) => s + l.facturas.filter(f => f.pago_estado === 'Pendiente').length, 0);
  const totalPendiente = withInvoices.reduce((s, l) => s + l.facturas.reduce((si, f) => si + f.pendiente, 0), 0);

  statsEl.innerHTML = `
    <div class="rdm-stat"><div class="rdm-stat-value">${totalLeads}</div><div class="rdm-stat-label">Leads totales</div></div>
    <div class="rdm-stat"><div class="rdm-stat-value">${totalClientes}</div><div class="rdm-stat-label">Con factura</div></div>
    <div class="rdm-stat"><div class="rdm-stat-value">${money(totalIngresos)}</div><div class="rdm-stat-label">Facturado</div></div>
    <div class="rdm-stat"><div class="rdm-stat-value" style="color:${totalPendiente > 0 ? 'var(--danger)' : 'var(--success)'}">${money(totalPendiente)}</div><div class="rdm-stat-label">Pendiente</div></div>
  `;

  // Subtitle with invoice breakdown
  const parts = [];
  if (pagadas) parts.push(`${pagadas} pagada${pagadas > 1 ? 's' : ''}`);
  if (parciales) parts.push(`${parciales} parcial${parciales > 1 ? 'es' : ''}`);
  if (pendientes) parts.push(`${pendientes} pendiente${pendientes > 1 ? 's' : ''}`);
  const subtitleEl = document.getElementById('rdmSubtitle');
  if (subtitleEl) {
    subtitleEl.textContent = parts.length
      ? `${totalFacturas} factura${totalFacturas > 1 ? 's' : ''}: ${parts.join(', ')}`
      : 'Sin facturas en el periodo';
  }

  if (withInvoices.length === 0) {
    bodyEl.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-muted);">No hay facturas en el periodo seleccionado para estas etiquetas.</div>';
    return;
  }

  // Sort by most recent invoice date
  withInvoices.sort((a, b) => {
    const aDate = a.facturas[0]?.fecha || '';
    const bDate = b.facturas[0]?.fecha || '';
    return bDate.localeCompare(aDate);
  });

  bodyEl.innerHTML = withInvoices.map(lead => {
    const tags = (lead.etiquetas || '').split(',').map(t => t.trim()).filter(Boolean);
    const tagsHtml = tags.map(t => `<span class="rdm-tag">${t}</span>`).join('');
    const fechaCreacion = lead.creacion ? lead.creacion.split(' ')[0].split('-').reverse().join('/') : '';
    const customerLabel = lead.customer_name || lead.nombre || lead.lead_name;
    const leadLabel = lead.nombre || lead.lead_name;
    const showBoth = lead.customer_name && lead.customer_name !== leadLabel;

    // Chatwoot link
    let chatwootLinkHtml = '';
    if (lead.chatwoot_id) {
      try {
        const ids = lead.chatwoot_id.split('|');
        const lastPart = ids[ids.length - 1].trim().split(':');
        const convId = lastPart.length === 2 ? lastPart[1] : lastPart[0];
        const cwLink = getChatwootLink(convId);
        if (convId && !isNaN(convId) && cwLink) {
          chatwootLinkHtml = `<a href="${cwLink}" target="_blank" class="btn-chat-action" style="border-color:#00a884;color:#00a884;" title="Ir a Chatwoot">&#8599; Chatwoot</a>`;
        }
      } catch(_) {}
    }

    return `
      <div class="rdm-lead-card">
        <div class="rdm-lead-header">
          <div>
            <span class="rdm-lead-name">${customerLabel}</span>
            ${showBoth ? `<span style="font-size:0.78rem;color:var(--text-muted);margin-left:6px;">Lead: ${leadLabel}</span>` : ''}
            <span class="rdm-lead-phone">${lead.telefono || ''}</span>
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            <button class="btn-chat-action btn-ver-mensajes" data-lead="${lead.lead_name}" data-leadname="${(leadLabel || '').replace(/"/g,'&quot;')}" title="Ver conversación">Ver Mensajes</button>
            ${chatwootLinkHtml}
            <span class="rdm-tag tag-cliente">Cliente</span>
            <span style="font-size:0.75rem;color:var(--text-muted);">Lead: ${fechaCreacion}</span>
          </div>
        </div>
        <div class="rdm-lead-tags">${tagsHtml}</div>
        ${lead.responsable ? `<div style="font-size:0.75rem;color:var(--text-muted);margin-top:4px;">Responsable: ${lead.responsable}</div>` : ''}
        <div class="rdm-invoices">
          ${lead.facturas.map(inv => {
            const badgeClass = inv.pago_estado === 'Pagado' ? 'inv-pagado' : inv.pago_estado === 'Parcial' ? 'inv-parcial' : 'inv-pendiente';
            const itemsHtml = inv.items.length ? `
              <div class="rdm-inv-items">
                <table>
                  <thead><tr><th>Producto</th><th style="text-align:right;">Cant.</th><th style="text-align:right;">Precio</th><th style="text-align:right;">Subtotal</th></tr></thead>
                  <tbody>${inv.items.map(it => `
                    <tr>
                      <td>${it.item_name}</td>
                      <td style="text-align:right;">${it.qty}</td>
                      <td style="text-align:right;">${money(it.rate)}</td>
                      <td style="text-align:right;">${money(it.amount)}</td>
                    </tr>`).join('')}
                  </tbody>
                </table>
              </div>` : '';
            const pendienteInfo = inv.pago_estado !== 'Pagado'
              ? `<span style="font-size:0.78rem;color:#c62828;font-weight:600;">Pendiente: ${money(inv.pendiente)}</span>`
              : '';
            return `
              <div class="rdm-invoice">
                <div class="rdm-inv-header">
                  <span class="rdm-inv-name">${inv.name}</span>
                  <span style="font-size:0.78rem;color:var(--text-muted);">Cliente: <strong>${inv.cliente || customerLabel}</strong></span>
                  <span style="font-size:0.78rem;color:var(--text-muted);">${inv.fecha ? inv.fecha.split('-').reverse().join('/') : ''}</span>
                  <span class="rdm-inv-badge ${badgeClass}">${inv.pago_estado}</span>
                </div>
                ${itemsHtml}
                <div class="rdm-inv-total">
                  <span>Total: ${money(inv.total)}</span>
                  ${pendienteInfo}
                </div>
              </div>`;
          }).join('')}
        </div>
      </div>`;
  }).join('');

  // Bind "Ver Mensajes" buttons
  bodyEl.querySelectorAll('.btn-ver-mensajes').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      mostrarConversacion(btn.dataset.lead, btn.dataset.leadname);
    });
  });
}

window.openAllLeadsModal = async (rowId) => {
  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;
  const rowEts = state.rowEtiquetas[row.id];
  if (!rowEts || rowEts.size === 0) return;

  const modal = document.getElementById('rowDetailModal');
  const titleEl = document.getElementById('rdmTitle');
  const subtitleEl = document.getElementById('rdmSubtitle');
  const statsEl = document.getElementById('rdmStats');
  const bodyEl = document.getElementById('rdmBody');
  if (!modal) return;

  titleEl.textContent = row.name;
  subtitleEl.textContent = `Etiquetas: ${[...rowEts].join(', ')}`;
  statsEl.innerHTML = '';
  bodyEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">Cargando todos los leads...</div>';
  modal.classList.remove('hidden');

  const { from: df, to: dt } = getDateRange();
  let url = `/api/method/marketinghub.api.meta_ads.get_row_detail?etiquetas_json=${encodeURIComponent(JSON.stringify([...rowEts]))}&filter_lead_creation=1`;
  if (df) url += `&date_from=${df}`;
  if (dt) url += `&date_to=${dt}`;

  try {
    const res = await fetch(url, { headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token } });
    const json = await res.json();
    const leads = json.message || [];
    renderAllLeadsModal(leads, row, statsEl, bodyEl);
  } catch (err) {
    bodyEl.innerHTML = `<div style="text-align:center;padding:40px;color:var(--danger);">Error: ${err.message}</div>`;
  }
};

function renderAllLeadsModal(leads, row, statsEl, bodyEl) {
  const total = leads.length;
  const clientes = leads.filter(l => l.es_cliente).length;
  const sinGestion = leads.filter(l => !l.estado_erp || l.estado_erp === 'Nuevo').length;

  statsEl.innerHTML = `
    <div class="rdm-stat"><div class="rdm-stat-value">${total}</div><div class="rdm-stat-label">Leads totales</div></div>
    <div class="rdm-stat"><div class="rdm-stat-value">${clientes}</div><div class="rdm-stat-label">Clientes</div></div>
    <div class="rdm-stat"><div class="rdm-stat-value">${sinGestion}</div><div class="rdm-stat-label">Sin gestionar</div></div>
  `;

  const subtitleEl = document.getElementById('rdmSubtitle');
  if (subtitleEl) subtitleEl.textContent = `${total} leads encontrados`;

  if (total === 0) {
    bodyEl.innerHTML = '<div style="text-align:center;padding:60px;color:var(--text-muted);">No se encontraron leads para estas etiquetas.</div>';
    return;
  }

  bodyEl.innerHTML = leads.map(lead => {
    const tags = (lead.etiquetas || '').split(',').map(t => t.trim()).filter(Boolean);
    const tagsHtml = tags.map(t => `<span class="rdm-tag">${t}</span>`).join('');
    const fechaCreacion = lead.creacion ? lead.creacion.split(' ')[0].split('-').reverse().join('/') : '';
    const leadLabel = lead.nombre || lead.lead_name;

    // Estado badge
    const estado = lead.estado_erp || lead.status || 'Nuevo';
    const estadoColors = {
      'Cliente': { bg: '#ecfdf5', color: '#065f46' },
      'Interesado': { bg: '#eff6ff', color: '#1e40af' },
      'No interesado': { bg: '#fef2f2', color: '#991b1b' },
      'Nuevo': { bg: '#f3f4f6', color: '#6b7280' },
    };
    const ec = estadoColors[estado] || estadoColors['Nuevo'];
    const estadoBadge = `<span class="rdm-tag" style="background:${ec.bg};color:${ec.color};border-color:${ec.bg};font-weight:600;">${estado}</span>`;

    // Chatwoot link
    let chatwootHtml = '';
    if (lead.chatwoot_id) {
      try {
        const ids = lead.chatwoot_id.split('|');
        const lastPart = ids[ids.length - 1].trim().split(':');
        const convId = lastPart.length === 2 ? lastPart[1] : lastPart[0];
        const cwLink2 = getChatwootLink(convId);
        if (convId && !isNaN(convId) && cwLink2) {
          chatwootHtml = `<a href="${cwLink2}" target="_blank" class="btn-chat-action" style="border-color:#00a884;color:#00a884;font-size:0.72rem;padding:2px 8px;" title="Chatwoot">&#8599; Chat</a>`;
        }
      } catch(_) {}
    }

    // Facturas resumen
    let facturasHtml = '';
    if (lead.facturas.length > 0) {
      const totalFact = lead.facturas.reduce((s, f) => s + f.total, 0);
      facturasHtml = `<span style="font-size:0.72rem;color:var(--text-muted);margin-left:6px;">${lead.facturas.length} factura${lead.facturas.length > 1 ? 's' : ''} (${money(totalFact)})</span>`;
    }

    return `
      <div class="rdm-lead-card" style="padding:12px 24px;">
        <div class="rdm-lead-header">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
            <span class="rdm-lead-name" style="font-size:0.88rem;">${leadLabel}</span>
            <span class="rdm-lead-phone">${lead.telefono || ''}</span>
            ${estadoBadge}
            ${facturasHtml}
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            <button class="btn-chat-action btn-ver-mensajes" data-lead="${lead.lead_name}" data-leadname="${(leadLabel || '').replace(/"/g,'&quot;')}" style="font-size:0.72rem;padding:2px 8px;" title="Ver conversación">Mensajes</button>
            ${chatwootHtml}
            <span style="font-size:0.72rem;color:var(--text-muted);">${fechaCreacion}</span>
          </div>
        </div>
        <div class="rdm-lead-tags" style="margin-top:4px;">${tagsHtml}</div>
        ${lead.responsable ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:2px;">Responsable: ${lead.responsable}</div>` : ''}
        ${lead.notas ? `<div style="font-size:0.72rem;color:var(--text-muted);margin-top:2px;font-style:italic;">Nota: ${lead.notas}</div>` : ''}
      </div>`;
  }).join('');

  // Bind "Ver Mensajes"
  bodyEl.querySelectorAll('.btn-ver-mensajes').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      mostrarConversacion(btn.dataset.lead, btn.dataset.leadname);
    });
  });
}

window.closeRowDetailModal = () => {
  const modal = document.getElementById('rowDetailModal');
  if (modal) modal.classList.add('hidden');
};

// ── Filtered Leads Modal (Leads filtro column) ──
window.openFilteredLeadsModal = async (rowId) => {
  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;
  const rowEts = state.rowEtiquetas[row.id];
  if (!rowEts || rowEts.size === 0) return;

  const modal = document.getElementById('rowDetailModal');
  const titleEl = document.getElementById('rdmTitle');
  const subtitleEl = document.getElementById('rdmSubtitle');
  const statsEl = document.getElementById('rdmStats');
  const bodyEl = document.getElementById('rdmBody');
  if (!modal) return;

  const selectedEts = state.mainEtiquetasSelected || [];
  const filterMode = state.mainFilterMode || 'OR';

  titleEl.textContent = row.name;
  subtitleEl.textContent = `Filtro (${filterMode}): ${selectedEts.join(', ')}`;
  statsEl.innerHTML = '';
  bodyEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">Cargando leads filtrados...</div>';
  modal.classList.remove('hidden');

  // Pasa fechas para filtrar facturas por posting_date
  const { from: df, to: dt } = getDateRange();
  let url = `/api/method/marketinghub.api.meta_ads.get_row_detail?etiquetas_json=${encodeURIComponent(JSON.stringify([...rowEts]))}`;
  if (df) url += `&date_from=${df}`;
  if (dt) url += `&date_to=${dt}`;

  try {
    const res = await fetch(url, { headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token } });
    const json = await res.json();
    const allLeads = json.message || [];

    // Filter: only leads with at least 1 invoice that also match selected etiquetas
    const filtered = allLeads.filter(lead => {
      if (!lead.facturas || lead.facturas.length === 0) return false;
      const leadTags = (lead.etiquetas || '').split(',').map(t => t.trim()).filter(Boolean);
      if (filterMode === 'AND') {
        return selectedEts.every(et => leadTags.includes(et));
      } else {
        return selectedEts.some(et => leadTags.includes(et));
      }
    });

    renderAllLeadsModal(filtered, row, statsEl, bodyEl);
    // Update subtitle with count
    subtitleEl.textContent = `${filtered.length} leads filtrados (${filterMode}: ${selectedEts.join(', ')})`;
  } catch (err) {
    bodyEl.innerHTML = `<div style="text-align:center;padding:40px;color:var(--danger);">Error: ${err.message}</div>`;
  }
};

// ── Cliente Leads Modal (Leads Cliente column) ──
// Filtra facturas por posting_date (no leads por creation) — coherente con columna Leads Cliente
window.openClienteLeadsModal = async (rowId) => {
  const row = state.rows.find(r => r.id === rowId);
  if (!row) return;
  const rowEts = state.rowEtiquetas[row.id];
  if (!rowEts || rowEts.size === 0) return;

  const modal = document.getElementById('rowDetailModal');
  const titleEl = document.getElementById('rdmTitle');
  const subtitleEl = document.getElementById('rdmSubtitle');
  const statsEl = document.getElementById('rdmStats');
  const bodyEl = document.getElementById('rdmBody');
  if (!modal) return;

  titleEl.textContent = row.name;
  subtitleEl.textContent = `Etiquetas: ${[...rowEts].join(', ')}`;
  statsEl.innerHTML = '';
  bodyEl.innerHTML = '<div style="text-align:center;padding:40px;color:var(--text-muted);">Cargando clientes con factura...</div>';
  modal.classList.remove('hidden');

  let editBtn = modal.querySelector('.btn-edit-camp-header');
  if (!editBtn) {
    editBtn = document.createElement('button');
    editBtn.className = 'btn-edit-camp btn-edit-camp-header';
    editBtn.style.cssText = 'margin-right:12px;padding:6px 14px;font-size:0.78rem;';
    editBtn.innerHTML = '&#9998; Editar Config';
    const closeBtn = modal.querySelector('.rdm-header button:last-child');
    if (closeBtn) closeBtn.parentElement.insertBefore(editBtn, closeBtn);
  }
  editBtn.onclick = () => window.openEditCampModal(row);

  // Pasa fechas para filtrar facturas por posting_date (no leads por creation)
  const { from: df, to: dt } = getDateRange();
  let url = `/api/method/marketinghub.api.meta_ads.get_row_detail?etiquetas_json=${encodeURIComponent(JSON.stringify([...rowEts]))}`;
  if (df) url += `&date_from=${df}`;
  if (dt) url += `&date_to=${dt}`;
  try {
    const res = await fetch(url, { headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token } });
    const json = await res.json();
    const leads = json.message || [];
    renderRowDetailModal(leads, row, statsEl, bodyEl);
  } catch (err) {
    bodyEl.innerHTML = `<div style="text-align:center;padding:40px;color:var(--danger);">Error al cargar: ${err.message}</div>`;
  }
};

// ── Chat Conversation Modal ──

function getChatwootLink(fullId) {
  if (!fullId) return null;
  const cfg = window.META_ADS_CHATWOOT;
  if (!cfg || !cfg.url || !cfg.account_id) return null;
  const parts = fullId.split(':');
  const id = parts.length > 1 ? parts[parts.length - 1] : parts[0];
  if (!id || isNaN(id)) return null;
  return `${cfg.url}/app/accounts/${cfg.account_id}/conversations/${id}`;
}

function mostrarConversacion(leadName, leadDisplayName) {
  frappe.call({
    method: 'marketinghub.api.meta_ads.get_conversation',
    args: { lead_name: leadName },
    freeze: true,
    freeze_message: 'Cargando conversación...',
    callback: function (r) {
      if (!r.message) {
        frappe.msgprint('No se pudieron cargar los mensajes.');
        return;
      }
      const { cuentas, mensajes } = r.message;
      if (!Object.keys(mensajes).length) {
        frappe.msgprint('No hay mensajes de WhatsApp para este lead.');
        return;
      }
      renderChatModal(leadDisplayName, cuentas, mensajes);
    }
  });
}

function renderChatModal(leadName, cuentas, mensajes) {
  const existing = document.getElementById('metaAdsChatOverlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'metaAdsChatOverlay';
  overlay.className = 'chat-overlay';

  const multiCuentas = cuentas.length > 1;
  let tabsHtml = '';
  if (multiCuentas) {
    tabsHtml = `<div class="chat-tabs">
      <button class="chat-tab active" data-panel="__todos">Todos</button>
      ${cuentas.map(c => `<button class="chat-tab" data-panel="${c.id}">${c.label}</button>`).join('')}
    </div>`;
  }

  let allMsgs = [];
  Object.values(mensajes).forEach(list => allMsgs = allMsgs.concat(list));
  allMsgs.sort((a, b) => new Date(a.creation) - new Date(b.creation));

  let panelsHtml = `<div class="chat-panels">
    <div class="chat-panel active" id="chatPanel-__todos">${generarHtmlMensajes(allMsgs)}</div>
    ${cuentas.map(c => {
      const msgs = (mensajes[c.id] || []).sort((a, b) => new Date(a.creation) - new Date(b.creation));
      return `<div class="chat-panel" id="chatPanel-${c.id}" style="display:none;">${generarHtmlMensajes(msgs)}</div>`;
    }).join('')}
  </div>`;

  // Chatwoot link button
  let initialLink = null;
  if (cuentas.length === 1 && cuentas[0].id !== 'sin_cuenta') {
    initialLink = getChatwootLink(cuentas[0].id);
  }
  const chatwootBtnId = 'metaAdsChatwootBtn';
  const chatwootBtnHtml = `<a id="${chatwootBtnId}" href="${initialLink || '#'}" target="_blank" class="btn-chatwoot-link" style="display:${initialLink ? 'inline-block' : 'none'}; margin-right:15px;">
    &#8599; Ir a Conversación
  </a>`;

  overlay.innerHTML = `<div class="chat-container">
    <div class="chat-header">
      <div class="chat-header-title">Conversación - ${leadName}</div>
      <div style="display:flex;align-items:center;">
        ${chatwootBtnHtml}
        <button class="chat-header-close" onclick="window.closeChatModal()">&times;</button>
      </div>
    </div>
    <div class="chat-body">
      ${tabsHtml}
      ${panelsHtml}
    </div>
  </div>`;

  document.body.appendChild(overlay);

  // Close on overlay click (not container)
  overlay.addEventListener('click', (e) => { if (e.target === overlay) window.closeChatModal(); });

  if (multiCuentas) {
    const tabs = overlay.querySelectorAll('.chat-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const targetId = tab.dataset.panel;
        overlay.querySelectorAll('.chat-panel').forEach(p => { p.style.display = 'none'; p.classList.remove('active'); });
        const targetPanel = overlay.querySelector(`#chatPanel-${targetId}`);
        if (targetPanel) { targetPanel.style.display = 'block'; targetPanel.classList.add('active'); targetPanel.scrollTop = targetPanel.scrollHeight; }
        // Update chatwoot button
        const btn = document.getElementById(chatwootBtnId);
        if (btn) {
          if (targetId === '__todos' || targetId === 'sin_cuenta') { btn.style.display = 'none'; }
          else {
            const link = getChatwootLink(targetId);
            if (link) { btn.href = link; btn.style.display = 'inline-block'; } else { btn.style.display = 'none'; }
          }
        }
      });
    });
  }

  setTimeout(() => {
    const activePanel = overlay.querySelector('.chat-panel.active');
    if (activePanel) activePanel.scrollTop = activePanel.scrollHeight;
  }, 100);
}

function generarHtmlMensajes(mensajes) {
  if (!mensajes || !mensajes.length) return '<div style="text-align:center;padding:20px;color:#999;">No hay mensajes.</div>';
  return mensajes.map(msg => {
    const content = msg.content || '';
    const isClient = content.includes('(Cliente)');
    const cssClass = isClient ? 'cliente' : 'agente';
    let body = content.replace(/<div.*?>.*?WhatsApp.*?<\/div>/i, '').trim();
    if (!body) body = content;
    const fullTime = frappe.datetime.str_to_user(msg.creation);
    return `<div class="msg-row ${cssClass}"><div class="msg-bubble">${body}<div class="msg-meta">${fullTime}</div></div></div>`;
  }).join('');
}

window.closeChatModal = () => {
  const ov = document.getElementById('metaAdsChatOverlay');
  if (ov) ov.remove();
};

// ── Edit Campaign Modal ──
let _editCampState = null; // { campana, row }
let _ecmEtiquetasLead = []; // local copy with palabras_clave
let _ecmPendingTagSelId = null;

window.openEditCampModal = async function(row) {
  const metaId = row.id;
  let campana = null;
  for (const camp of state.campanasData) {
    if (camp.meta_id === metaId) { campana = camp; break; }
    for (const conj of camp.conjuntos || []) {
      if (conj.meta_id === metaId) { campana = camp; break; }
      for (const an of conj.anuncios || []) {
        if (an.meta_id === metaId) { campana = camp; break; }
      }
      if (campana) break;
    }
    if (campana) break;
  }

  if (!campana) {
    alert('No se encontró la campaña asociada en el ERP. Verifica que esté sincronizada en Campañas Meta.');
    return;
  }

  // Load etiquetas with palabras_clave
  try {
    const res = await new Promise(resolve => {
      frappe.call({
        method: 'marketinghub.www.campanas_meta.index.obtener_etiquetas_lead',
        callback: r => resolve(r.message || [])
      });
    });
    _ecmEtiquetasLead = res;
  } catch (_) { _ecmEtiquetasLead = []; }

  _editCampState = { campana: JSON.parse(JSON.stringify(campana)), row };
  const modal = document.getElementById('editCampModal');
  document.getElementById('ecmTitle').textContent = `Editar: ${campana.nombre}`;

  _renderEditCampBody(document.getElementById('ecmBody'));
  _inyectarModalEtiquetaEcm();
  modal.classList.remove('hidden');
};

function _escHtml(s) { return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

function _renderEditCampBody(bodyEl) {
  const c = _editCampState.campana;
  const conjuntos = c.conjuntos || [];

  let conjListHtml = conjuntos.map((conj, ci) => `
    <div class="ecm-conj-item ${ci === 0 ? 'active' : ''}" data-ci="${ci}" onclick="window._ecmSelectConj(${ci})">
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${conj.nombre || '(sin nombre)'}</span>
      <span class="ecm-conj-item-meta">${(conj.anuncios || []).length} anuncio${(conj.anuncios || []).length !== 1 ? 's' : ''}</span>
    </div>
  `).join('');

  if (!conjuntos.length) {
    conjListHtml = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;">Sin conjuntos</div>';
  }

  bodyEl.innerHTML = `
    <div class="ecm-tree">
      <div class="ecm-tree-left">
        <div class="ecm-camp-panel">
          <div class="ecm-section-title">Campaña</div>
          <div class="ecm-field">
            <label>Nombre</label>
            <input type="text" id="ecm-camp-nombre" value="${_escHtml(c.nombre)}">
          </div>
          <div class="ecm-field-row">
            <div class="ecm-field" style="flex:1;">
              <label>Objetivo</label>
              <select id="ecm-camp-objetivo">
                <option value="">Sin objetivo</option>
                <option value="OUTCOME_LEADS" ${c.objetivo === 'OUTCOME_LEADS' ? 'selected' : ''}>Leads</option>
                <option value="OUTCOME_SALES" ${c.objetivo === 'OUTCOME_SALES' ? 'selected' : ''}>Ventas</option>
                <option value="OUTCOME_TRAFFIC" ${c.objetivo === 'OUTCOME_TRAFFIC' ? 'selected' : ''}>Tráfico</option>
                <option value="OUTCOME_ENGAGEMENT" ${c.objetivo === 'OUTCOME_ENGAGEMENT' ? 'selected' : ''}>Interacción</option>
                <option value="OUTCOME_AWARENESS" ${c.objetivo === 'OUTCOME_AWARENESS' ? 'selected' : ''}>Reconocimiento</option>
              </select>
            </div>
          </div>
          ${c.meta_id ? `<div style="font-size:10px;color:var(--text-muted);margin-top:2px;">Meta ID: ${c.meta_id}</div>` : ''}
        </div>
        <div class="ecm-conj-list-header">Conjuntos de anuncios</div>
        <div class="ecm-conj-list" id="ecmConjList">${conjListHtml}</div>
      </div>
      <div class="ecm-tree-right" id="ecmRightPanel">
        ${conjuntos.length ? '' : '<div class="ecm-right-empty">Selecciona un conjunto para editar</div>'}
      </div>
    </div>
  `;

  if (conjuntos.length) {
    _ecmRenderConjDetail(0);
  }
}

window._ecmSelectConj = function(ci) {
  // Save current edits before switching
  _ecmSaveCurrentConjEdits();

  document.querySelectorAll('.ecm-conj-item').forEach(el => el.classList.remove('active'));
  const item = document.querySelector(`.ecm-conj-item[data-ci="${ci}"]`);
  if (item) item.classList.add('active');
  _ecmRenderConjDetail(ci);
};

function _ecmSaveCurrentConjEdits() {
  const rightPanel = document.getElementById('ecmRightPanel');
  if (!rightPanel || !_editCampState) return;
  const ciAttr = rightPanel.dataset.activeCi;
  if (ciAttr === undefined || ciAttr === '') return;
  const ci = parseInt(ciAttr);
  const conj = _editCampState.campana.conjuntos[ci];
  if (!conj) return;

  const nombreInput = rightPanel.querySelector('.ecm-conj-nombre');
  const valorInput = rightPanel.querySelector('.ecm-conj-valor');
  if (nombreInput) conj.nombre = nombreInput.value.trim();
  if (valorInput) conj.valor = parseFloat(valorInput.value) || 0;

  (conj.anuncios || []).forEach((an, ai) => {
    const nameInput = rightPanel.querySelector(`.ecm-an-name[data-ai="${ai}"]`);
    const tagSel = document.getElementById(`ecm-tag-${ci}-${ai}`);
    if (nameInput) an.nombre = nameInput.value.trim();
    if (tagSel) an.etiqueta = tagSel.dataset.value || '';
  });

  // Update left panel label
  const item = document.querySelector(`.ecm-conj-item[data-ci="${ci}"]`);
  if (item) {
    const span = item.querySelector('span');
    if (span) span.textContent = conj.nombre || '(sin nombre)';
  }
}

function _ecmRenderConjDetail(ci) {
  const rightPanel = document.getElementById('ecmRightPanel');
  if (!rightPanel || !_editCampState) return;
  rightPanel.dataset.activeCi = ci;
  const conj = _editCampState.campana.conjuntos[ci];
  if (!conj) return;

  const anuncios = conj.anuncios || [];

  const adsHtml = anuncios.length ? anuncios.map((an, ai) => {
    const selId = `ecm-tag-${ci}-${ai}`;
    return `
      <div class="ecm-ad-card">
        <div class="ecm-ad-card-header">
          <input type="text" class="ecm-an-name" data-ci="${ci}" data-ai="${ai}" value="${_escHtml(an.nombre)}" placeholder="Nombre del anuncio">
          <span class="ecm-an-metaid">${an.meta_id ? 'ID: ' + an.meta_id : ''}</span>
        </div>
        ${_buildEcmTagSelector(selId, an.etiqueta || '')}
      </div>`;
  }).join('') : '<div style="padding:14px;text-align:center;color:var(--text-muted);font-size:13px;">Sin anuncios configurados</div>';

  rightPanel.innerHTML = `
    <div class="ecm-right-header">
      <h4>Conjunto: ${_escHtml(conj.nombre || '(sin nombre)')}</h4>
      ${conj.meta_id ? `<span style="font-size:10px;color:var(--text-muted);margin-left:auto;">ID: ${conj.meta_id}</span>` : ''}
    </div>
    <div class="ecm-right-body">
      <div class="ecm-conj-fields">
        <div class="ecm-field">
          <label>Nombre del conjunto</label>
          <input type="text" class="ecm-conj-nombre" data-ci="${ci}" value="${_escHtml(conj.nombre)}">
        </div>
        <div class="ecm-field">
          <label>Presupuesto diario (S/)</label>
          <input type="number" class="ecm-conj-valor" data-ci="${ci}" value="${conj.valor || 0}" step="0.01" min="0">
        </div>
      </div>
      <div class="ecm-ads-section">
        <div class="ecm-ads-header">Anuncios (${anuncios.length})</div>
        <div class="ecm-ads-list">${adsHtml}</div>
      </div>
    </div>
  `;
}

// ── Tag Selector (replicates campanas_meta pattern) ──

function _buildEcmTagSelector(selId, valorActual) {
  const tag = _ecmEtiquetasLead.find(t => t.name === valorActual);
  const kw = tag ? (tag.palabras_clave || '') : '';
  const hasTag = !!valorActual;

  return `
    <div class="ecm-tag-selector" id="${selId}" data-value="${_escHtml(valorActual)}">
      <input type="hidden" class="ecm-tag-value" value="${_escHtml(valorActual)}">
      <div class="ecm-tag-trigger" onclick="window._ecmAbrirTagDropdown('${selId}')">
        ${hasTag
          ? `<span class="ecm-tag-badge">${_escHtml(valorActual)}</span>`
          : `<span class="ecm-tag-placeholder">Seleccionar etiqueta...</span>`
        }
        ${hasTag ? `<button class="ecm-tag-clear-btn" onclick="event.stopPropagation(); window._ecmEditarEtiqueta('${_escHtml(valorActual)}', '${selId}')" title="Editar activadores">&#9998;</button>` : ''}
        ${hasTag ? `<button class="ecm-tag-clear-btn" onclick="event.stopPropagation(); window._ecmLimpiarEtiqueta('${selId}')" title="Quitar etiqueta">&times;</button>` : ''}
        <span style="color:var(--text-muted);font-size:0.7rem;flex-shrink:0;">&#9662;</span>
      </div>
      ${hasTag && kw ? `<div class="ecm-tag-kw-preview">&#9889; ${_escHtml(kw)}</div>` : ''}
    </div>`;
}

window._ecmAbrirTagDropdown = function(selId) {
  // Close any open dropdown
  document.querySelectorAll('.ecm-tag-dropdown').forEach(d => d.remove());

  const selector = document.getElementById(selId);
  if (!selector) return;
  const valorActual = selector.dataset.value;

  const dropdown = document.createElement('div');
  dropdown.className = 'ecm-tag-dropdown';
  dropdown.id = `${selId}-dropdown`;

  dropdown.innerHTML = `
    <div class="ecm-tag-dd-search">
      <input type="text" class="ecm-tag-dd-input" placeholder="Buscar etiqueta..."
             oninput="window._ecmFiltrarDropdown('${selId}', this.value)" autocomplete="off">
    </div>
    <div class="ecm-tag-dd-list" id="${selId}-dd-list">
      ${_ecmRenderTagOptions(selId, '', valorActual)}
    </div>
    <div class="ecm-tag-dd-footer">
      <button class="btn btn-secondary" style="width:100%;padding:6px;font-size:0.78rem;" onclick="window._ecmCrearEtiqueta('${selId}')">
        + Nueva etiqueta
      </button>
    </div>
  `;

  document.body.appendChild(dropdown);

  // Position below trigger
  const trigger = selector.querySelector('.ecm-tag-trigger');
  const rect = (trigger || selector).getBoundingClientRect();
  dropdown.style.top = (rect.bottom + 4) + 'px';
  dropdown.style.left = rect.left + 'px';
  dropdown.style.width = Math.max(rect.width, 260) + 'px';

  setTimeout(() => dropdown.querySelector('.ecm-tag-dd-input')?.focus(), 50);

  // Close on outside click
  setTimeout(() => {
    document.addEventListener('click', function _cerrar(e) {
      if (!selector.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.remove();
        document.removeEventListener('click', _cerrar);
      }
    });
  }, 10);
};

function _ecmRenderTagOptions(selId, query, valorActual) {
  const q = (query || '').toLowerCase().trim();
  const tags = q
    ? _ecmEtiquetasLead.filter(t => t.name.toLowerCase().includes(q) || (t.palabras_clave || '').toLowerCase().includes(q))
    : _ecmEtiquetasLead;

  if (!tags.length) return '<div class="ecm-tag-dd-empty">Sin resultados</div>';

  return tags.map(t => {
    const isActive = t.name === valorActual;
    const kw = t.palabras_clave ? `<div class="ecm-tag-dd-kw">&#9889; ${_escHtml(t.palabras_clave)}</div>` : '';
    return `
      <div class="ecm-tag-dd-option ${isActive ? 'active' : ''}">
        <div class="ecm-tag-dd-option-main" onclick="window._ecmSeleccionarEtiqueta('${selId}', '${_escHtml(t.name)}')">
          <div class="ecm-tag-dd-name">${_escHtml(t.name)}</div>
          ${kw}
        </div>
        <button class="ecm-tag-dd-edit" onclick="event.stopPropagation(); window._ecmEditarEtiqueta('${_escHtml(t.name)}', '${selId}')" title="Editar activadores">&#9998;</button>
      </div>`;
  }).join('');
}

window._ecmFiltrarDropdown = function(selId, query) {
  const selector = document.getElementById(selId);
  const listEl = document.getElementById(`${selId}-dd-list`);
  if (!listEl) return;
  listEl.innerHTML = _ecmRenderTagOptions(selId, query, selector?.dataset.value || '');
};

window._ecmSeleccionarEtiqueta = function(selId, tagName) {
  const selector = document.getElementById(selId);
  if (!selector) return;
  document.getElementById(`${selId}-dropdown`)?.remove();

  selector.dataset.value = tagName;
  const hidden = selector.querySelector('.ecm-tag-value');
  if (hidden) hidden.value = tagName;

  const tag = _ecmEtiquetasLead.find(t => t.name === tagName);
  const kw = tag?.palabras_clave || '';
  const trigger = selector.querySelector('.ecm-tag-trigger');
  if (trigger) {
    trigger.innerHTML = `
      <span class="ecm-tag-badge">${_escHtml(tagName)}</span>
      <button class="ecm-tag-clear-btn" onclick="event.stopPropagation(); window._ecmEditarEtiqueta('${_escHtml(tagName)}', '${selId}')" title="Editar activadores">&#9998;</button>
      <button class="ecm-tag-clear-btn" onclick="event.stopPropagation(); window._ecmLimpiarEtiqueta('${selId}')" title="Quitar etiqueta">&times;</button>
      <span style="color:var(--text-muted);font-size:0.7rem;flex-shrink:0;">&#9662;</span>
    `;
  }
  let kwEl = selector.querySelector('.ecm-tag-kw-preview');
  if (kw) {
    if (!kwEl) {
      kwEl = document.createElement('div');
      kwEl.className = 'ecm-tag-kw-preview';
      trigger?.after(kwEl);
    }
    kwEl.innerHTML = `&#9889; ${_escHtml(kw)}`;
  } else if (kwEl) {
    kwEl.remove();
  }
};

window._ecmLimpiarEtiqueta = function(selId) {
  const selector = document.getElementById(selId);
  if (!selector) return;
  selector.dataset.value = '';
  const hidden = selector.querySelector('.ecm-tag-value');
  if (hidden) hidden.value = '';
  const trigger = selector.querySelector('.ecm-tag-trigger');
  if (trigger) {
    trigger.innerHTML = `
      <span class="ecm-tag-placeholder">Seleccionar etiqueta...</span>
      <span style="color:var(--text-muted);font-size:0.7rem;flex-shrink:0;">&#9662;</span>
    `;
  }
  selector.querySelector('.ecm-tag-kw-preview')?.remove();
};

// ── Crear / Editar Etiqueta modal (within edit camp) ──

let _ecmEtiquetaModoEdicion = false;
let _ecmEtiquetaEditandoNombre = null;

function _inyectarModalEtiquetaEcm() {
  if (document.getElementById('ecm-modal-etiqueta')) return;
  const div = document.createElement('div');
  div.innerHTML = `
    <div id="ecm-modal-etiqueta" class="ecm-etiqueta-overlay hidden" onclick="if(event.target===this) window._ecmCerrarModalEtiqueta()">
      <div class="ecm-etiqueta-modal" onclick="event.stopPropagation()">
        <div class="ecm-etiqueta-header">
          <h4 id="ecm-etiqueta-title" style="margin:0;font-size:0.95rem;font-weight:700;">Nueva Etiqueta Lead</h4>
          <button onclick="window._ecmCerrarModalEtiqueta()" style="background:none;border:none;font-size:1.3rem;cursor:pointer;color:var(--text-muted);">&times;</button>
        </div>
        <div style="padding:16px;display:flex;flex-direction:column;gap:12px;">
          <div>
            <label style="font-size:0.72rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;display:block;margin-bottom:4px;">Nombre de la etiqueta</label>
            <input type="text" id="ecm-etiqueta-nombre" class="select" placeholder="Ej: Interesado Calzado" autocomplete="off">
          </div>
          <div>
            <label style="font-size:0.72rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;display:block;margin-bottom:4px;">Activadores (palabras clave, separadas por coma)</label>
            <textarea id="ecm-etiqueta-palabras" class="select" placeholder="Ej: zapatos, calzado, sandalias" rows="3" style="resize:vertical;"></textarea>
            <span style="font-size:0.68rem;color:var(--text-muted);">Cuando el chatbot detecte estas palabras asignará esta etiqueta al lead automáticamente.</span>
          </div>
        </div>
        <div style="padding:12px 16px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:8px;">
          <button class="btn btn-secondary" style="width:auto;padding:8px 16px;" onclick="window._ecmCerrarModalEtiqueta()">Cancelar</button>
          <button class="btn btn-primary" style="width:auto;padding:8px 16px;" id="ecm-btn-guardar-etiqueta" onclick="window._ecmGuardarEtiqueta()">Crear Etiqueta</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(div.firstElementChild);
}

window._ecmCrearEtiqueta = function(selId) {
  _ecmPendingTagSelId = selId;
  _ecmEtiquetaModoEdicion = false;
  _ecmEtiquetaEditandoNombre = null;
  document.querySelectorAll('.ecm-tag-dropdown').forEach(d => d.remove());

  const modal = document.getElementById('ecm-modal-etiqueta');
  document.getElementById('ecm-etiqueta-title').textContent = 'Nueva Etiqueta Lead';
  const nombreInput = document.getElementById('ecm-etiqueta-nombre');
  nombreInput.value = '';
  nombreInput.disabled = false;
  document.getElementById('ecm-etiqueta-palabras').value = '';
  document.getElementById('ecm-btn-guardar-etiqueta').textContent = 'Crear Etiqueta';
  modal.classList.remove('hidden');
  setTimeout(() => nombreInput.focus(), 100);
};

window._ecmEditarEtiqueta = function(tagName, selId) {
  _ecmPendingTagSelId = selId;
  _ecmEtiquetaModoEdicion = true;
  _ecmEtiquetaEditandoNombre = tagName;
  document.querySelectorAll('.ecm-tag-dropdown').forEach(d => d.remove());

  const tag = _ecmEtiquetasLead.find(t => t.name === tagName);
  const modal = document.getElementById('ecm-modal-etiqueta');
  document.getElementById('ecm-etiqueta-title').textContent = 'Editar Etiqueta Lead';
  const nombreInput = document.getElementById('ecm-etiqueta-nombre');
  nombreInput.value = tagName;
  nombreInput.disabled = true;
  document.getElementById('ecm-etiqueta-palabras').value = tag?.palabras_clave || '';
  document.getElementById('ecm-btn-guardar-etiqueta').textContent = 'Guardar Cambios';
  modal.classList.remove('hidden');
  setTimeout(() => document.getElementById('ecm-etiqueta-palabras').focus(), 100);
};

window._ecmGuardarEtiqueta = async function() {
  const btn = document.getElementById('ecm-btn-guardar-etiqueta');
  btn.disabled = true;
  btn.textContent = _ecmEtiquetaModoEdicion ? 'Guardando...' : 'Creando...';

  try {
    if (_ecmEtiquetaModoEdicion) {
      const palabras = document.getElementById('ecm-etiqueta-palabras').value.trim();
      await new Promise((resolve, reject) => {
        frappe.call({
          method: 'marketinghub.www.campanas_meta.index.actualizar_palabras_clave_etiqueta',
          args: { nombre: _ecmEtiquetaEditandoNombre, palabras_clave: palabras },
          callback: r => {
            if (r.message?.status === 'ok') {
              const tag = _ecmEtiquetasLead.find(t => t.name === _ecmEtiquetaEditandoNombre);
              if (tag) tag.palabras_clave = palabras;
              // Refresh preview in selector
              if (_ecmPendingTagSelId) {
                const selector = document.getElementById(_ecmPendingTagSelId);
                if (selector && selector.dataset.value === _ecmEtiquetaEditandoNombre) {
                  let kwEl = selector.querySelector('.ecm-tag-kw-preview');
                  if (palabras) {
                    if (!kwEl) {
                      kwEl = document.createElement('div');
                      kwEl.className = 'ecm-tag-kw-preview';
                      selector.querySelector('.ecm-tag-trigger')?.after(kwEl);
                    }
                    kwEl.innerHTML = `&#9889; ${_escHtml(palabras)}`;
                  } else if (kwEl) { kwEl.remove(); }
                }
              }
              _maToast(`Etiqueta "${_ecmEtiquetaEditandoNombre}" actualizada`, 'success');
              resolve();
            } else { reject(new Error('Error al actualizar')); }
          },
          error: reject
        });
      });
    } else {
      const nombre = document.getElementById('ecm-etiqueta-nombre').value.trim();
      const palabras = document.getElementById('ecm-etiqueta-palabras').value.trim();
      if (!nombre) { _maToast('El nombre de la etiqueta es obligatorio', 'error'); return; }
      await new Promise((resolve, reject) => {
        frappe.call({
          method: 'marketinghub.www.campanas_meta.index.crear_etiqueta_lead',
          args: { nombre, palabras_clave: palabras || '' },
          callback: r => {
            if (r.message?.status === 'ok') {
              _ecmEtiquetasLead.push({ name: r.message.name, palabras_clave: r.message.palabras_clave });
              _ecmEtiquetasLead.sort((a, b) => a.name.localeCompare(b.name));
              // Auto-select in the selector that triggered creation
              if (_ecmPendingTagSelId) {
                window._ecmSeleccionarEtiqueta(_ecmPendingTagSelId, r.message.name);
              }
              _maToast(`Etiqueta "${r.message.name}" creada`, 'success');
              resolve();
            } else { reject(new Error('Error al crear')); }
          },
          error: reject
        });
      });
    }
    window._ecmCerrarModalEtiqueta();
  } catch (err) {
    _maToast(err.message || 'Error al guardar la etiqueta', 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = _ecmEtiquetaModoEdicion ? 'Guardar Cambios' : 'Crear Etiqueta';
  }
};

window._ecmCerrarModalEtiqueta = function() {
  document.getElementById('ecm-modal-etiqueta')?.classList.add('hidden');
  _ecmPendingTagSelId = null;
};

// ── Save Campaign ──

// ── Toast ──
function _maToast(msg, tipo) {
  const toast = document.getElementById('maToast');
  if (!toast) return;
  toast.textContent = msg;
  toast.className = 'ma-toast show' + (tipo ? ' ' + tipo : '');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => toast.classList.remove('show'), 3500);
}

// ── Log Modal ──
function _mostrarLogGuardado(log) {
  if (!log || !log.length) {
    _maToast('Campaña guardada correctamente', 'success');
    return;
  }
  const errores = log.filter(l => l.tipo === 'error').length;
  const warns = log.filter(l => l.tipo === 'warn').length;
  const oks = log.filter(l => l.tipo === 'ok').length;

  const titleEl = document.getElementById('ecmLogTitle');
  if (errores > 0) {
    titleEl.innerHTML = '<span style="color:var(--danger);">⚠</span> Guardado con errores';
  } else if (warns > 0) {
    titleEl.innerHTML = '<span style="color:var(--warning);">⚠</span> Guardado con avisos';
  } else {
    titleEl.innerHTML = '<span style="color:var(--success);">✓</span> Guardado correctamente';
  }

  const bodyEl = document.getElementById('ecmLogBody');
  let html = `<div class="ecm-log-summary">
    <span class="ecm-log-summary-item" style="color:var(--success);">✓ ${oks} OK</span>
    <span class="ecm-log-summary-item" style="color:var(--warning);">⚠ ${warns} Avisos</span>
    <span class="ecm-log-summary-item" style="color:var(--danger);">✗ ${errores} Errores</span>
  </div>`;

  html += log.map(l => {
    const cls = l.tipo === 'ok' ? 'log-ok' : l.tipo === 'error' ? 'log-error' : 'log-warn';
    const icon = l.tipo === 'ok' ? '✓' : l.tipo === 'error' ? '✗' : '⚠';
    const color = l.tipo === 'ok' ? 'var(--success)' : l.tipo === 'error' ? 'var(--danger)' : 'var(--warning)';
    return `<div class="ecm-log-line ${cls}">
      <span class="ecm-log-line-icon" style="color:${color};">${icon}</span>
      <span class="ecm-log-line-msg">${_escHtml(l.msg)}</span>
    </div>`;
  }).join('');

  bodyEl.innerHTML = html;
  document.getElementById('ecmLogModal').classList.remove('hidden');
}

window.closeEcmLogModal = function() {
  document.getElementById('ecmLogModal')?.classList.add('hidden');
};

// ── Save Campaign ──
window.guardarEditCamp = async function() {
  if (!_editCampState) return;
  const c = _editCampState.campana;
  const saveBtn = document.getElementById('ecmSaveBtn');

  // Save current panel edits into state
  _ecmSaveCurrentConjEdits();

  const campNombre = document.getElementById('ecm-camp-nombre')?.value.trim() || c.nombre;
  const campObjetivo = document.getElementById('ecm-camp-objetivo')?.value || '';

  const conjuntos = (c.conjuntos || []).map(conj => ({
    name: conj.name || '',
    nombre: conj.nombre,
    valor: conj.valor || 0,
    anuncios: (conj.anuncios || []).map(an => ({
      name: an.name || '',
      nombre: an.nombre,
      etiqueta: an.etiqueta || ''
    }))
  }));

  if (!campNombre) { _maToast('El nombre de la campaña es obligatorio', 'error'); return; }

  saveBtn.disabled = true;
  saveBtn.textContent = 'Guardando...';

  try {
    const result = await new Promise((resolve, reject) => {
      frappe.call({
        method: 'marketinghub.www.campanas_meta.index.guardar_campana',
        args: {
          nombre: campNombre,
          conjuntos_json: JSON.stringify(conjuntos),
          objetivo: campObjetivo,
          nombre_original: c.name || ''
        },
        callback: r => resolve(r.message),
        error: reject
      });
    });

    if (result.status === 'ok') {
      window.closeEditCampModal();
      await loadErpMapping();
      if (state.rows.length) applyFiltersAndSort();
    }

    // Show log modal with detailed results
    _mostrarLogGuardado(result.log || []);

  } catch (err) {
    _maToast(err.message || 'Error al guardar', 'error');
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Guardar y Sincronizar';
  }
};

window.closeEditCampModal = function() {
  const modal = document.getElementById('editCampModal');
  if (modal) modal.classList.add('hidden');
  document.querySelectorAll('.ecm-tag-dropdown').forEach(d => d.remove());
  _editCampState = null;
};

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const logModal = document.getElementById('ecmLogModal');
    const etqModal = document.getElementById('ecm-modal-etiqueta');
    if (logModal && !logModal.classList.contains('hidden')) {
      window.closeEcmLogModal();
    } else if (etqModal && !etqModal.classList.contains('hidden')) {
      window._ecmCerrarModalEtiqueta();
    } else if (document.querySelector('.ecm-tag-dropdown')) {
      document.querySelectorAll('.ecm-tag-dropdown').forEach(d => d.remove());
    } else if (document.getElementById('editCampModal') && !document.getElementById('editCampModal').classList.contains('hidden')) {
      window.closeEditCampModal();
    } else {
      window.closeChatModal();
      window.closeRowDetailModal();
    }
  }
});

// Initial call
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
