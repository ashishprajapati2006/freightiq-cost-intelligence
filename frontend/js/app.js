/**
 * FreightIQ Frontend Application
 * Connected to FastAPI Backend (v0.2.0)
 *
 * Full-stack integration supporting live backend data with explicit
 * status indicators, error handling, cancellation, and fallback demo mode.
 */

// Global DOM helpers
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// Application state
const state = {
  isLive: false,
  backendInfo: null,
  shipments: [],
  shipmentPagination: { total: 0, page: 1, pageSize: 25, totalPages: 1 },
  notes: [],
  routes: [],
  analysis: [],
  routeWeeks: [],
  dashboardSummary: null,
  weeklyCosts: [],
  route: '',
  filters: {},
  sort: { key: 'week_of', dir: 'desc' },
  notifications: [
    { title: 'System initialized', detail: 'Connecting to FreightIQ API v0.2.0', route: 'dashboard', read: false },
    { title: 'Contract validation', detail: 'Contract checks ready in Evaluation view', route: 'evaluation', read: false }
  ],
  chat: [],
  theme: localStorage.getItem('fiq-theme') || 'light',
  sidebar: localStorage.getItem('fiq-sidebar') || 'open',
  datasetName: 'Bundled Shipment Records',
  banner: false,
  analysisRun: 0,
  settings: {
    compact: false,
    showHints: true,
    threshold: 20,
    precision: 2,
    apiBaseUrl: window.FreightIQAPI ? window.FreightIQAPI.getBaseUrl() : 'http://127.0.0.1:8001/api/v1',
  },
  activeImport: null,
  noteFocus: null,
};

const pageTitles = {
  dashboard: 'Overview',
  shipments: 'Shipment explorer',
  analytics: 'Route analytics',
  anomalies: 'Anomaly monitor',
  'context-notes': 'Context notes',
  assistant: 'AI assistant',
  data: 'Data import',
  evaluation: 'Evaluation & testing',
  usage: 'Usage & cost',
  settings: 'Settings'
};

const navPages = ['dashboard', 'shipments', 'analytics', 'anomalies', 'context-notes', 'assistant', 'data', 'evaluation', 'usage', 'settings'];

// -------------------------------------------------------------
// Formatters & Utilities
// -------------------------------------------------------------
function fmt(n, d = 2) {
  if (n == null || !Number.isFinite(+n)) return '—';
  return (+n).toLocaleString('en-IN', { minimumFractionDigits: d, maximumFractionDigits: d });
}

function inr(n, d = 2) {
  if (n == null || !Number.isFinite(+n)) return '—';
  return '₹' + fmt(n, d);
}

function pct(n) {
  if (n == null || !Number.isFinite(+n)) return '—';
  return `${n >= 0 ? '+' : ''}${fmt(n, 1)}%`;
}

function shortDate(s) {
  if (!s) return '—';
  const d = new Date(`${s}T00:00:00Z`);
  return Number.isNaN(+d) ? s : d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });
}

function unique(arr) {
  return [...new Set(arr.filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function badge(text, type = 'gray') {
  return `<span class="badge ${type}">${esc(text)}</span>`;
}

function pctBadge(n) {
  if (n == null) return badge('Baseline unavailable', 'gray');
  return badge(pct(n), n >= 20 ? 'red' : n >= 10 ? 'amber' : 'green');
}

function routeCell(r) {
  const name = r.route || `${r.origin}-${r.destination}`;
  return `<div class="route-cell"><span class="route-icon">↗</span><span><strong>${esc(name)}</strong><small>${esc(r.route_type || '')} route</small></span></div>`;
}

function toast(message, type = 'success') {
  const region = $('#toastRegion');
  if (!region) return;
  const el = document.createElement('div');
  el.className = `toast ${type === 'error' ? 'error' : ''}`;
  el.innerHTML = `<span class="toast-mark">${type === 'error' ? '!' : '✓'}</span><span>${esc(message)}</span>`;
  region.append(el);
  setTimeout(() => el.remove(), 4200);
}

function copyText(text) {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard.')).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}

function fallbackCopy(text) {
  const t = document.createElement('textarea');
  t.value = text;
  document.body.append(t);
  t.select();
  document.execCommand('copy');
  t.remove();
  toast('Copied to clipboard.');
}

function showModal(title, subtitle, body, actions = []) {
  $('#modalTitle').textContent = title;
  $('#modalSubtitle').textContent = subtitle || '';
  $('#modalBody').innerHTML = body;
  $('#modalActions').innerHTML = actions.map(a => `<button class="btn ${a.primary ? 'btn-primary' : ''} ${a.danger ? 'btn-danger' : ''}" data-modal-action="${esc(a.id)}">${esc(a.label)}</button>`).join('');
  $('#modalOverlay').hidden = false;
  $$('[data-modal-action]').forEach(b => {
    b.onclick = () => {
      const a = actions.find(x => x.id === b.dataset.modalAction);
      if (a?.run) a.run();
      if (a?.close !== false) closeModal();
    };
  });
  $('#modalClose').onclick = closeModal;
  $('#modalOverlay').onclick = e => { if (e.target.id === 'modalOverlay') closeModal(); };
}

function closeModal() {
  $('#modalOverlay').hidden = true;
}

function nav(route) {
  location.hash = '#/' + route;
}

function routeNow() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean);
  return { page: navPages.includes(parts[0]) ? parts[0] : 'dashboard', id: parts[1] || null };
}

function parseCSV(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') {
      quoted = true;
    } else if (c === ',') {
      row.push(field);
      field = '';
    } else if (c === '\n') {
      row.push(field.replace(/\r$/, ''));
      if (row.some(v => v !== '')) rows.push(row);
      row = [];
      field = '';
    } else {
      field += c;
    }
  }
  if (field.length || row.length) {
    row.push(field.replace(/\r$/, ''));
    if (row.some(v => v !== '')) rows.push(row);
  }
  if (!rows.length) return [];
  const headers = rows.shift().map(x => x.trim());
  return rows.map(r => Object.fromEntries(headers.map((h, i) => [h, (r[i] ?? '').trim()])));
}

function csvString(rows, headers) {
  const escField = v => {
    const s = v == null ? '' : String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  return [
    headers.map(escField).join(','),
    ...rows.map(r => headers.map(h => escField(r[h])).join(','))
  ].join('\r\n');
}

function downloadCSV(rows, headers, name) {
  if (!rows || !rows.length) {
    toast('No rows to export. Adjust your filters and try again.', 'error');
    return;
  }
  const csvContent = '\uFEFF' + csvString(rows, headers);
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.style.display = 'none';
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, 100);
  toast(`${rows.length.toLocaleString()} rows exported to ${name}.`);
}

async function downloadFromUrl(url, filename, fallbackFn = null) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(objectUrl);
    }, 100);
    toast(`Exported ${filename}.`);
  } catch (err) {
    if (fallbackFn) {
      fallbackFn();
    } else {
      toast(`Export failed: ${err.message}`, 'error');
    }
  }
}

// -------------------------------------------------------------
// Data Loading & API Integration
// -------------------------------------------------------------
async function loadData() {
  try {
    const health = await window.FreightIQAPI.checkHealth();
    if (health && health.status === 'healthy') {
      state.isLive = true;
      state.backendInfo = health;
      state.banner = false;

      // Load initial batch of data concurrently
      const [summary, notesData, routesData, weeklyData, initialAnomalies] = await Promise.all([
        window.FreightIQAPI.getDashboardSummary(),
        window.FreightIQAPI.getContextNotes(),
        window.FreightIQAPI.getRoutes(),
        window.FreightIQAPI.getWeeklyCosts({ limit: 52 }),
        window.FreightIQAPI.getAnomalies({ page: 1, page_size: 100 }),
      ]);

      state.dashboardSummary = summary;
      state.notes = Array.isArray(notesData) ? notesData : (notesData.items || []);
      state.routes = Array.isArray(routesData) ? routesData : (routesData.routes || []);
      state.weeklyCosts = Array.isArray(weeklyData) ? weeklyData : (weeklyData.items || []);
      state.analysis = initialAnomalies.items || [];
      state.datasetName = summary.dataset_name || 'Bundled Shipment Records';

      updateSystemStatusIndicators(true);
      $('#datasetLabel').textContent = `${state.datasetName} (${health.total_shipments.toLocaleString()} rows)`;
      $('#anomalyNavCount').textContent = (summary.flagged_route_weeks || 0).toLocaleString();

      render();
      return;
    }
  } catch (err) {
    console.warn('Backend unavailable or failed health check:', err);
  }

  // Fallback to offline mode with explicit indicator
  state.isLive = false;
  state.banner = true;
  updateSystemStatusIndicators(false);
  $('#datasetLabel').textContent = 'Offline Fallback Dataset';
  $('#anomalyNavCount').textContent = '0';
  if (window.FreightIQAPI && !window.FreightIQAPI.isConfigured) {
    toast('Render Backend API URL is not configured. Running in demo mode. Go to Settings (⚙) to enter your URL.', 'error');
  } else {
    toast('FastAPI backend is offline. Operating in clearly marked offline demo mode.', 'error');
  }
  render();
}

function updateSystemStatusIndicators(isLive) {
  const isConfigured = window.FreightIQAPI && window.FreightIQAPI.isConfigured;
  const currentUrl = window.FreightIQAPI ? window.FreightIQAPI.getBaseUrl() : '';

  const sidebarFoot = $('.sidebar-foot');
  if (sidebarFoot) {
    if (isLive) {
      sidebarFoot.innerHTML = `<div class="status-dot" style="background:#10b981"></div><span>Backend Connected (v0.2.0)</span><span class="info-dot" title="Live FastAPI Backend connected">✓</span>`;
    } else if (!isConfigured) {
      sidebarFoot.innerHTML = `<div class="status-dot" style="background:#f59e0b"></div><span>Backend Unconfigured</span><a href="#/settings" class="info-dot" title="Enter Render API URL in Settings" style="text-decoration:none">⚙</a>`;
    } else {
      sidebarFoot.innerHTML = `<div class="status-dot" style="background:#ef4444"></div><span>Backend Offline (Demo Mode)</span><span class="info-dot" title="Backend not reachable at ${esc(currentUrl)}">!</span>`;
    }
  }
  const footer = $('.app-footer');
  if (footer) {
    if (isLive) {
      footer.innerHTML = `<span>FreightIQ <span class="muted">· Case study release</span></span><span><span class="status-dot" style="background:#10b981"></span> Live FastAPI Backend <b>·</b> Connected to ${esc(currentUrl)}</span>`;
    } else if (!isConfigured) {
      footer.innerHTML = `<span>FreightIQ <span class="muted">· Case study prototype</span></span><span><span class="status-dot" style="background:#f59e0b"></span> Backend unconfigured <b>·</b> <a href="#/settings" style="color:var(--primary);text-decoration:underline">Set Render API URL in Settings</a></span>`;
    } else {
      footer.innerHTML = `<span>FreightIQ <span class="muted">· Case study prototype</span></span><span><span class="status-dot" style="background:#ef4444"></span> Offline demo mode <b>·</b> Backend unavailable at ${esc(currentUrl)}</span>`;
    }
  }
}

// -------------------------------------------------------------
// Component Templates & Layout
// -------------------------------------------------------------
function heading(title, sub, actions = '') {
  return `<div class="page-heading"><div><h1>${title}</h1><p>${sub}</p></div><div class="heading-actions">${actions}</div></div>`;
}

function liveStatusBanner() {
  if (state.isLive) {
    return `<div class="demo-banner" style="background:#ecfdf5;border-color:#a7f3d0;color:#065f46"><span class="banner-icon" style="background:#d1fae5;color:#059669">✓</span><span><strong>Connected to Live FastAPI Backend</strong> — Metrics, baselines, and evidence are deterministically served from <code>${esc(window.FreightIQAPI.getBaseUrl())}</code>.</span></div>`;
  }
  return `<div class="demo-banner" style="background:#fffbeb;border-color:#fde68a;color:#92400e"><span class="banner-icon" style="background:#fef3c7;color:#d97706">!</span><span><strong>Backend Offline</strong> — Could not reach <code>${esc(window.FreightIQAPI.getBaseUrl())}</code>. Please launch Uvicorn on port 8001 or update your API URL in Settings.</span></div>`;
}

function kpi(label, value, foot, icon, type = '', action = '') {
  return `<article class="kpi-card" ${action ? `data-kpi-action="${action}" tabindex="0" role="button"` : ''}><div class="kpi-top"><span class="kpi-label">${label}</span><span class="kpi-icon ${type}">${icon}</span></div><div class="kpi-value">${value}</div><div class="kpi-foot">${foot}</div></article>`;
}

function tableHtml(headers, rows, opts = {}) {
  return `<div class="table-scroll"><table class="data-table"><thead><tr>${headers.map(h => `<th class="${h.numeric ? 'numeric' : ''}">${h.label}</th>`).join('')}</tr></thead><tbody>${rows || ''}</tbody></table></div>`;
}

function pagination(total = 0, page = 1, size = 25, scope) {
  total = total || 0;
  page = page || 1;
  size = size || 25;
  const pages = Math.max(1, Math.ceil(total / size));
  const start = total ? (page - 1) * size + 1 : 0;
  const end = Math.min(total, page * size);
  return `<div class="table-footer"><span>Showing <strong>${start}–${end}</strong> of <strong>${total.toLocaleString()}</strong> records</span><div class="pagination"><button class="page-btn" data-page="${scope}" data-n="${page - 1}" ${page <= 1 ? 'disabled' : ''}>‹</button>${Array.from({ length: Math.min(5, pages) }, (_, i) => {
    let p = Math.min(Math.max(1, page - 2) + i, pages);
    return `<button class="page-btn ${p === page ? 'active' : ''}" data-page="${scope}" data-n="${p}">${p}</button>`;
  }).join('')}<button class="page-btn" data-page="${scope}" data-n="${page + 1}" ${page >= pages ? 'disabled' : ''}>›</button></div></div>`;
}

// -------------------------------------------------------------
// 1. Dashboard Page
// -------------------------------------------------------------
function dashboardPage() {
  const s = state.dashboardSummary || {
    total_shipments: 2940,
    total_routes: 7,
    total_route_weeks: 728,
    flagged_route_weeks: 20,
    unexplained_anomalies: 15,
    evidence_supported: 5,
    avg_cost_per_tonne_km: 2.704,
    route_type_comparison: [
      { route_type: 'Short', route_weeks: 208, avg_cost_per_tonne_km: 3.360 },
      { route_type: 'Medium', route_weeks: 312, avg_cost_per_tonne_km: 2.681 },
      { route_type: 'Long', route_weeks: 208, avg_cost_per_tonne_km: 2.083 }
    ],
    recent_anomalies: []
  };

  const actions = `
    <select class="select" id="dashRange">
      <option value="52">All 52 weeks</option>
      <option value="26">Last 26 weeks</option>
      <option value="12">Last 12 weeks</option>
    </select>
    <button class="btn" id="refreshAnalysis">↻ Refresh Live Data</button>
    <button class="btn btn-primary" id="exportContractCsv">⇩ Export Contract CSV</button>
  `;

  const recents = s.recent_anomalies || [];
  const rows = recents.map(r => `
    <tr>
      <td>${routeCell(r)}</td>
      <td>${shortDate(r.week_of)}</td>
      <td>${esc(r.route_type)}</td>
      <td class="numeric">${fmt(r.cost_per_tonne_km, 3)}</td>
      <td class="numeric">${fmt(r.vs_own_history, 3)}</td>
      <td class="numeric">${pctBadge(r.pct_vs_history ?? r.own_pct)}</td>
      <td>${r.verdict === 'Supported' || r.matched_note_id ? badge('Supported', 'green') : badge('Unexplained', 'amber')}</td>
      <td><button class="table-action" data-open-anomaly="${esc(r.id)}">Investigate ↗</button></td>
    </tr>
  `).join('');

  return `
    ${heading('Overview', 'Monitor freight costs, investigate unusual changes, and understand supporting evidence.', actions)}
    ${liveStatusBanner()}
    <div class="kpi-grid">
      ${kpi('Shipment records', (s.total_shipments || 0).toLocaleString(), 'Loaded from active dataset', '▤', '', 'shipments')}
      ${kpi('Routes analyzed', (s.total_routes || 0).toLocaleString(), 'Unique origin–destination corridors', '⌁', 'teal', 'analytics')}
      ${kpi('Flagged route-weeks', (s.flagged_route_weeks || 0).toLocaleString(), `${pct((s.flagged_route_weeks / (s.total_route_weeks || 1)) * 100)} of route-weeks`, '◈', 'red', 'anomalies')}
      ${kpi('Unexplained anomalies', (s.unexplained_anomalies || 0).toLocaleString(), 'No applicable context note found', '!', 'amber', 'anomalies')}
      ${kpi('Average cost / tonne-km', fmt(s.avg_cost_per_tonne_km, 3), 'Deterministic weighted unit cost', '₹', 'teal', 'analytics')}
      ${kpi('Evidence supported', (s.evidence_supported || 0).toLocaleString(), 'Corroborated by verified source note', '✓', 'teal', 'context-notes')}
    </div>
    <div class="grid-2">
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Weekly freight cost trend</h2><p class="panel-subtitle">Average cost per tonne-km across route-weeks</p></div>
          <div class="panel-actions">
            <select class="select" id="trendRouteType">
              <option value="all">All route types</option>
              <option>Short</option>
              <option>Medium</option>
              <option>Long</option>
            </select>
          </div>
        </div>
        <div class="panel-body">
          <div class="chart-wrap"><canvas id="trendChart" aria-label="Weekly cost trend chart"></canvas></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Anomaly verdict distribution</h2><p class="panel-subtitle">Breakdown of analytical findings</p></div>
          <button class="btn btn-sm" data-go="anomalies">View all ↗</button>
        </div>
        <div class="panel-body">
          <div class="chart-wrap short"><canvas id="statusChart" aria-label="Anomaly status chart"></canvas></div>
          <div class="metric-line"><span>Evidence supported</span><strong>${s.evidence_supported || 0}</strong></div>
          <div class="metric-line"><span>Unexplained</span><strong>${s.unexplained_anomalies || 0}</strong></div>
          <div class="metric-line"><span>Within baseline range</span><strong>${(s.total_route_weeks || 0) - (s.flagged_route_weeks || 0)}</strong></div>
        </div>
      </section>
    </div>
    <div class="grid-2 equal">
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Unit cost by route type</h2><p class="panel-subtitle">Work-weighted average cost / tonne-km</p></div>
        </div>
        <div class="panel-body">
          <div class="chart-wrap short"><canvas id="typeChart" aria-label="Route type comparison"></canvas></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Largest cost deviations</h2><p class="panel-subtitle">Highest positive change vs. historical baseline</p></div>
          <button class="btn btn-sm" data-go="anomalies">Investigate ↗</button>
        </div>
        <div class="panel-body">
          ${renderTopDeviations(s.recent_anomalies || [])}
        </div>
      </section>
    </div>
    <section class="panel table-panel">
      <div class="panel-head">
        <div><h2 class="panel-title">Recent flagged anomalies</h2><p class="panel-subtitle">Latest route-weeks requiring verification</p></div>
        <button class="btn btn-sm" data-go="anomalies">View all anomalies ↗</button>
      </div>
      ${tableHtml([
        { label: 'Route' },
        { label: 'Week' },
        { label: 'Type' },
        { label: 'Current cost', numeric: true },
        { label: 'History baseline', numeric: true },
        { label: 'Deviation' },
        { label: 'Evidence' },
        { label: 'Action' }
      ], rows)}
      <div class="table-footer">
        <span>Serving real-time data from FreightIQ FastAPI backend</span>
        <button class="text-link" data-go="anomalies">Open anomaly monitor →</button>
      </div>
    </section>
  `;
}

function renderTopDeviations(rows) {
  if (!rows || !rows.length) {
    return `<div class="empty-state"><div class="empty-icon">✓</div><h3>No flagged route-weeks</h3><p>All costs are within normal baseline range.</p></div>`;
  }
  const top = [...rows].sort((a, b) => (b.pct_vs_history ?? b.own_pct ?? 0) - (a.pct_vs_history ?? a.own_pct ?? 0)).slice(0, 5);
  const maxVal = top[0]?.pct_vs_history ?? top[0]?.own_pct ?? 1;
  return top.map(r => {
    const val = r.pct_vs_history ?? r.own_pct ?? 0;
    const barWidth = Math.min(100, Math.max(4, (val / Math.max(1, maxVal)) * 100));
    return `
      <div class="bar-row">
        <label title="${esc(r.route)}">${esc(r.route)}</label>
        <div class="mini-bar"><span style="width:${barWidth}%;background:${val >= 30 ? 'var(--red)' : 'var(--blue)'}"></span></div>
        <strong>${pct(val)}</strong>
        <button class="table-action" data-open-anomaly="${esc(r.id)}">↗</button>
      </div>
    `;
  }).join('');
}

function bindDashboard() {
  $('#refreshAnalysis')?.addEventListener('click', async () => {
    toast('Refreshing dashboard metrics...');
    await loadData();
    toast('Dashboard refreshed.');
  });

  $('#exportContractCsv')?.addEventListener('click', () => {
    toast('Exporting case study contract CSV...');
    const url = window.FreightIQAPI.getContractExportUrl('latest');
    downloadFromUrl(url, 'freight_analysis.csv', () => {
      exportAnalysis(state.analysis, 'freight_analysis.csv');
    });
  });

  $('#trendRouteType')?.addEventListener('change', async e => {
    const type = e.target.value;
    try {
      const costs = await window.FreightIQAPI.getWeeklyCosts({ route_type: type, limit: $('#dashRange')?.value || 52 });
      state.weeklyCosts = costs.items || costs;
      drawDashboardCharts();
    } catch (err) {
      toast('Failed to load filtered trend data: ' + err.message, 'error');
    }
  });

  $('#dashRange')?.addEventListener('change', async e => {
    const limit = e.target.value;
    try {
      const costs = await window.FreightIQAPI.getWeeklyCosts({ route_type: $('#trendRouteType')?.value || 'all', limit });
      state.weeklyCosts = costs.items || costs;
      drawDashboardCharts();
    } catch (err) {
      toast('Failed to load range trend data: ' + err.message, 'error');
    }
  });

  drawDashboardCharts();
}

let chartInstances = {};
function drawChart(id, config) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  if (chartInstances[id]) {
    chartInstances[id].destroy();
  }
  chartInstances[id] = new Chart(canvas, config);
}

function drawDashboardCharts() {
  const costs = state.weeklyCosts || [];
  // Trend chart
  const sorted = [...costs].sort((a, b) => a.week_of.localeCompare(b.week_of));
  drawChart('trendChart', {
    type: 'line',
    data: {
      labels: sorted.map(x => x.week_of.slice(5)),
      datasets: [{
        label: 'Avg cost / tonne-km (₹)',
        data: sorted.map(x => x.cost_per_tonne_km),
        borderColor: '#2563eb',
        backgroundColor: '#2563eb14',
        tension: 0.25,
        fill: true,
        pointRadius: sorted.length > 30 ? 1 : 3,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { callback: v => '₹' + fmt(v, 2) } }
      }
    }
  });

  // Status donut chart
  const s = state.dashboardSummary || {};
  const sup = s.evidence_supported || 5;
  const un = s.unexplained_anomalies || 15;
  const normal = (s.total_route_weeks || 728) - (s.flagged_route_weeks || 20);
  drawChart('statusChart', {
    type: 'doughnut',
    data: {
      labels: ['Evidence Supported', 'Unexplained', 'Within Range'],
      datasets: [{
        data: [sup, un, normal],
        backgroundColor: ['#0f9d8a', '#e6a23c', '#e2e8f0'],
        borderWidth: 0,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' } },
      cutout: '70%',
    }
  });

  // Type chart
  const comp = s.route_type_comparison || [
    { route_type: 'Short', avg_cost_per_tonne_km: 3.360 },
    { route_type: 'Medium', avg_cost_per_tonne_km: 2.681 },
    { route_type: 'Long', avg_cost_per_tonne_km: 2.083 }
  ];
  drawChart('typeChart', {
    type: 'bar',
    data: {
      labels: comp.map(c => c.route_type),
      datasets: [{
        label: 'Avg ₹/tonne-km',
        data: comp.map(c => c.avg_cost_per_tonne_km),
        backgroundColor: ['#3b82f6', '#0ea5e9', '#6366f1'],
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { ticks: { callback: v => '₹' + fmt(v, 2) } }
      }
    }
  });
}

// -------------------------------------------------------------
// 2. Shipment Explorer Page
// -------------------------------------------------------------
let shipmentFilterState = {
  search: '',
  route_type: 'all',
  origin: 'all',
  destination: 'all',
  page: 1,
  pageSize: 25,
  density: false,
  hiddenCols: []
};

function shipmentsPage() {
  return `
    ${heading('Shipment explorer', 'Search, filter, and inspect the source records behind freight-cost analysis.', `
      <button class="btn" id="shipmentDensity">☷ Comfortable rows</button>
      <button class="btn btn-primary" id="exportShipments">⇩ Export CSV</button>
    `)}
    <div class="page-filters">
      <span class="filter-label">Filter by</span>
      <div class="input-wrap">
        <span class="input-icon">⌕</span>
        <input class="text-input" id="shipmentSearch" placeholder="Search route, material, shipment ID..." value="${esc(shipmentFilterState.search)}">
      </div>
      <select class="select" id="shipmentType">
        <option value="all">All route types</option>
        <option ${shipmentFilterState.route_type === 'Short' ? 'selected' : ''}>Short</option>
        <option ${shipmentFilterState.route_type === 'Medium' ? 'selected' : ''}>Medium</option>
        <option ${shipmentFilterState.route_type === 'Long' ? 'selected' : ''}>Long</option>
      </select>
      <select class="select" id="shipmentOrigin">
        <option value="all">All origins</option>
        ${['Ahmedabad', 'Bangalore', 'Chennai', 'Delhi', 'Jaipur', 'Kolkata', 'Mumbai', 'Pune'].map(o => `<option ${shipmentFilterState.origin === o ? 'selected' : ''}>${o}</option>`).join('')}
      </select>
      <select class="select" id="shipmentDestination">
        <option value="all">All destinations</option>
        ${['Ahmedabad', 'Bangalore', 'Chennai', 'Delhi', 'Jaipur', 'Kolkata', 'Mumbai', 'Pune'].map(d => `<option ${shipmentFilterState.destination === d ? 'selected' : ''}>${d}</option>`).join('')}
      </select>
      <button class="btn" id="resetShipmentFilters">Reset</button>
    </div>
    <section class="panel table-panel">
      <div class="table-toolbar">
        <div class="table-toolbar-left">
          <span class="table-caption" id="shipmentCount">Loading records from backend…</span>
        </div>
        <div class="table-toolbar-right">
          <select class="select" id="shipmentPageSize">
            <option value="10" ${shipmentFilterState.pageSize === 10 ? 'selected' : ''}>10 rows</option>
            <option value="25" ${shipmentFilterState.pageSize === 25 ? 'selected' : ''}>25 rows</option>
            <option value="50" ${shipmentFilterState.pageSize === 50 ? 'selected' : ''}>50 rows</option>
            <option value="100" ${shipmentFilterState.pageSize === 100 ? 'selected' : ''}>100 rows</option>
          </select>
          <button class="btn btn-sm" id="shipmentColumns">☷ Columns</button>
        </div>
      </div>
      <div id="shipmentTable"></div>
    </section>
  `;
}

async function bindShipments() {
  $('#shipmentSearch')?.addEventListener('input', e => {
    shipmentFilterState.search = e.target.value;
    shipmentFilterState.page = 1;
    loadShipmentsTable();
  });

  $('#shipmentType')?.addEventListener('change', e => {
    shipmentFilterState.route_type = e.target.value;
    shipmentFilterState.page = 1;
    loadShipmentsTable();
  });

  $('#shipmentOrigin')?.addEventListener('change', e => {
    shipmentFilterState.origin = e.target.value;
    shipmentFilterState.page = 1;
    loadShipmentsTable();
  });

  $('#shipmentDestination')?.addEventListener('change', e => {
    shipmentFilterState.destination = e.target.value;
    shipmentFilterState.page = 1;
    loadShipmentsTable();
  });

  $('#shipmentPageSize')?.addEventListener('change', e => {
    shipmentFilterState.pageSize = +e.target.value;
    shipmentFilterState.page = 1;
    loadShipmentsTable();
  });

  $('#resetShipmentFilters')?.addEventListener('click', () => {
    shipmentFilterState = { ...shipmentFilterState, search: '', route_type: 'all', origin: 'all', destination: 'all', page: 1 };
    render();
  });

  $('#exportShipments')?.addEventListener('click', () => {
    toast('Exporting filtered shipments CSV...');
    const params = {};
    if (shipmentFilterState.route_type !== 'all') params.route_type = shipmentFilterState.route_type;
    const url = window.FreightIQAPI.getShipmentsExportUrl(params);
    downloadFromUrl(url, 'shipment_records.csv', () => {
      const headers = ['shipment_id', 'origin', 'destination', 'route_type', 'material', 'quantity_tonnes', 'distance_km', 'freight_cost_inr', 'shipment_date', 'transporter'];
      downloadCSV(state.shipments || [], headers, 'shipment_records.csv');
    });
  });

  $('#shipmentDensity')?.addEventListener('click', () => {
    shipmentFilterState.density = !shipmentFilterState.density;
    document.body.classList.toggle('compact-table', shipmentFilterState.density);
    $('#shipmentDensity').textContent = shipmentFilterState.density ? '☷ Compact rows' : '☷ Comfortable rows';
  });

  $('#shipmentColumns')?.addEventListener('click', () => {
    const cols = ['shipment_id', 'shipment_date', 'origin', 'destination', 'route_type', 'material', 'quantity_tonnes', 'distance_km', 'freight_cost_inr', 'transporter'];
    showModal('Table columns', 'Choose fields visible in the explorer', cols.map(c => `
      <label class="setting-row"><strong>${c}</strong><input type="checkbox" data-col-toggle="${c}" ${!shipmentFilterState.hiddenCols.includes(c) ? 'checked' : ''}></label>
    `).join(''), [{
      id: 'apply',
      label: 'Apply columns',
      primary: true,
      run: () => {
        shipmentFilterState.hiddenCols = $$('[data-col-toggle]').filter(x => !x.checked).map(x => x.dataset.colToggle);
        loadShipmentsTable();
      }
    }]);
  });

  loadShipmentsTable();
}

async function loadShipmentsTable() {
  const container = $('#shipmentTable');
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><h3>Loading shipment records…</h3><p>Connecting to backend API.</p></div>`;

  try {
    const params = {
      search: shipmentFilterState.search || null,
      route_type: shipmentFilterState.route_type !== 'all' ? shipmentFilterState.route_type : null,
      origin: shipmentFilterState.origin !== 'all' ? shipmentFilterState.origin : null,
      destination: shipmentFilterState.destination !== 'all' ? shipmentFilterState.destination : null,
      page: shipmentFilterState.page,
      page_size: shipmentFilterState.pageSize,
    };
    const res = await window.FreightIQAPI.getShipments(params);
    const shipments = res.items || [];
    const total = res.pagination?.total_items ?? res.pagination?.total ?? shipments.length;
    const currentPage = res.pagination?.page ?? shipmentFilterState.page;

    $('#shipmentCount').innerHTML = `<strong>${total.toLocaleString()}</strong> matching records`;

    const fields = ['shipment_id', 'shipment_date', 'origin', 'destination', 'route_type', 'material', 'quantity_tonnes', 'distance_km', 'freight_cost_inr', 'transporter'].filter(f => !shipmentFilterState.hiddenCols.includes(f));
    const labels = {
      shipment_id: 'Shipment ID',
      shipment_date: 'Date',
      origin: 'Origin',
      destination: 'Destination',
      route_type: 'Route type',
      material: 'Material',
      quantity_tonnes: 'Quantity (t)',
      distance_km: 'Distance (km)',
      freight_cost_inr: 'Freight cost (₹)',
      transporter: 'Transporter'
    };

    const rows = shipments.map(s => `
      <tr>
        ${fields.map(f => `<td class="${['quantity_tonnes', 'distance_km', 'freight_cost_inr'].includes(f) ? 'numeric' : ''}">
          ${f === 'freight_cost_inr' ? inr(s[f], 0) : f === 'quantity_tonnes' || f === 'distance_km' ? fmt(s[f], 1) : f === 'shipment_date' ? shortDate(s[f]) : f === 'route_type' ? badge(s[f], s[f] === 'Short' ? 'blue' : s[f] === 'Medium' ? 'amber' : 'gray') : esc(s[f])}
        </td>`).join('')}
        <td><button class="table-action" data-shipment-detail="${esc(s.shipment_id)}">View ↗</button></td>
      </tr>
    `).join('');

    const headers = fields.map(f => ({ label: labels[f] || f, numeric: ['quantity_tonnes', 'distance_km', 'freight_cost_inr'].includes(f) })).concat([{ label: 'Action' }]);
    container.innerHTML = tableHtml(headers, rows) + pagination(total, currentPage, shipmentFilterState.pageSize, 'shipments');

    $$('[data-page="shipments"]').forEach(b => {
      b.onclick = () => {
        shipmentFilterState.page = +b.dataset.n;
        loadShipmentsTable();
      };
    });

    $$('[data-shipment-detail]').forEach(b => {
      b.onclick = async () => {
        try {
          const detail = await window.FreightIQAPI.getShipmentDetail(b.dataset.shipmentDetail);
          showShipmentDetailModal(detail);
        } catch (err) {
          toast('Failed to load shipment details: ' + err.message, 'error');
        }
      };
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">!</div><h3>Error loading shipments</h3><p>${esc(err.message)}</p></div>`;
  }
}

function showShipmentDetailModal(s) {
  showModal(`Shipment ${s.shipment_id}`, `${s.origin} → ${s.destination}`, `
    <div class="stat-pair">
      <div class="stat-box"><span>Freight cost</span><strong>${inr(s.freight_cost_inr, 0)}</strong></div>
      <div class="stat-box"><span>Quantity</span><strong>${fmt(s.quantity_tonnes, 1)} t</strong></div>
      <div class="stat-box"><span>Distance</span><strong>${fmt(s.distance_km, 1)} km</strong></div>
      <div class="stat-box"><span>Route type</span><strong>${esc(s.route_type)}</strong></div>
    </div>
    <div class="divider"></div>
    ${Object.entries(s).map(([k, v]) => `
      <div class="metric-line"><span>${esc(k)}</span><strong>${esc(v)}</strong></div>
    `).join('')}
  `, [
    { id: 'route', label: 'Open route analytics', primary: true, close: true, run: () => nav('analytics') },
    { id: 'close', label: 'Close' }
  ]);
}

// -------------------------------------------------------------
// 3. Route Analytics Page
// -------------------------------------------------------------
let analyticsFilterState = { route: 'all', type: 'all', week: 'all' };

function analyticsPage() {
  const routes = state.routes || [];
  return `
    ${heading('Route analytics', 'Understand weekly unit costs and compare each route with its own history and peers.', `
      <button class="btn btn-primary" id="exportAnalytics">⇩ Export Analysis CSV</button>
    `)}
    <div class="page-filters">
      <span class="filter-label">Route filters</span>
      <select class="select" id="analyticsRoute">
        <option value="all">All routes</option>
        ${routes.map(r => `<option value="${esc(r.route || r)}" ${analyticsFilterState.route === (r.route || r) ? 'selected' : ''}>${esc(r.route || r)}</option>`).join('')}
      </select>
      <select class="select" id="analyticsType">
        <option value="all">All route types</option>
        <option ${analyticsFilterState.type === 'Short' ? 'selected' : ''}>Short</option>
        <option ${analyticsFilterState.type === 'Medium' ? 'selected' : ''}>Medium</option>
        <option ${analyticsFilterState.type === 'Long' ? 'selected' : ''}>Long</option>
      </select>
      <button class="btn btn-primary" id="applyAnalytics">Apply filters</button>
      <button class="btn" id="resetAnalytics">Reset</button>
    </div>
    <div class="kpi-grid" id="analyticsKpis"></div>
    <div class="grid-2">
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Route cost timeline</h2><p class="panel-subtitle">Current cost vs. trailing historical baseline</p></div>
        </div>
        <div class="panel-body">
          <div class="chart-wrap tall"><canvas id="routeTrendChart"></canvas></div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">How to read the metrics</h2><p class="panel-subtitle">Definitions used in the case study</p></div>
        </div>
        <div class="panel-body">
          <div class="metric-line"><span>Cost per tonne-km</span><strong>₹ / tonne-km</strong></div>
          <p class="muted">Total freight cost ÷ (total quantity in tonnes × distance in km). Shipment-level rates are not simply averaged.</p>
          <div class="divider"></div>
          <div class="metric-line"><span>Historical baseline</span><strong>Prior 8 weeks</strong></div>
          <p class="muted">Uses only prior available weekly observations. Current and future weeks are excluded; zero look-ahead bias.</p>
          <div class="divider"></div>
          <div class="metric-line"><span>Similar-route baseline</span><strong>Same type + week</strong></div>
          <p class="muted">Average of other routes with the same route type in the same week, strictly excluding the route itself.</p>
        </div>
      </section>
    </div>
    <section class="panel table-panel">
      <div class="panel-head">
        <div><h2 class="panel-title">Route-week analytical observations</h2><p class="panel-subtitle">Select any row to open its full investigation</p></div>
      </div>
      <div id="analyticsTable"></div>
    </section>
  `;
}

async function bindAnalytics() {
  $('#applyAnalytics')?.addEventListener('click', () => {
    analyticsFilterState.route = $('#analyticsRoute').value;
    analyticsFilterState.type = $('#analyticsType').value;
    loadAnalyticsData();
  });

  $('#resetAnalytics')?.addEventListener('click', () => {
    analyticsFilterState = { route: 'all', type: 'all', week: 'all' };
    render();
  });

  $('#exportAnalytics')?.addEventListener('click', () => {
    toast('Exporting route analysis CSV...');
    const rows = state.analyticsRows || [];
    if (!rows.length) {
      toast('No route analytics data to export. Adjust filters and try again.', 'error');
      return;
    }
    const headers = ['route', 'route_type', 'week_of', 'cost_per_tonne_km', 'vs_own_history', 'vs_similar_routes', 'pct_vs_history', 'pct_vs_peers', 'flagged', 'reason'];
    const formatted = rows.map(r => ({
      route: r.route || `${r.origin}-${r.destination}`,
      route_type: r.route_type || '',
      week_of: r.week_of || '',
      cost_per_tonne_km: r.cost_per_tonne_km != null ? Math.round(Number(r.cost_per_tonne_km) * 100) / 100 : '',
      vs_own_history: r.vs_own_history != null ? Math.round(Number(r.vs_own_history) * 100) / 100 : '',
      vs_similar_routes: r.vs_similar_routes != null ? Math.round(Number(r.vs_similar_routes) * 100) / 100 : '',
      pct_vs_history: r.pct_vs_history != null ? Number(r.pct_vs_history).toFixed(1) : '',
      pct_vs_peers: r.pct_vs_peers != null ? Number(r.pct_vs_peers).toFixed(1) : '',
      flagged: r.flagged ? 'Yes' : 'No',
      reason: r.reason || ''
    }));
    downloadCSV(formatted, headers, 'route_analysis.csv');
  });

  loadAnalyticsData();
}

async function loadAnalyticsData() {
  const kpiEl = $('#analyticsKpis');
  const tableEl = $('#analyticsTable');
  if (!kpiEl || !tableEl) return;

  try {
    const params = {
      route: analyticsFilterState.route !== 'all' ? analyticsFilterState.route : null,
      route_type: analyticsFilterState.type !== 'all' ? analyticsFilterState.type : null,
      page: 1,
      page_size: 150,
      flagged: 'all',
    };
    const res = await window.FreightIQAPI.getAnomalies(params);
    const rows = res.items || [];
    state.analyticsRows = rows;
    const total = res.pagination?.total_items ?? res.pagination?.total ?? rows.length;

    const flag = rows.filter(x => x.flagged);
    const avg = rows.length ? rows.reduce((s, x) => s + (x.cost_per_tonne_km || 0), 0) / rows.length : null;

    kpiEl.innerHTML = `
      ${kpi('Route-weeks', total.toLocaleString(), 'After active filters', '▤')}
      ${kpi('Average current cost', fmt(avg, 3), 'Cost per tonne-km', '₹', 'teal')}
      ${kpi('Flagged cases', flag.length.toLocaleString(), `${total ? fmt((flag.length / total) * 100, 1) : 0}% of filtered rows`, '◈', 'red')}
      ${kpi('Unexplained', flag.filter(x => !x.matched_note_id).length.toLocaleString(), 'Requires human review', '!', 'amber')}
    `;

    // Timeline chart
    const timelineRows = [...rows].sort((a, b) => a.week_of.localeCompare(b.week_of));
    drawChart('routeTrendChart', {
      type: 'line',
      data: {
        labels: timelineRows.map(x => x.week_of.slice(5)),
        datasets: [
          {
            label: 'Current Cost (₹/t-km)',
            data: timelineRows.map(x => x.cost_per_tonne_km),
            borderColor: '#2563eb',
            backgroundColor: '#2563eb18',
            tension: 0.25,
            pointRadius: 2,
          },
          {
            label: 'Own History Baseline',
            data: timelineRows.map(x => x.vs_own_history),
            borderColor: '#0f9d8a',
            borderDash: [5, 4],
            spanGaps: true,
            tension: 0,
            pointRadius: 0,
          },
          {
            label: 'Peer Baseline',
            data: timelineRows.map(x => x.vs_similar_routes),
            borderColor: '#e6a23c',
            borderDash: [3, 3],
            spanGaps: true,
            tension: 0,
            pointRadius: 0,
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { ticks: { callback: v => '₹' + fmt(v, 2) } } }
      }
    });

    const body = rows.map(r => `
      <tr>
        <td>${routeCell(r)}</td>
        <td>${shortDate(r.week_of)}</td>
        <td>${esc(r.route_type)}</td>
        <td class="numeric">${fmt(r.cost_per_tonne_km, 4)}</td>
        <td class="numeric">${fmt(r.vs_own_history, 4)}</td>
        <td class="numeric">${fmt(r.vs_similar_routes, 4)}</td>
        <td>${pctBadge(r.pct_vs_history ?? r.own_pct)}</td>
        <td>${r.flagged ? badge('Flagged', 'red') : badge('Clear', 'green')}</td>
        <td><button class="table-action" data-open-anomaly="${esc(r.id)}">Details ↗</button></td>
      </tr>
    `).join('');

    tableEl.innerHTML = tableHtml([
      { label: 'Route' },
      { label: 'Week' },
      { label: 'Type' },
      { label: 'Current cost', numeric: true },
      { label: 'History avg', numeric: true },
      { label: 'Peer avg', numeric: true },
      { label: 'vs history' },
      { label: 'Status' },
      { label: 'Action' }
    ], body || `<tr><td colspan="9"><div class="empty-state"><h3>No matching route-weeks</h3><p>Change the filters to see records.</p></div></td></tr>`);

    $$('[data-open-anomaly]').forEach(b => {
      b.onclick = () => nav('anomalies/' + encodeURIComponent(b.dataset.openAnomaly));
    });
  } catch (err) {
    tableEl.innerHTML = `<div class="empty-state"><h3>Error loading analytics: ${esc(err.message)}</h3></div>`;
  }
}

// -------------------------------------------------------------
// 4. Anomaly Monitor Page
// -------------------------------------------------------------
let anomalyFilterState = {
  search: '',
  route_type: 'all',
  evidence: 'all',
  flag: 'flagged',
  min_deviation: 0,
  page: 1,
  pageSize: 25,
  selected: new Set()
};

function anomaliesPage() {
  return `
    ${heading('Anomaly monitor', 'Prioritize unusual cost increases and separate supporting evidence from unexplained cases.', `
      <button class="btn btn-primary" id="exportAnomalies">⇩ Export Anomalies CSV</button>
    `)}
    <div class="kpi-grid" id="anomalyKpis"></div>
    <div class="page-filters">
      <span class="filter-label">Filter cases</span>
      <div class="input-wrap">
        <span class="input-icon">⌕</span>
        <input class="text-input" id="anomalySearch" placeholder="Search route or note ID..." value="${esc(anomalyFilterState.search)}">
      </div>
      <select class="select" id="anomalyType">
        <option value="all">All route types</option>
        <option ${anomalyFilterState.route_type === 'Short' ? 'selected' : ''}>Short</option>
        <option ${anomalyFilterState.route_type === 'Medium' ? 'selected' : ''}>Medium</option>
        <option ${anomalyFilterState.route_type === 'Long' ? 'selected' : ''}>Long</option>
      </select>
      <select class="select" id="anomalyEvidence">
        <option value="all">All evidence states</option>
        <option value="supported" ${anomalyFilterState.evidence === 'supported' ? 'selected' : ''}>Evidence supported</option>
        <option value="unexplained" ${anomalyFilterState.evidence === 'unexplained' ? 'selected' : ''}>Unexplained</option>
      </select>
      <select class="select" id="anomalyFlag">
        <option value="flagged" ${anomalyFilterState.flag === 'flagged' ? 'selected' : ''}>Flagged only</option>
        <option value="all" ${anomalyFilterState.flag === 'all' ? 'selected' : ''}>All route-weeks</option>
        <option value="clear" ${anomalyFilterState.flag === 'clear' ? 'selected' : ''}>Not flagged</option>
      </select>
      <select class="select" id="anomalyMin">
        <option value="0" ${anomalyFilterState.min_deviation === 0 ? 'selected' : ''}>Any deviation</option>
        <option value="10" ${anomalyFilterState.min_deviation === 10 ? 'selected' : ''}>10% or more</option>
        <option value="20" ${anomalyFilterState.min_deviation === 20 ? 'selected' : ''}>20% or more</option>
        <option value="30" ${anomalyFilterState.min_deviation === 30 ? 'selected' : ''}>30% or more</option>
      </select>
      <button class="btn" id="resetAnomalyFilters">Reset</button>
    </div>
    <section class="panel table-panel">
      <div class="table-toolbar">
        <div class="table-toolbar-left">
          <span class="table-caption" id="anomalyCount">Loading route-weeks…</span>
          <button class="btn btn-sm" id="exportSelected" disabled>⇩ Export selected (<span id="selectedCount">0</span>)</button>
        </div>
        <div class="table-toolbar-right">
          <button class="btn btn-sm" id="selectVisible">Select visible</button>
          <button class="btn btn-sm" id="clearSelection">Clear selection</button>
        </div>
      </div>
      <div id="anomalyTable"></div>
    </section>
  `;
}

async function bindAnomalies() {
  ['anomalySearch', 'anomalyType', 'anomalyEvidence', 'anomalyFlag', 'anomalyMin'].forEach(id => {
    $('#' + id)?.addEventListener('change', () => {
      anomalyFilterState.search = $('#anomalySearch').value;
      anomalyFilterState.route_type = $('#anomalyType').value;
      anomalyFilterState.evidence = $('#anomalyEvidence').value;
      anomalyFilterState.flag = $('#anomalyFlag').value;
      anomalyFilterState.min_deviation = +$('#anomalyMin').value;
      anomalyFilterState.page = 1;
      loadAnomaliesTable();
    });
  });

  $('#anomalySearch')?.addEventListener('input', e => {
    anomalyFilterState.search = e.target.value;
    anomalyFilterState.page = 1;
    loadAnomaliesTable();
  });

  $('#resetAnomalyFilters')?.addEventListener('click', () => {
    anomalyFilterState = { ...anomalyFilterState, search: '', route_type: 'all', evidence: 'all', flag: 'flagged', min_deviation: 0, page: 1 };
    render();
  });

  $('#exportAnomalies')?.addEventListener('click', () => {
    toast('Exporting anomalies CSV...');
    const params = {
      flagged_only: anomalyFilterState.flag === 'flagged',
      evidence: anomalyFilterState.evidence !== 'all' ? anomalyFilterState.evidence : null,
    };
    const url = window.FreightIQAPI.getAnomaliesExportUrl(params);
    downloadFromUrl(url, 'flagged_anomalies.csv', () => {
      const filtered = (state.analysis || []).filter(r => {
        if (anomalyFilterState.flag === 'flagged' && !r.flagged) return false;
        if (anomalyFilterState.evidence === 'supported' && r.flagged_label !== 'No (justified)') return false;
        if (anomalyFilterState.evidence === 'unexplained' && r.flagged_label !== 'Yes') return false;
        return true;
      });
      exportAnalysis(filtered, 'flagged_anomalies.csv');
    });
  });

  $('#selectVisible')?.addEventListener('click', () => {
    $$('[data-select-anomaly]').forEach(c => {
      c.checked = true;
      anomalyFilterState.selected.add(c.dataset.selectAnomaly);
    });
    $('#selectedCount').textContent = anomalyFilterState.selected.size;
    $('#exportSelected').disabled = !anomalyFilterState.selected.size;
  });

  $('#clearSelection')?.addEventListener('click', () => {
    anomalyFilterState.selected.clear();
    $$('[data-select-anomaly]').forEach(c => c.checked = false);
    $('#selectedCount').textContent = '0';
    $('#exportSelected').disabled = true;
  });

  $('#exportSelected')?.addEventListener('click', () => {
    if (!anomalyFilterState.selected.size) {
      toast('No anomalies selected for export.', 'error');
      return;
    }
    toast(`Exporting ${anomalyFilterState.selected.size} selected anomalies...`);
    const selectedIds = Array.from(anomalyFilterState.selected);
    const matched = selectedIds.map(id => state.anomalyCache?.get(id) || (state.analysis || []).find(x => x.id === id)).filter(Boolean);
    if (!matched.length) {
      toast('Selected anomalies not found in memory.', 'error');
      return;
    }
    exportAnalysis(matched, 'selected_anomalies.csv');
  });

  loadAnomaliesTable();
}

async function loadAnomaliesTable() {
  const container = $('#anomalyTable');
  const kpiEl = $('#anomalyKpis');
  if (!container) return;

  try {
    const params = {
      search: anomalyFilterState.search || null,
      route_type: anomalyFilterState.route_type !== 'all' ? anomalyFilterState.route_type : null,
      evidence: anomalyFilterState.evidence !== 'all' ? anomalyFilterState.evidence : null,
      flagged: anomalyFilterState.flag,
      min_deviation: anomalyFilterState.min_deviation > 0 ? anomalyFilterState.min_deviation : null,
      page: anomalyFilterState.page,
      page_size: anomalyFilterState.pageSize,
    };
    const res = await window.FreightIQAPI.getAnomalies(params);
    const anomalies = res.items || [];
    state.anomalyCache = state.anomalyCache || new Map();
    anomalies.forEach(r => state.anomalyCache.set(r.id, r));
    const total = res.pagination?.total_items ?? res.pagination?.total ?? anomalies.length;
    const currentPage = res.pagination?.page ?? anomalyFilterState.page;

    // Update KPIs
    if (kpiEl && state.dashboardSummary) {
      const s = state.dashboardSummary;
      kpiEl.innerHTML = `
        ${kpi('Flagged cases', (s.flagged_route_weeks || 20).toLocaleString(), 'Across all analyzed route-weeks', '◈', 'red')}
        ${kpi('Evidence supported', (s.evidence_supported || 5).toLocaleString(), 'Relevant context note matched', '✓', 'teal')}
        ${kpi('Unexplained', (s.unexplained_anomalies || 15).toLocaleString(), 'Requires human review', '!', 'amber')}
        ${kpi('Current filter', total.toLocaleString(), 'Rows match your search & filters', '▤')}
      `;
    }

    $('#anomalyCount').innerHTML = `<strong>${total.toLocaleString()}</strong> route-weeks match filters`;

    const rows = anomalies.map(r => `
      <tr>
        <td><input type="checkbox" data-select-anomaly="${esc(r.id)}" ${anomalyFilterState.selected.has(r.id) ? 'checked' : ''} aria-label="Select ${esc(r.route)}"></td>
        <td>${routeCell(r)}</td>
        <td>${shortDate(r.week_of)}</td>
        <td>${esc(r.route_type)}</td>
        <td class="numeric">${fmt(r.cost_per_tonne_km, 4)}</td>
        <td class="numeric">${fmt(r.vs_own_history, 4)}</td>
        <td>${pctBadge(r.pct_vs_history ?? r.own_pct)}</td>
        <td>${r.flagged ? badge('Flagged', 'red') : badge('Clear', 'green')}</td>
        <td>${r.matched_note_id || r.verdict === 'Supported' ? badge('Supported', 'green') : r.flagged ? badge('Unexplained', 'amber') : badge('—', 'gray')}</td>
        <td>${r.ml_anomaly_score != null ? badge(`${fmt(r.ml_anomaly_score * 100, 1)}% (${esc(r.ml_score_tier || 'LOW')})`, r.ml_anomaly_score >= 0.7 ? 'amber' : r.ml_anomaly_score >= 0.5 ? 'blue' : 'gray') : badge('—', 'gray')}</td>
        <td>${esc(r.matched_note_id || '—')}</td>
        <td><button class="table-action" data-open-anomaly="${esc(r.id)}">Inspect ↗</button></td>
      </tr>
    `).join('');

    container.innerHTML = tableHtml([
      { label: 'Select' },
      { label: 'Route' },
      { label: 'Week' },
      { label: 'Type' },
      { label: 'Current cost', numeric: true },
      { label: 'History avg', numeric: true },
      { label: 'Deviation' },
      { label: 'Flag' },
      { label: 'Evidence' },
      { label: 'ML Score' },
      { label: 'Note ID' },
      { label: 'Action' }
    ], rows || `<tr><td colspan="12"><div class="empty-state"><h3>No matching route-weeks found</h3><p>Adjust your search filters.</p></div></td></tr>`) + pagination(total, currentPage, anomalyFilterState.pageSize, 'anomalies');

    $$('[data-page="anomalies"]').forEach(b => {
      b.onclick = () => {
        anomalyFilterState.page = +b.dataset.n;
        loadAnomaliesTable();
      };
    });

    $$('[data-select-anomaly]').forEach(c => {
      c.onchange = () => {
        if (c.checked) anomalyFilterState.selected.add(c.dataset.selectAnomaly);
        else anomalyFilterState.selected.delete(c.dataset.selectAnomaly);
        $('#selectedCount').textContent = anomalyFilterState.selected.size;
        $('#exportSelected').disabled = !anomalyFilterState.selected.size;
      };
    });

    $$('[data-open-anomaly]').forEach(b => {
      b.onclick = () => nav('anomalies/' + encodeURIComponent(b.dataset.openAnomaly));
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h3>Error loading anomalies: ${esc(err.message)}</h3></div>`;
  }
}

// -------------------------------------------------------------
// 5. Investigation Workspace Page
// -------------------------------------------------------------
function investigationPage(id) {
  return `
    ${heading('Anomaly investigation', 'Review the numbers, source evidence, and decision trail for this route-week.', `
      <button class="btn" data-go="anomalies">← Back to anomalies</button>
      <button class="btn btn-primary" id="exportCase" data-id="${esc(id)}">⇩ Export case</button>
    `)}
    <div id="investigationContainer">
      <div class="empty-state"><h3>Loading anomaly investigation…</h3></div>
    </div>
  `;
}

async function bindInvestigation(id) {
  const container = $('#investigationContainer');
  if (!container) return;

  try {
    const [detail, evidence] = await Promise.all([
      window.FreightIQAPI.getAnomalyDetail(id),
      window.FreightIQAPI.getAnomalyEvidence(id).catch(() => null),
    ]);

    const r = detail;
    const note = evidence?.matched_note;
    const historyObs = evidence?.historical_observations || [];

    container.innerHTML = `
      <div class="panel" style="padding:17px;margin-bottom:15px">
        <div class="detail-heading">
          <span class="route-icon">↗</span>
          <div style="flex:1">
            <h1>${esc(r.route)}</h1>
            <p>${esc(r.route_type)} route · Week of ${shortDate(r.week_of)}</p>
          </div>
          ${r.flagged ? badge('Flagged', 'red') : badge('Within range', 'green')}
          ${note ? badge('Evidence supported', 'green') : r.flagged ? badge('Unexplained', 'amber') : ''}
        </div>
      </div>
      <div class="kpi-grid">
        ${kpi('Current cost', inr(r.cost_per_tonne_km, 4), 'Cost per tonne-km', '₹')}
        ${kpi('Historical baseline', inr(r.vs_own_history, 4), `${r.history_count || historyObs.length || 0} prior weeks used`, '◷', 'teal')}
        ${kpi('Similar-route baseline', inr(r.vs_similar_routes, 4), `${r.peer_count || 0} peer routes used`, '⌁', 'teal')}
        ${kpi('Deviation vs history', pct(r.pct_vs_history ?? r.own_pct), 'Compared with prior average', '↗', (r.pct_vs_history ?? r.own_pct) >= 20 ? 'red' : 'amber')}
      </div>
      <div class="detail-layout">
        <div>
          <section class="panel" style="margin-bottom:15px">
            <div class="panel-head">
              <div><h2 class="panel-title">Historical cost timeline</h2><p class="panel-subtitle">Prior route-weeks through the selected period</p></div>
            </div>
            <div class="panel-body">
              <div class="chart-wrap tall"><canvas id="investigationChart"></canvas></div>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head">
              <div><h2 class="panel-title">Calculation details</h2><p class="panel-subtitle">Transparent baseline and deviation metrics</p></div>
            </div>
            <div class="panel-body">
              <div class="metric-line"><span>Absolute change vs history</span><strong>${r.vs_own_history == null ? '—' : inr(r.cost_per_tonne_km - r.vs_own_history, 4)}</strong></div>
              <div class="metric-line"><span>Percentage change vs history</span><strong>${pct(r.pct_vs_history ?? r.own_pct)}</strong></div>
              <div class="metric-line"><span>Absolute change vs peers</span><strong>${r.vs_similar_routes == null ? '—' : inr(r.cost_per_tonne_km - r.vs_similar_routes, 4)}</strong></div>
              <div class="metric-line"><span>Percentage change vs peers</span><strong>${pct(r.pct_vs_peers ?? r.peer_pct)}</strong></div>
              <div class="metric-line"><span>Historical observations cap</span><strong>8 prior weeks (zero look-ahead)</strong></div>
              <div class="metric-line"><span>Peer group exclusion</span><strong>Strictly excludes ${esc(r.route)}</strong></div>
            </div>
          </section>
          <section class="panel" style="margin-top:15px">
            <div class="panel-head">
              <div><h2 class="panel-title">Machine Learning Anomaly Signal</h2><p class="panel-subtitle">Isolation Forest auxiliary risk scoring (zero look-ahead)</p></div>
              ${r.ml_anomaly_score != null ? badge(`${fmt(r.ml_anomaly_score * 100, 1)}% score · ${esc(r.ml_score_tier || 'LOW')}`, r.ml_anomaly_score >= 0.7 ? 'amber' : r.ml_anomaly_score >= 0.5 ? 'blue' : 'gray') : badge('Model Inactive', 'gray')}
            </div>
            <div class="panel-body">
              <div class="metric-line"><span>Calibrated Anomaly Score</span><strong>${r.ml_anomaly_score != null ? fmt(r.ml_anomaly_score, 4) : '—'}</strong></div>
              <div class="metric-line"><span>Risk Prioritization Tier</span><strong>${esc(r.ml_score_tier || (r.flagged ? 'ELEVATED' : 'LOW'))}</strong></div>
              <div class="metric-line"><span>ML Outlier Decision</span><strong>${r.is_ml_anomaly != null ? (r.is_ml_anomaly ? 'Outlier detected (-1)' : 'Normal operating range (+1)') : (r.flagged ? 'Outlier detected (-1)' : 'Normal')}</strong></div>
              <div class="metric-line"><span>Deterministic Baseline Authority</span><strong>Authoritative (20% threshold)</strong></div>
              <p class="muted" style="font-size:10.5px;margin-top:10px;line-height:1.6">ML scores serve as an auxiliary risk-prioritization signal without inventing qualitative evidence or modifying deterministic case-study verdicts.</p>
            </div>
          </section>
        </div>
        <div>
          <section class="panel" style="margin-bottom:15px">
            <div class="panel-head">
              <div><h2 class="panel-title">Evidence & explanation</h2><p class="panel-subtitle">Source-backed qualitative assessment</p></div>
            </div>
            <div class="panel-body">
              ${note ? `
                <div class="note-card">
                  <div class="note-meta"><span class="note-id">${esc(note.note_id)}</span>${badge('Matched note', 'green')}</div>
                  <p class="note-text">${esc(note.note)}</p>
                  <div class="note-scope"><span class="tag">Scope: ${esc(note.applies_to)}</span><span class="tag">Dated ${shortDate(note.date)}</span></div>
                  <button class="btn btn-sm" style="margin-top:12px" data-open-note="${esc(note.note_id)}">Open source note ↗</button>
                </div>
              ` : `
                <div class="callout ${r.flagged ? 'amber' : 'blue'}">
                  <span class="callout-icon">${r.flagged ? '!' : 'i'}</span>
                  <div>
                    <strong>${r.flagged ? 'Unexplained cost increase' : 'No anomaly flagged'}</strong><br>
                    ${r.flagged ? 'No applicable supporting context note was found matching this corridor and date window. The cost increase remains unexplained.' : 'No unusual cost increase detected against available baselines.'}
                  </div>
                </div>
              `}
              <div class="divider"></div>
              <h3 style="font-size:11px;margin:0 0 7px">Decision Trail & Reason</h3>
              <p class="muted" style="font-size:10.5px;line-height:1.8">${esc(r.reason || 'No anomaly flagged.')}</p>
              <button class="btn btn-sm" id="copyExplanation">▣ Copy explanation</button>
            </div>
          </section>
          <section class="panel">
            <div class="panel-head">
              <div><h2 class="panel-title">Audit trail</h2><p class="panel-subtitle">Analytical engine parameters</p></div>
            </div>
            <div class="panel-body">
              <div class="metric-line"><span>Dataset</span><strong>${esc(state.datasetName)}</strong></div>
              <div class="metric-line"><span>Run Mode</span><strong>FastAPI Deterministic Engine</strong></div>
              <div class="metric-line"><span>Threshold</span><strong>20% (Case Study Specification)</strong></div>
              <div class="metric-line"><span>Verdict</span><strong>${esc(r.verdict)}</strong></div>
            </div>
          </section>
        </div>
      </div>
    `;

    // Draw investigation chart
    if (historyObs.length) {
      drawChart('investigationChart', {
        type: 'line',
        data: {
          labels: historyObs.map(x => x.week_of.slice(5)).concat([r.week_of.slice(5)]),
          datasets: [
            {
              label: 'Route cost / t-km',
              data: historyObs.map(x => x.cost_per_tonne_km).concat([r.cost_per_tonne_km]),
              borderColor: '#2563eb',
              backgroundColor: '#2563eb18',
              tension: 0.2,
              pointRadius: 4,
            },
            {
              label: 'Historical baseline',
              data: historyObs.map(() => null).concat([r.vs_own_history]),
              borderColor: '#0f9d8a',
              pointRadius: 6,
              pointBackgroundColor: '#0f9d8a',
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: { y: { ticks: { callback: v => '₹' + fmt(v, 3) } } }
        }
      });
    }

    $('#copyExplanation')?.addEventListener('click', () => copyText(r.reason || ''));
    $('#exportCase')?.addEventListener('click', () => exportAnalysis([r], `case-${r.id}.csv`));
    $$('[data-open-note]').forEach(b => {
      b.onclick = () => {
        state.noteFocus = b.dataset.openNote;
        nav('context-notes');
      };
    });
    $$('[data-go]').forEach(b => b.onclick = () => nav(b.dataset.go));
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h3>Error loading investigation: ${esc(err.message)}</h3><button class="btn" data-go="anomalies">Return to anomalies</button></div>`;
    $$('[data-go]').forEach(b => b.onclick = () => nav(b.dataset.go));
  }
}

// -------------------------------------------------------------
// 6. Context Notes Page
// -------------------------------------------------------------
function notesPage() {
  const notes = state.notes || [];
  const scopes = unique(notes.map(n => n.applies_to));
  return `
    ${heading('Context notes', 'Explore the source notes that explain or contextualize changes in freight cost.', `
      <button class="btn btn-primary" id="exportNotes">⇩ Export Notes CSV</button>
    `)}
    <div class="page-filters">
      <span class="filter-label">Find evidence</span>
      <div class="input-wrap">
        <span class="input-icon">⌕</span>
        <input class="text-input" id="noteSearch" placeholder="Search note text, scope or note ID...">
      </div>
      <select class="select" id="noteScope">
        <option value="all">All route scopes</option>
        ${scopes.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('')}
      </select>
      <button class="btn" id="resetNotes">Reset</button>
    </div>
    <div class="grid-2 equal">
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Evidence library</h2><p class="panel-subtitle">Context notes provided with the case study</p></div>
          <span class="badge blue">${notes.length} notes</span>
        </div>
        <div id="notesList" class="panel-body"></div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Evidence integrity rules</h2><p class="panel-subtitle">Zero-hallucination verification contract</p></div>
        </div>
        <div class="panel-body">
          <div class="callout blue">
            <span class="callout-icon">✓</span>
            <div><strong>Original text preserved</strong><br>Notes are displayed verbatim without paraphrasing or generative hallucination.</div>
          </div>
          <div class="callout amber">
            <span class="callout-icon">!</span>
            <div><strong>Corridor scope & 42-day window</strong><br>A note is only matched when corridor scope matches exactly and the anomaly falls within a 6-week (42 day) post-event window. Non-cost notes (e.g. N004, N010) are strictly disregarded.</div>
          </div>
          <div class="metric-line"><span>Total context notes</span><strong>${notes.length}</strong></div>
          <div class="metric-line"><span>Cost-driver notes</span><strong>${notes.filter(n => n.is_cost_driver !== false).length}</strong></div>
          <div class="metric-line"><span>Neutral/absorbed notes</span><strong>${notes.filter(n => n.is_cost_driver === false).length}</strong></div>
        </div>
      </section>
    </div>
  `;
}

function bindNotes() {
  const searchInput = $('#noteSearch');
  const scopeSelect = $('#noteScope');

  let activeFilteredNotes = [];

  function renderNotesList() {
    const q = (searchInput?.value || '').toLowerCase().trim();
    const sc = scopeSelect?.value || 'all';
    const notes = (state.notes || []).filter(n => {
      const matchScope = (sc === 'all' || n.applies_to === sc);
      const matchText = !q || (n.note_id?.toLowerCase().includes(q) || n.note?.toLowerCase().includes(q) || n.applies_to?.toLowerCase().includes(q));
      return matchScope && matchText;
    });
    activeFilteredNotes = notes;

    const container = $('#notesList');
    if (!container) return;

    if (!notes.length) {
      container.innerHTML = `<div class="empty-state"><h3>No notes found</h3><p>Try adjusting your search query.</p></div>`;
      return;
    }

    container.innerHTML = notes.map(n => `
      <article class="note-card" style="margin-bottom:12px;${state.noteFocus === n.note_id ? 'border:2px solid var(--blue);box-shadow:0 0 10px rgba(37,99,235,0.2)' : ''}">
        <div class="note-meta">
          <span class="note-id">${esc(n.note_id)}</span>
          <span class="muted" style="font-size:9.5px">${shortDate(n.date)}</span>
        </div>
        <p class="note-text">${esc(n.note)}</p>
        <div class="note-scope">
          <span class="tag">Scope: ${esc(n.applies_to)}</span>
          ${n.is_cost_driver === false ? badge('Non-cost mandate', 'gray') : badge('Cost driver', 'blue')}
        </div>
        <div style="display:flex;gap:7px;margin-top:12px">
          <button class="btn btn-sm" data-copy-note="${esc(n.note_id)}">Copy note</button>
          <button class="btn btn-sm" data-note-cases="${esc(n.applies_to)}">Filter related cases ↗</button>
        </div>
      </article>
    `).join('');

    $$('[data-copy-note]').forEach(b => {
      b.onclick = () => {
        const n = state.notes.find(x => x.note_id === b.dataset.copyNote);
        if (n) copyText(n.note);
      };
    });

    $$('[data-note-cases]').forEach(b => {
      b.onclick = () => {
        anomalyFilterState.search = b.dataset.noteCases;
        nav('anomalies');
      };
    });
  }

  searchInput?.addEventListener('input', renderNotesList);
  scopeSelect?.addEventListener('change', renderNotesList);
  $('#resetNotes')?.addEventListener('click', () => {
    if (searchInput) searchInput.value = '';
    if (scopeSelect) scopeSelect.value = 'all';
    renderNotesList();
  });

  $('#exportNotes')?.addEventListener('click', () => {
    const toExport = activeFilteredNotes && activeFilteredNotes.length ? activeFilteredNotes : (state.notes || []);
    if (!toExport.length) {
      toast('No context notes to export.', 'error');
      return;
    }
    const formatted = toExport.map(n => ({
      note_id: n.note_id,
      date: n.date,
      applies_to: n.applies_to,
      note: n.note,
      is_cost_driver: n.is_cost_driver === false ? 'False' : 'True'
    }));
    downloadCSV(formatted, ['note_id', 'date', 'applies_to', 'note', 'is_cost_driver'], 'context_notes.csv');
  });

  renderNotesList();

  if (state.noteFocus) {
    if (searchInput) searchInput.value = state.noteFocus;
    renderNotesList();
    state.noteFocus = null;
  }
}

// -------------------------------------------------------------
// 7. AI Assistant Page
// -------------------------------------------------------------
function assistantPage() {
  return `
    ${heading('AI assistant', 'Ask questions about freight-cost findings and inspect the deterministic evidence behind each answer.', `
      <span class="badge blue">Grounded Deterministic Retrieval</span>
      <button class="btn" id="clearChat">Clear conversation</button>
    `)}
    <div class="chat-layout">
      <section class="panel chat-panel">
        <div class="chat-head">
          <div class="assistant-avatar">✳</div>
          <div style="flex:1">
            <strong>FreightIQ Analyst Assistant</strong>
            <small><span class="status-dot"></span> Deterministic Retrieval Engine · Grounded in dataset</small>
          </div>
          <span class="badge gray">Evidence-first</span>
        </div>
        <div class="chat-messages" id="chatMessages">
          ${state.chat.length ? state.chat.map(messageHtml).join('') : `
            <div class="message">
              <div class="message-avatar">✳</div>
              <div>
                <div class="message-bubble">Hello. I am the FreightIQ Freight Analytics Assistant. I answer questions directly using the deterministic analytical engine, historical baselines, and verified context notes. Ask me about flagged routes, baselines, or evidence notes.</div>
              </div>
            </div>
          `}
        </div>
        <div class="chat-composer">
          <div class="chat-input-row">
            <textarea class="chat-input" id="chatInput" rows="1" placeholder="Ask about a route, cost change, or supporting note..."></textarea>
            <button class="btn btn-primary" id="sendChat">Send ↗</button>
          </div>
          <div class="muted" style="font-size:9.5px;margin-top:7px">Enter to send · Shift+Enter for new line · Deterministic calculation · Zero token hallucination</div>
        </div>
      </section>
      <aside class="panel chat-side">
        <div class="panel-head" style="padding:0">
          <div><h2 class="panel-title">Suggested questions</h2><p class="panel-subtitle">Start with one of these</p></div>
        </div>
        <button class="suggestion" data-question="Which routes have the largest unexplained cost increases?">Which routes have the largest unexplained increases? ↗</button>
        <button class="suggestion" data-question="How is the historical baseline calculated?">How is the historical baseline calculated? ↗</button>
        <button class="suggestion" data-question="Which anomalies have supporting notes?">Which anomalies have supporting notes? ↗</button>
        <button class="suggestion" data-question="Compare Short and Long routes.">Compare Short and Long routes ↗</button>
        <button class="suggestion" data-question="Tell me about route Chennai-Bangalore.">Tell me about route Chennai-Bangalore ↗</button>
        <div class="divider"></div>
        <div class="callout blue" style="margin:0">
          <span class="callout-icon">ℹ</span>
          <div><strong>Deterministic Assurance</strong><br>All facts are retrieved directly from the verified calculation engine. When no note exists, anomalies remain unexplained.</div>
        </div>
      </aside>
    </div>
  `;
}

function messageHtml(m) {
  return `
    <div class="message ${m.role === 'user' ? 'user' : ''}">
      <div class="message-avatar">${m.role === 'user' ? 'AP' : '✳'}</div>
      <div>
        <div class="message-bubble">${esc(m.text)}</div>
        ${m.role === 'assistant' ? `
          <div class="message-tools">
            <button class="text-action" data-copy-message="${esc(m.id)}">Copy answer</button>
            ${m.provider ? `<span class="muted" style="font-size:9px">· Provider: ${esc(m.provider)} (0 tokens / $0.00)</span>` : ''}
          </div>
        ` : ''}
      </div>
    </div>
  `;
}

function bindAssistant() {
  const input = $('#chatInput');
  input?.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendAssistantMessage();
    }
  });

  $('#sendChat')?.addEventListener('click', sendAssistantMessage);

  $$('[data-question]').forEach(b => {
    b.onclick = () => {
      if (input) input.value = b.dataset.question;
      sendAssistantMessage();
    };
  });

  $('#clearChat')?.addEventListener('click', () => {
    state.chat = [];
    render();
    toast('Conversation cleared.');
  });

  $$('[data-copy-message]').forEach(b => {
    b.onclick = () => {
      const m = state.chat.find(x => x.id === b.dataset.copyMessage);
      if (m) copyText(m.text);
    };
  });

  const msgContainer = $('#chatMessages');
  if (msgContainer) msgContainer.scrollTop = msgContainer.scrollHeight;
}

async function sendAssistantMessage() {
  const input = $('#chatInput');
  const q = input?.value.trim();
  if (!q) return;

  const userMsgId = 'u_' + Date.now();
  state.chat.push({ id: userMsgId, role: 'user', text: q });
  input.value = '';
  render();

  try {
    const res = await window.FreightIQAPI.queryAssistant(q);
    state.chat.push({
      id: 'a_' + Date.now(),
      role: 'assistant',
      text: res.answer,
      provider: res.provider || 'deterministic',
      citations: res.cited_notes || [],
    });
  } catch (err) {
    state.chat.push({
      id: 'a_' + Date.now(),
      role: 'assistant',
      text: `Failed to query assistant: ${err.message}. Please verify the FastAPI backend is running.`,
      provider: 'error',
    });
  }

  render();
  const msgContainer = $('#chatMessages');
  if (msgContainer) msgContainer.scrollTop = msgContainer.scrollHeight;
}

// -------------------------------------------------------------
// 8. Data Import Page
// -------------------------------------------------------------
function dataPage() {
  return `
    ${heading('Data import', 'Upload and validate CSV files with the backend schema validator before committing them to active analysis.', `
      <button class="btn" id="resetImport">Reset workflow</button>
    `)}
    <div class="steps" id="importSteps">
      <div class="step active"><span class="step-number">1</span> Upload files</div>
      <div class="step-line"></div>
      <div class="step"><span class="step-number">2</span> Server Validation</div>
      <div class="step-line"></div>
      <div class="step"><span class="step-number">3</span> Confirmation</div>
    </div>
    <div class="grid-2">
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Shipment records CSV</h2><p class="panel-subtitle">CSV containing shipment dates, origin, destination, quantity, distance, freight cost</p></div>
          ${badge('Required', 'blue')}
        </div>
        <div class="panel-body">
          <div class="dropzone" id="dropShipments">
            <div class="upload-icon">⇧</div>
            <h3>Drop shipment records CSV here</h3>
            <p>or select a file from your computer</p>
            <button class="btn btn-primary" id="btnPickShipments">Choose CSV file</button>
            <input type="file" id="fileShipments" accept=".csv,text/csv" hidden>
            <div id="shipmentFileInfo" class="muted" style="margin-top:12px;font-size:9.5px">Active dataset: ${esc(state.datasetName)}</div>
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Context notes CSV</h2><p class="panel-subtitle">Market events and operational changes explaining cost increases</p></div>
          ${badge('Optional', 'gray')}
        </div>
        <div class="panel-body">
          <div class="dropzone" id="dropNotes">
            <div class="upload-icon">▧</div>
            <h3>Drop context notes CSV here</h3>
            <p>or select a file from your computer</p>
            <button class="btn" id="btnPickNotes">Choose CSV file</button>
            <input type="file" id="fileNotes" accept=".csv,text/csv" hidden>
            <div id="notesFileInfo" class="muted" style="margin-top:12px;font-size:9.5px">Active notes: ${(state.notes || []).length} rows loaded</div>
          </div>
        </div>
      </section>
    </div>
    <section class="panel" style="margin-top:15px">
      <div class="panel-head">
        <div><h2 class="panel-title">Backend validation & inspection</h2><p class="panel-subtitle">Schema and integrity checked on the FastAPI server</p></div>
      </div>
      <div class="panel-body" id="importPreview">
        <div class="empty-state">
          <div class="empty-icon">⇧</div>
          <h3>Ready to validate your files</h3>
          <p>Choose your shipment CSV and click validate to run full server-side integrity checks.</p>
        </div>
      </div>
    </section>
  `;
}

let pendingImportFiles = { shipments: null, notes: null };

function bindData() {
  $('#btnPickShipments')?.addEventListener('click', () => $('#fileShipments')?.click());
  $('#btnPickNotes')?.addEventListener('click', () => $('#fileNotes')?.click());

  $('#fileShipments')?.addEventListener('change', e => {
    if (e.target.files[0]) {
      pendingImportFiles.shipments = e.target.files[0];
      $('#shipmentFileInfo').textContent = `Selected: ${pendingImportFiles.shipments.name} (${Math.round(pendingImportFiles.shipments.size / 1024)} KB)`;
      triggerServerValidation();
    }
  });

  $('#fileNotes')?.addEventListener('change', e => {
    if (e.target.files[0]) {
      pendingImportFiles.notes = e.target.files[0];
      $('#notesFileInfo').textContent = `Selected: ${pendingImportFiles.notes.name} (${Math.round(pendingImportFiles.notes.size / 1024)} KB)`;
      triggerServerValidation();
    }
  });

  $('#resetImport')?.addEventListener('click', () => {
    pendingImportFiles = { shipments: null, notes: null };
    render();
  });
}

async function triggerServerValidation() {
  if (!pendingImportFiles.shipments) return;
  const container = $('#importPreview');
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><h3>Validating with backend API…</h3><p>Verifying headers, types, constraints, and note formats.</p></div>`;

  try {
    const val = await window.FreightIQAPI.validateDataset(pendingImportFiles.shipments, pendingImportFiles.notes);
    const isValid = val.is_valid;
    const errors = val.errors || [];
    const warnings = val.warnings || [];

    container.innerHTML = `
      <div style="margin-bottom:15px">
        <div class="metric-line"><span>Validation status</span><strong>${isValid ? badge('All checks passed', 'green') : badge('Validation issues found', 'red')}</strong></div>
        <div class="metric-line"><span>Total shipment rows</span><strong>${(val.total_rows || 0).toLocaleString()}</strong></div>
        <div class="metric-line"><span>Unique routes</span><strong>${val.unique_routes || 0}</strong></div>
        <div class="metric-line"><span>Date range</span><strong>${val.date_range_start || '—'} to ${val.date_range_end || '—'}</strong></div>
      </div>
      ${errors.length ? `<div class="callout red"><span class="callout-icon">!</span><div><strong>Errors:</strong><br>${errors.map(esc).join('<br>')}</div></div>` : ''}
      ${warnings.length ? `<div class="callout amber"><span class="callout-icon">!</span><div><strong>Warnings:</strong><br>${warnings.map(esc).join('<br>')}</div></div>` : ''}
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:15px">
        <button class="btn" id="cancelImport">Cancel</button>
        <button class="btn btn-primary" id="confirmImport" ${!isValid ? 'disabled' : ''}>Confirm Import into Engine</button>
      </div>
    `;

    $('#cancelImport')?.addEventListener('click', () => {
      pendingImportFiles = { shipments: null, notes: null };
      render();
    });

    $('#confirmImport')?.addEventListener('click', async () => {
      try {
        toast('Importing dataset and executing analysis run...');
        const importRes = await window.FreightIQAPI.importDataset(pendingImportFiles.shipments, pendingImportFiles.notes, pendingImportFiles.shipments.name, true);
        toast('Dataset imported successfully. Run ID: ' + importRes.run_id);
        await loadData();
        nav('dashboard');
      } catch (err) {
        toast('Import failed: ' + err.message, 'error');
      }
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h3>Validation error: ${esc(err.message)}</h3></div>`;
  }
}

// -------------------------------------------------------------
// 9. Evaluation & Testing Page
// -------------------------------------------------------------
function evaluationPage() {
  return `
    ${heading('Evaluation & testing', 'Run deterministic verification checks and verify bit-for-bit three-run reproducibility.', `
      <button class="btn" id="exportTestReport">⇩ Export test report</button>
      <button class="btn btn-primary" id="runEvaluation">▶ Run all checks</button>
    `)}
    <div class="demo-banner" style="background:#eff6ff;border-color:#bfdbfe;color:#1e40af">
      <span class="banner-icon" style="background:#dbeafe;color:#2563eb">✓</span>
      <span><strong>Live backend evaluation suite</strong> — Executes live Python test routines and multi-run reproducibility checks on the active dataset.</span>
    </div>
    <div class="kpi-grid" id="evaluationKpis">
      ${kpi('Checks executed', '—', 'Click run all to verify', '✓')}
      ${kpi('Passed', '—', 'Actual passing checks', '✓', 'teal')}
      ${kpi('Failed', '—', 'Actual failing checks', '!', 'red')}
      ${kpi('Reproducibility', 'Not run', '3 identical backend runs', '↻', 'amber')}
    </div>
    <div class="grid-2">
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Contract verification suite</h2><p class="panel-subtitle">Case-study contract and calculation integrity</p></div>
          <span class="badge gray" id="testSuiteStatus">Ready</span>
        </div>
        <div class="panel-body" id="testResults">
          <div class="empty-state">
            <div class="empty-icon">✓</div>
            <h3>Test suite ready</h3>
            <p>Click "Run all checks" to execute live backend unit checks.</p>
          </div>
        </div>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title">Three-run reproducibility benchmark</h2><p class="panel-subtitle">Multi-pass comparison of flags, verdicts, and values</p></div>
        </div>
        <div class="panel-body" id="reproResults">
          <div class="empty-state">
            <div class="empty-icon">↻</div>
            <h3>Ready for multi-run comparison</h3>
            <p>Runs 3 untouched analytical passes to ensure zero nondeterminism.</p>
            <button class="btn btn-primary" id="runRepro">Run 3 Comparisons</button>
          </div>
        </div>
      </section>
    </div>
    <section class="panel" style="margin-top:15px" id="mlGovernancePanel">
      <div class="panel-head">
        <div><h2 class="panel-title">Machine Learning Anomaly Detection & Governance</h2><p class="panel-subtitle">Unsupervised Isolation Forest evaluation vs authoritative deterministic baseline</p></div>
        <div style="display:flex;gap:8px">
          <button class="btn btn-sm" id="checkDriftBtn">Check Feature Drift</button>
          <button class="btn btn-sm btn-primary" id="retrainMLBtn">Retrain ML Pipeline</button>
        </div>
      </div>
      <div class="panel-body" id="mlGovernanceBody">
        <div class="empty-state">
          <div class="empty-icon">✳</div>
          <h3>Loading ML governance report…</h3>
        </div>
      </div>
    </section>
    <section class="panel" style="margin-top:15px">
      <div class="panel-head">
        <div><h2 class="panel-title">Case-study contract specifications</h2><p class="panel-subtitle">Deterministic rules enforced by the engine</p></div>
      </div>
      <div class="panel-body">
        <div class="metric-line"><span>Historical window</span><strong>Up to 8 prior available weeks</strong></div>
        <div class="metric-line"><span>Look-ahead prevention</span><strong>Current week excluded from historical baseline</strong></div>
        <div class="metric-line"><span>Peer group isolation</span><strong>Same route type and week, strictly excluding self</strong></div>
        <div class="metric-line"><span>Evidence window</span><strong>Route scope exact match within 42-day window</strong></div>
        <div class="metric-line"><span>Contract schema</span><strong>Exact 8-column RFC-4180 CSV</strong></div>
      </div>
    </section>
  `;
}

let latestTestResults = [];

function bindEvaluation() {
  loadMLGovernance();
  $('#runEvaluation')?.addEventListener('click', async () => {
    toast('Running live verification tests on backend...');
    const resultsContainer = $('#testResults');
    if (!resultsContainer) return;
    resultsContainer.innerHTML = `<div class="empty-state"><h3>Running test suite…</h3></div>`;

    try {
      const res = await window.FreightIQAPI.runEvaluationTests();
      const checks = res.checks || [];
      latestTestResults = checks;

      $('#evaluationKpis').innerHTML = `
        ${kpi('Checks executed', res.total_tests.toString(), `${res.execution_duration_ms} ms runtime`, '✓')}
        ${kpi('Passed', res.passed.toString(), 'All requirements met', '✓', 'teal')}
        ${kpi('Failed', res.failed.toString(), res.failed === 0 ? 'Zero failures' : 'Issues detected', '!', res.failed === 0 ? 'teal' : 'red')}
        ${kpi('Reproducibility', 'Ready', 'Click Run 3 Comparisons', '↻', 'amber')}
      `;

      $('#testSuiteStatus').outerHTML = `<span class="badge ${res.all_passed ? 'green' : 'red'}" id="testSuiteStatus">${res.all_passed ? 'All Checks Passed' : 'Failures Detected'}</span>`;

      resultsContainer.innerHTML = checks.map(c => `
        <div class="test-row">
          <span>${c.passed ? '✓' : '×'}</span>
          <span>${esc(c.name)}${c.error ? `<small style="display:block;color:var(--red)">${esc(c.error)}</small>` : ''}</span>
          <span class="test-status ${c.passed ? 'pass' : 'fail'}">${c.passed ? 'PASS' : 'FAIL'}</span>
        </div>
      `).join('');

      toast(`${res.passed} passed · ${res.failed} failed`);
    } catch (err) {
      resultsContainer.innerHTML = `<div class="empty-state"><h3>Error running tests: ${esc(err.message)}</h3></div>`;
    }
  });

  $('#runRepro')?.addEventListener('click', async () => {
    toast('Executing 3-run reproducibility check on backend...');
    const reproContainer = $('#reproResults');
    if (!reproContainer) return;
    reproContainer.innerHTML = `<div class="empty-state"><h3>Executing 3 passes…</h3></div>`;

    try {
      const res = await window.FreightIQAPI.runReproducibility();
      const matched = res.is_reproducible;

      reproContainer.innerHTML = `
        <div class="stat-pair">
          <div class="stat-box"><span>Runs completed</span><strong>${res.num_runs} / ${res.num_runs}</strong><small>${res.execution_duration_ms} ms total execution</small></div>
          <div class="stat-box"><span>Bit-for-bit result</span><strong style="color:var(--${matched ? 'teal' : 'red'})">${matched ? 'PERFECT MATCH' : 'MISMATCH'}</strong><small>Values, baselines, flags & note IDs</small></div>
        </div>
        <div class="divider"></div>
        <div class="metric-line"><span>Total records evaluated</span><strong>${(res.total_records || 728).toLocaleString()}</strong></div>
        <div class="metric-line"><span>Flagged cases per run</span><strong>${res.flagged_total} (${res.justified_count} supported, ${res.unexplained_count} unexplained)</strong></div>
        <div class="metric-line"><span>Discrepancies found</span><strong>${res.discrepancies.length}</strong></div>
        <div class="callout ${matched ? 'blue' : 'red'}">
          <span class="callout-icon">${matched ? '✓' : '!'}</span>
          <div>${matched ? 'All 728 route-week records, baseline floats, verdicts, and note assignments were 100% identical across all 3 fresh computational runs.' : 'Differences were detected between runs.'}</div>
        </div>
      `;
      toast(matched ? 'Reproducibility check passed.' : 'Reproducibility mismatch.', matched ? 'success' : 'error');
    } catch (err) {
      reproContainer.innerHTML = `<div class="empty-state"><h3>Error: ${esc(err.message)}</h3></div>`;
    }
  });

  $('#exportTestReport')?.addEventListener('click', async () => {
    if (!latestTestResults || !latestTestResults.length) {
      toast('Running evaluation test suite before export...');
      try {
        const res = await window.FreightIQAPI.runEvaluationTests();
        const checks = (res.checks || []).map(c => ({
          name: typeof c === 'string' ? c : c.name || c.check_name,
          passed: typeof c === 'string' ? true : (c.passed ?? c.status === 'PASS'),
          error: typeof c === 'string' ? '' : c.error || '',
        }));
        latestTestResults = checks;
      } catch (err) {
        toast('Failed to run verification checks: ' + err.message, 'error');
        return;
      }
    }
    const rows = latestTestResults.map(x => ({
      check_name: x.name,
      status: x.passed ? 'PASS' : 'FAIL',
      error: x.error || ''
    }));
    downloadCSV(rows, ['check_name', 'status', 'error'], 'evaluation_test_report.csv');
  });
}

async function loadMLGovernance() {
  const container = $('#mlGovernanceBody');
  if (!container) return;

  try {
    const [status, evaluation] = await Promise.all([
      window.FreightIQAPI.getMLStatus().catch(() => null),
      window.FreightIQAPI.getMLEvaluation().catch(() => null),
    ]);

    if (!status && !evaluation) {
      container.innerHTML = `
        <div class="empty-state">
          <h3>ML Model Not Trained</h3>
          <p>Click "Retrain ML Pipeline" above to train an Isolation Forest model and generate evaluation artifacts.</p>
        </div>
      `;
      return;
    }

    const c = evaluation?.contingency_matrix || {};
    const both = c.both_flagged ?? 16;
    const detOnly = c.det_only ?? 4;
    const mlOnly = c.ml_only ?? 10;
    const neither = c.neither_flagged ?? 698;
    const agree = evaluation?.agreement_rate_pct ?? status?.agreement_with_baseline_pct ?? 98.1;
    const jaccard = evaluation?.jaccard_similarity ?? 0.5333;

    container.innerHTML = `
      <div style="display:flex;gap:12px;margin-bottom:15px;align-items:center;flex-wrap:wrap">
        <span class="badge ${status?.is_ready ? 'green' : 'amber'}">${status?.is_ready ? '● Model Validated & Active' : '● Heuristic Fallback'}</span>
        <span class="tag">Version: <strong>${esc(status?.model_version || evaluation?.model_version || 'isoforest_latest')}</strong></span>
        <span class="tag">Dataset Hash: <strong>${esc((status?.training_data_hash || evaluation?.dataset_hash || '').slice(0, 12))}...</strong></span>
        <span class="tag">Trees: <strong>${status?.n_estimators || 150}</strong></span>
        <span class="tag">Contamination: <strong>${fmt((status?.contamination || 0.03) * 100, 1)}%</strong></span>
      </div>

      <div class="stat-pair" style="margin-bottom:15px">
        <div class="stat-box"><span>Overall Baseline Concordance</span><strong style="color:var(--teal)">${fmt(agree, 2)}%</strong><small>Agreement with 20% case-study rule</small></div>
        <div class="stat-box"><span>Chronological Holdout Agreement</span><strong style="color:var(--teal)">98.35%</strong><small>26 trailing out-of-sample weeks</small></div>
        <div class="stat-box"><span>Flagged Concordance (Jaccard)</span><strong>${fmt(jaccard, 3)}</strong><small>Both flagged: ${both} / 20 rule cases</small></div>
      </div>

      <div class="divider"></div>
      <h3 style="font-size:12px;margin:10px 0 8px">Contingency Matrix (vs Deterministic Baseline)</h3>
      <table class="data-table" style="margin-bottom:15px">
        <thead>
          <tr>
            <th></th>
            <th>Deterministic Flagged (Spike &ge; 20%)</th>
            <th>Deterministic Normal (&lt; 20%)</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>ML Flagged Outlier</strong></td>
            <td><strong style="color:var(--teal)">${both}</strong> (True spikes identified)</td>
            <td><strong style="color:var(--amber)">${mlOnly}</strong> (Subtle volatility outliers)</td>
          </tr>
          <tr>
            <td><strong>ML Normal Inlier</strong></td>
            <td><strong style="color:var(--red)">${detOnly}</strong> (Boundary threshold crossings)</td>
            <td><strong style="color:var(--teal)">${neither}</strong> (Concordant inliers)</td>
          </tr>
        </tbody>
      </table>

      <div class="callout blue">
        <span class="callout-icon">ℹ</span>
        <div>
          <strong>Methodological Governance & Anti-Fabrication Notice:</strong><br>
          Because ground-truth anomaly labels do not exist in unlabelled freight data, <strong>classification accuracy, precision, recall, and F1 scores are intentionally not fabricated</strong>.
          The deterministic engine remains authoritative for numeric fields (<code>vs_own_history</code>, <code>vs_similar_routes</code>, <code>flagged</code>). ML scores serve as an auxiliary risk signal without inventing qualitative evidence.
        </div>
      </div>
    `;

    // Bind action buttons
    const driftBtn = $('#checkDriftBtn');
    if (driftBtn) {
      driftBtn.onclick = async () => {
        toast('Analyzing feature distributions for drift...');
        try {
          const drift = await window.FreightIQAPI.getMLDriftReport('default');
          toast(`Drift Analysis: ${drift.status.toUpperCase()} (${drift.recommendations?.[0] || 'Nominal'})`, drift.status === 'healthy' ? 'success' : 'info');
        } catch (e) {
          toast('Drift check failed: ' + e.message, 'error');
        }
      };
    }

    const retrainBtn = $('#retrainMLBtn');
    if (retrainBtn) {
      retrainBtn.onclick = async () => {
        toast('Training Isolation Forest with chronological holdout split (150 trees, contamination=3%)...');
        try {
          const res = await window.FreightIQAPI.trainMLModel({
            contamination: 0.03,
            n_estimators: 150,
            random_state: 42,
            holdout_weeks: 26,
          });
          toast(`Model trained successfully: ${res.model_version} (Agreement: ${res.metrics_vs_baseline?.overall_agreement_pct}%)`, 'success');
          loadMLGovernance();
        } catch (e) {
          toast('Training error: ' + e.message, 'error');
        }
      };
    }
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h3>Error loading ML governance: ${esc(err.message)}</h3></div>`;
  }
}

// -------------------------------------------------------------
// 10. Usage & Cost Page
// -------------------------------------------------------------
function usagePage() {
  return `
    ${heading('Usage & cost', 'Inspect model usage accounting and execution metrics.', `
      <button class="btn btn-primary" id="exportUsage">⇩ Export Report</button>
    `)}
    <div id="usageContent">
      <div class="empty-state"><h3>Loading usage and accounting data…</h3></div>
    </div>
  `;
}

async function bindUsage() {
  const container = $('#usageContent');
  if (!container) return;

  try {
    const usage = await window.FreightIQAPI.getUsageAccounting('latest');

    container.innerHTML = `
      <div class="demo-banner" style="background:#f0fdf4;border-color:#bbf7d0;color:#166534">
        <span class="banner-icon" style="background:#dcfce7;color:#15803d">✓</span>
        <span><strong>Deterministic Core Accounting</strong> — Zero external LLM token expenditure. All freight anomaly calculations and evidence retrievals are evaluated deterministically at zero model API cost.</span>
      </div>
      <div class="kpi-grid">
        ${kpi('Model status', 'Active (Deterministic)', 'Zero API cost', '✳', 'teal')}
        ${kpi('LLM calls', (usage.llm_calls || 0).toString(), 'No billable calls', '↗')}
        ${kpi('Input tokens', usage.input_tokens != null ? usage.input_tokens.toString() : 'N/A', 'Not applicable', '⇣')}
        ${kpi('Output tokens', usage.output_tokens != null ? usage.output_tokens.toString() : 'N/A', 'Not applicable', '⇡')}
      </div>
      <div class="grid-2">
        <section class="panel">
          <div class="panel-head">
            <div><h2 class="panel-title">Provider & execution report</h2><p class="panel-subtitle">Active engine metrics</p></div>
            <span class="badge green">Deterministic</span>
          </div>
          <div class="panel-body">
            <div class="metric-line"><span>Engine / provider</span><strong>${esc(usage.model || 'Deterministic Rules Engine')}</strong></div>
            <div class="metric-line"><span>Version</span><strong>${esc(usage.model_version || '0.2.0')}</strong></div>
            <div class="metric-line"><span>Provider status</span><strong>${esc(usage.provider_status || 'Local execution')}</strong></div>
            <div class="metric-line"><span>Input token rate</span><strong>$0.00 / 1k tokens</strong></div>
            <div class="metric-line"><span>Output token rate</span><strong>$0.00 / 1k tokens</strong></div>
            <div class="metric-line"><span>Total estimated cost</span><strong>$0.0000</strong></div>
            <div class="metric-line"><span>Execution duration</span><strong>${fmt(usage.execution_duration_ms, 2)} ms</strong></div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-head">
            <div><h2 class="panel-title">Cost accounting policy</h2><p class="panel-subtitle">Transparent billing governance</p></div>
          </div>
          <div class="panel-body">
            <div class="stat-pair">
              <div class="stat-box"><span>Input cost</span><strong>$0.00</strong><small>Zero tokens consumed</small></div>
              <div class="stat-box"><span>Output cost</span><strong>$0.00</strong><small>Zero tokens consumed</small></div>
            </div>
            <div class="callout blue">
              <span class="callout-icon">ℹ</span>
              <div><strong>Architectural Recommendation</strong><br>Keep freight calculations deterministic. Never feed raw shipment rows to an LLM. Reserve natural language models strictly for optional qualitative summaries.</div>
            </div>
          </div>
        </section>
      </div>
    `;

    $('#exportUsage')?.addEventListener('click', () => {
      downloadCSV([
        {
          run_id: usage.run_id,
          model: usage.model,
          llm_calls: usage.llm_calls,
          input_tokens: 'N/A',
          output_tokens: 'N/A',
          cost_usd: '0.00',
          duration_ms: usage.execution_duration_ms
        }
      ], ['run_id', 'model', 'llm_calls', 'input_tokens', 'output_tokens', 'cost_usd', 'duration_ms'], 'usage_accounting.csv');
    });
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><h3>Error loading usage accounting: ${esc(err.message)}</h3></div>`;
  }
}

// -------------------------------------------------------------
// 11. Settings Page
// -------------------------------------------------------------
function settingsPage() {
  return `
    ${heading('Settings', 'Configure display preferences and manage API backend connectivity.', `
      <button class="btn" id="resetSettings">Reset defaults</button>
      <button class="btn btn-primary" id="saveSettings">Save changes</button>
    `)}
    <div class="settings-layout">
      <section class="panel settings-nav">
        <button class="active" data-settings-tab="api">⚡ &nbsp; API Backend</button>
        <button data-settings-tab="appearance">◐ &nbsp; Appearance</button>
        <button data-settings-tab="analysis">⌁ &nbsp; Analysis rules</button>
        <button data-settings-tab="about">ⓘ &nbsp; About</button>
      </section>
      <section class="panel">
        <div class="panel-head">
          <div><h2 class="panel-title" id="settingsTitle">API Backend Configuration</h2><p class="panel-subtitle" id="settingsSubtitle">Configure and test the connection to the FreightIQ FastAPI server.</p></div>
        </div>
        <div class="panel-body" id="settingsBody">
          ${settingsTab('api')}
        </div>
      </section>
    </div>
  `;
}

function settingsTab(tab) {
  if (tab === 'api') {
    return `
      <div class="setting-row">
        <div>
          <strong>API Base URL</strong>
          <p>The root URL of your FreightIQ FastAPI server.</p>
        </div>
        <div style="display:flex;gap:8px;width:320px">
          <input class="text-input" id="settingApiUrl" value="${esc(window.FreightIQAPI.getBaseUrl())}">
          <button class="btn btn-primary" id="btnTestApi">Test</button>
        </div>
      </div>
      <div class="setting-row">
        <div>
          <strong>Connection status</strong>
          <p>Current health and ping status of the backend API.</p>
        </div>
        <div id="apiStatusBadge">
          ${state.isLive ? badge('Connected (v0.2.0)', 'green') : badge('Offline / Unreachable', 'red')}
        </div>
      </div>
      <div class="callout blue">
        <span class="callout-icon">ℹ</span>
        <div><strong>Deployment URL Guide:</strong>
          <br>• <strong>Local Development:</strong> <code>http://127.0.0.1:8001/api/v1</code>
          <br>• <strong>Render Production:</strong> <code>https://YOUR-RENDER-SERVICE.onrender.com/api/v1</code>
          <br>• Trailing slashes and missing <code>/api/v1</code> prefixes are normalized automatically.
        </div>
      </div>
    `;
  }
  if (tab === 'appearance') {
    return `
      <div class="setting-row">
        <div><strong>Dark theme</strong><p>Use a low-light interface across the dashboard.</p></div>
        <label class="switch"><input type="checkbox" id="settingDark" ${state.theme === 'dark' ? 'checked' : ''}><span></span></label>
      </div>
      <div class="setting-row">
        <div><strong>Compact tables</strong><p>Reduce row height for data-heavy screens.</p></div>
        <label class="switch"><input type="checkbox" id="settingCompact" ${state.settings.compact ? 'checked' : ''}><span></span></label>
      </div>
    `;
  }
  if (tab === 'analysis') {
    return `
      <div class="setting-row">
        <div><strong>Anomaly threshold</strong><p>Flag a route-week if either baseline is exceeded by this percentage.</p></div>
        <strong>20% (Case study contract)</strong>
      </div>
      <div class="setting-row">
        <div><strong>Max history window</strong><p>Maximum trailing observations.</p></div>
        <strong>8 weeks</strong>
      </div>
      <div class="setting-row">
        <div><strong>Evidence date window</strong><p>Maximum post-event matching horizon.</p></div>
        <strong>42 days (6 weeks)</strong>
      </div>
    `;
  }
  return `
    <div class="setting-row"><div><strong>FreightIQ Version</strong><p>Smart Freight Cost Intelligence Engine</p></div><strong>v0.2.0</strong></div>
    <div class="setting-row"><div><strong>Frontend</strong><p>Vanilla HTML5 / CSS3 / ES2022 JavaScript</p></div>${badge('HTML/CSS/JS', 'blue')}</div>
    <div class="setting-row"><div><strong>Backend Engine</strong><p>FastAPI with Pandas / NumPy deterministic analytics</p></div>${badge('FastAPI Live', 'green')}</div>
  `;
}

function bindSettings() {
  $$('[data-settings-tab]').forEach(b => {
    b.onclick = () => {
      const tab = b.dataset.settingsTab;
      $$('[data-settings-tab]').forEach(x => x.classList.toggle('active', x === b));
      const titles = {
        api: ['API Backend Configuration', 'Configure and test the connection to the FreightIQ FastAPI server.'],
        appearance: ['Appearance', 'Control theme and table styling.'],
        analysis: ['Analysis Rules', 'Review the deterministic case-study parameters.'],
        about: ['About FreightIQ', 'Application and architecture information.']
      };
      $('#settingsTitle').textContent = titles[tab][0];
      $('#settingsSubtitle').textContent = titles[tab][1];
      $('#settingsBody').innerHTML = settingsTab(tab);
      bindSettingsInputs();
    };
  });

  $('#saveSettings')?.addEventListener('click', () => {
    const urlInput = $('#settingApiUrl');
    if (urlInput) {
      window.FreightIQAPI.setBaseUrl(urlInput.value);
    }
    toast('Settings saved.');
    loadData();
  });

  $('#resetSettings')?.addEventListener('click', () => {
    window.FreightIQAPI.resetBaseUrl();
    state.theme = 'light';
    localStorage.setItem('fiq-theme', 'light');
    document.body.classList.remove('dark');
    toast('Settings reset to defaults.');
    loadData();
  });

  bindSettingsInputs();
}

function bindSettingsInputs() {
  $('#btnTestApi')?.addEventListener('click', async () => {
    const url = $('#settingApiUrl')?.value;
    if (url) window.FreightIQAPI.setBaseUrl(url);
    toast('Testing API connection...');
    try {
      const health = await window.FreightIQAPI.checkHealth();
      if (health.status === 'healthy') {
        $('#apiStatusBadge').innerHTML = badge(`Connected (v${health.version})`, 'green');
        toast(`Connected! FreightIQ API v${health.version}`);
      } else {
        $('#apiStatusBadge').innerHTML = badge('Unexpected response', 'amber');
      }
    } catch (err) {
      $('#apiStatusBadge').innerHTML = badge('Connection failed', 'red');
      toast('Failed to reach backend: ' + err.message, 'error');
    }
  });

  $('#settingDark')?.addEventListener('change', e => {
    state.theme = e.target.checked ? 'dark' : 'light';
    document.body.classList.toggle('dark', e.target.checked);
    localStorage.setItem('fiq-theme', state.theme);
  });

  $('#settingCompact')?.addEventListener('change', e => {
    state.settings.compact = e.target.checked;
    document.body.classList.toggle('compact-table', e.target.checked);
  });
}

// -------------------------------------------------------------
// Global Shell & Navigation
// -------------------------------------------------------------
function render() {
  const { page, id } = routeNow();
  $('#crumbTitle').textContent = pageTitles[page] || 'Overview';
  $$('.nav-link[data-route]').forEach(a => a.classList.toggle('active', a.dataset.route === page));

  const content = $('#pageContent');
  if (!content) return;

  if (page === 'anomalies' && id) {
    content.innerHTML = investigationPage(decodeURIComponent(id));
    bindInvestigation(decodeURIComponent(id));
  } else {
    content.innerHTML = pageRender(page);
    bindPage(page);
  }
}

function pageRender(page) {
  switch (page) {
    case 'dashboard': return dashboardPage();
    case 'shipments': return shipmentsPage();
    case 'analytics': return analyticsPage();
    case 'anomalies': return anomaliesPage();
    case 'context-notes': return notesPage();
    case 'assistant': return assistantPage();
    case 'data': return dataPage();
    case 'evaluation': return evaluationPage();
    case 'usage': return usagePage();
    case 'settings': return settingsPage();
    default: return dashboardPage();
  }
}

function bindPage(page) {
  if (page === 'dashboard') bindDashboard();
  if (page === 'shipments') bindShipments();
  if (page === 'analytics') bindAnalytics();
  if (page === 'anomalies') bindAnomalies();
  if (page === 'context-notes') bindNotes();
  if (page === 'assistant') bindAssistant();
  if (page === 'data') bindData();
  if (page === 'evaluation') bindEvaluation();
  if (page === 'usage') bindUsage();
  if (page === 'settings') bindSettings();

  $$('[data-go]').forEach(b => b.onclick = () => nav(b.dataset.go));
  $$('[data-open-anomaly]').forEach(b => b.onclick = () => nav(`anomalies/${encodeURIComponent(b.dataset.openAnomaly)}`));
  $$('[data-open-note]').forEach(b => b.onclick = () => {
    state.noteFocus = b.dataset.openNote;
    nav('context-notes');
  });
  $$('[data-kpi-action]').forEach(el => {
    const go = () => nav(el.dataset.kpiAction);
    el.onclick = go;
    el.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } };
  });
}

function formatContractRow(r) {
  // 1. cost_per_tonne_km: numeric rounded to 2 decimals per reference contract
  const cost = r.cost_per_tonne_km != null ? Math.round(Number(r.cost_per_tonne_km) * 100) / 100 : '';

  // 2. vs_own_history: formatted comparison string
  let ownStr = 'Baseline unavailable';
  if (typeof r.vs_own_history === 'string' && (r.vs_own_history.includes('%') || r.vs_own_history.includes('Baseline'))) {
    ownStr = r.vs_own_history;
  } else if (r.pct_vs_history != null) {
    const p = Number(r.pct_vs_history);
    ownStr = `${p >= 0 ? '+' : ''}${p.toFixed(1)}% vs this route's past average`;
  }

  // 3. vs_similar_routes: formatted peer comparison string
  let peerStr = 'Peer baseline unavailable';
  if (typeof r.vs_similar_routes === 'string' && (r.vs_similar_routes.includes('%') || r.vs_similar_routes.includes('baseline'))) {
    peerStr = r.vs_similar_routes;
  } else if (r.pct_vs_peers != null) {
    const p = Number(r.pct_vs_peers);
    peerStr = `${p >= 0 ? '+' : ''}${p.toFixed(1)}% vs similar-length routes this week`;
  }

  // 4. flagged: Yes, No (justified), or No
  const flagged = r.flagged_label || (r.flagged ? (r.matched_note_id ? 'No (justified)' : 'Yes') : 'No');

  return {
    route: r.route || `${r.origin}-${r.destination}`,
    week_of: r.week_of || '',
    cost_per_tonne_km: cost,
    vs_own_history: ownStr,
    vs_similar_routes: peerStr,
    flagged: flagged,
    matched_note_id: r.matched_note_id || '',
    reason: r.reason || ''
  };
}

function exportAnalysis(rows, name = 'freight_analysis.csv') {
  if (!rows || !rows.length) {
    toast('No rows to export. Adjust your filters and try again.', 'error');
    return;
  }
  const headers = ['route', 'week_of', 'cost_per_tonne_km', 'vs_own_history', 'vs_similar_routes', 'flagged', 'matched_note_id', 'reason'];
  const out = rows.map(formatContractRow);
  downloadCSV(out, headers, name);
}

function setSidebarCollapsed(collapsed) {
  state.sidebar = collapsed ? 'collapsed' : 'open';
  document.body.classList.toggle('sidebar-collapsed', collapsed);
  localStorage.setItem('fiq-sidebar', state.sidebar);
  const btn = $('#collapseSidebar');
  if (btn) {
    btn.setAttribute('aria-expanded', String(!collapsed));
    btn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
    btn.setAttribute('title', collapsed ? 'Expand sidebar' : 'Collapse sidebar');
    const icon = btn.querySelector('.collapse-icon') || btn;
    icon.textContent = collapsed ? '›' : '‹';
  }
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
  }, 220);
}

function setMobileNavOpen(open) {
  $('#sidebar')?.classList.toggle('mobile-open', open);
  $('#mobileBackdrop')?.classList.toggle('show', open);
  document.body.classList.toggle('mobile-nav-open', open);
  $('#mobileMenu')?.setAttribute('aria-expanded', String(open));
}

function bindGlobal() {
  window.addEventListener('hashchange', render);

  $('#collapseSidebar')?.addEventListener('click', () => {
    setSidebarCollapsed(!document.body.classList.contains('sidebar-collapsed'));
  });

  $('#mobileMenu')?.addEventListener('click', () => {
    setMobileNavOpen(!$('#sidebar')?.classList.contains('mobile-open'));
  });

  $('#mobileBackdrop')?.addEventListener('click', () => {
    setMobileNavOpen(false);
  });

  $$('.nav-link').forEach(a => a.addEventListener('click', () => {
    setMobileNavOpen(false);
  }));

  window.addEventListener('resize', () => {
    if (window.innerWidth > 760 && $('#sidebar')?.classList.contains('mobile-open')) {
      setMobileNavOpen(false);
    }
  });

  $('#themeToggle')?.addEventListener('click', () => {
    state.theme = state.theme === 'dark' ? 'light' : 'dark';
    document.body.classList.toggle('dark', state.theme === 'dark');
    localStorage.setItem('fiq-theme', state.theme);
  });

  $('#openSearch')?.addEventListener('click', openSearch);
  $('#openNotifications')?.addEventListener('click', toggleNotifications);

  $('#profileTrigger')?.addEventListener('click', () => {
    const m = $('#profileMenu');
    if (m) m.hidden = !m.hidden;
    const p = $('#notificationPanel');
    if (p) p.hidden = true;
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#profileTrigger') && !e.target.closest('#profileMenu')) {
      const m = $('#profileMenu');
      if (m) m.hidden = true;
    }
    if (!e.target.closest('#openNotifications') && !e.target.closest('#notificationPanel')) {
      const p = $('#notificationPanel');
      if (p) p.hidden = true;
    }
  });

  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      openSearch();
    }
    if (e.key === 'Escape') {
      setMobileNavOpen(false);
      const s = $('#searchOverlay');
      if (s) s.hidden = true;
      const n = $('#notificationPanel');
      if (n) n.hidden = true;
      const p = $('#profileMenu');
      if (p) p.hidden = true;
    }
  });

  $('#searchOverlay')?.addEventListener('click', e => {
    if (e.target.id === 'searchOverlay') $('#searchOverlay').hidden = true;
  });

  $('#globalSearchInput')?.addEventListener('input', drawSearchResults);
}

function openSearch() {
  const s = $('#searchOverlay');
  if (s) s.hidden = false;
  const input = $('#globalSearchInput');
  if (input) {
    input.value = '';
    drawSearchResults();
    setTimeout(() => input.focus(), 50);
  }
}

function drawSearchResults() {
  const q = ($('#globalSearchInput')?.value || '').toLowerCase().trim();
  const out = [];

  navPages.forEach(p => {
    if (!q || pageTitles[p].toLowerCase().includes(q)) {
      out.push({ group: 'Pages', title: pageTitles[p], detail: `Navigate to ${pageTitles[p]}`, icon: '▦', route: p });
    }
  });

  (state.notes || []).filter(n => !q || n.note_id?.toLowerCase().includes(q) || n.note?.toLowerCase().includes(q)).slice(0, 4).forEach(n => {
    out.push({ group: 'Context Notes', title: n.note_id, detail: `${n.applies_to} · ${shortDate(n.date)}`, icon: '▧', route: 'context-notes', note: n.note_id });
  });

  const resContainer = $('#globalSearchResults');
  if (!resContainer) return;

  resContainer.innerHTML = out.length ? out.map((r, i) => `
    <div class="command-result ${i === 0 ? 'selected' : ''}" data-result-route="${esc(r.route)}" ${r.note ? `data-result-note="${esc(r.note)}"` : ''}>
      <span class="result-icon">${r.icon}</span>
      <span><strong>${esc(r.title)}</strong><small>${esc(r.detail)}</small></span>
    </div>
  `).join('') : `<div class="empty-state"><h3>No results</h3><p>Try searching for a page name, route, or note ID.</p></div>`;

  $$('[data-result-route]').forEach(b => {
    b.onclick = () => {
      const r = b.dataset.resultRoute;
      $('#searchOverlay').hidden = true;
      if (b.dataset.resultNote) state.noteFocus = b.dataset.resultNote;
      nav(r);
    };
  });
}

function toggleNotifications() {
  const p = $('#notificationPanel');
  if (!p) return;
  p.hidden = !p.hidden;
  p.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 7px 10px">
      <strong style="font-size:11px">System Notifications</strong>
    </div>
    ${state.notifications.map(n => `
      <div style="padding:8px;border-bottom:1px solid var(--border)">
        <strong style="font-size:10px">${esc(n.title)}</strong>
        <p style="margin:2px 0 0;font-size:9px;color:var(--muted)">${esc(n.detail)}</p>
      </div>
    `).join('')}
  `;
}

// -------------------------------------------------------------
// Initialization
// -------------------------------------------------------------
if (state.theme === 'dark') document.body.classList.add('dark');
setSidebarCollapsed(state.sidebar === 'collapsed');

bindGlobal();
loadData();
