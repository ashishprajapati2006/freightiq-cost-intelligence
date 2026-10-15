/**
 * FreightIQ Centralized API Client
 *
 * Provides configurable base URL, timeout handling, retry logic for idempotent requests,
 * request cancellation, and structured error reporting.
 */
(function(window) {
  'use strict';

  const DEFAULT_LOCAL_URL = 'http://127.0.0.1:8001/api/v1';
  const STORAGE_KEY = 'fiq_api_base_url';

  function isLocalEnvironment() {
    if (typeof window === 'undefined') return true;
    const hostname = window.location.hostname;
    return (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '0.0.0.0' ||
      hostname === '' ||
      hostname === '::1' ||
      window.location.protocol === 'file:'
    );
  }

  function normalizeApiUrl(rawUrl) {
    if (!rawUrl) return '';
    let url = String(rawUrl).trim().replace(/\/+$/, '');
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://' + url;
    }
    if (!url.endsWith('/api/v1') && !url.includes('/api/')) {
      url += '/api/v1';
    }
    return url;
  }

  class ApiClient {
    constructor() {
      this.isLocal = isLocalEnvironment();
      this.activeRequests = new Map();
      this.listeners = new Set();
      this.isOnline = null;
      this.diagnosticError = null;

      // Configuration resolution hierarchy:
      // 1. window.__FREIGHTIQ_CONFIG__ (injected via config.js / build)
      // 2. localStorage user setting (via Settings UI)
      // 3. window.API_BASE_URL (legacy / manual override)
      const envConfig = window.__FREIGHTIQ_CONFIG__?.API_BASE_URL;
      const globalConfig = window.API_BASE_URL || window.FREIGHTIQ_API_BASE_URL;
      const storedUrl = localStorage.getItem(STORAGE_KEY);

      let resolved = (envConfig && envConfig.trim()) ||
                     (storedUrl && storedUrl.trim()) ||
                     (globalConfig && globalConfig.trim()) ||
                     '';

      // Guard against stale localhost URLs when deployed to remote domains (Vercel)
      if (resolved && !this.isLocal && (resolved.includes('127.0.0.1') || resolved.includes('localhost'))) {
        console.warn('[FreightIQ API] Stale localhost URL detected on non-local domain. Resetting to unconfigured.');
        localStorage.removeItem(STORAGE_KEY);
        resolved = (envConfig && !envConfig.includes('localhost') && !envConfig.includes('127.0.0.1')) ? envConfig.trim() : '';
      }

      if (resolved) {
        this.baseUrl = normalizeApiUrl(resolved);
        this.isConfigured = true;
      } else if (this.isLocal) {
        this.baseUrl = DEFAULT_LOCAL_URL;
        this.isConfigured = true;
      } else {
        this.baseUrl = '';
        this.isConfigured = false;
        this.diagnosticError = 'Render Backend API URL is not configured. Please set FREIGHTIQ_API_BASE_URL on Vercel or configure your Render backend URL in Settings (⚙).';
      }

      this.timeoutMs = window.__FREIGHTIQ_CONFIG__?.TIMEOUT_MS || 15000;
    }

    getBaseUrl() {
      return this.baseUrl || (this.isLocal ? DEFAULT_LOCAL_URL : '');
    }

    setBaseUrl(url) {
      if (!url || !url.trim()) {
        this.baseUrl = this.isLocal ? DEFAULT_LOCAL_URL : '';
        this.isConfigured = this.isLocal;
        this.diagnosticError = this.isLocal ? null : 'Backend API URL is unconfigured.';
        localStorage.removeItem(STORAGE_KEY);
      } else {
        this.baseUrl = normalizeApiUrl(url);
        this.isConfigured = true;
        this.diagnosticError = null;
        localStorage.setItem(STORAGE_KEY, this.baseUrl);
      }
      this.notifyListeners('config_changed', { baseUrl: this.baseUrl, isConfigured: this.isConfigured });
    }

    resetBaseUrl() {
      localStorage.removeItem(STORAGE_KEY);
      if (this.isLocal) {
        this.baseUrl = DEFAULT_LOCAL_URL;
        this.isConfigured = true;
        this.diagnosticError = null;
      } else {
        const envConfig = window.__FREIGHTIQ_CONFIG__?.API_BASE_URL;
        if (envConfig && envConfig.trim()) {
          this.baseUrl = normalizeApiUrl(envConfig);
          this.isConfigured = true;
          this.diagnosticError = null;
        } else {
          this.baseUrl = '';
          this.isConfigured = false;
          this.diagnosticError = 'Render Backend API URL not configured. Enter Render service URL in Settings.';
        }
      }
      this.notifyListeners('config_changed', { baseUrl: this.baseUrl, isConfigured: this.isConfigured });
    }

    onStateChange(fn) {
      this.listeners.add(fn);
      return () => this.listeners.delete(fn);
    }

    notifyListeners(event, data) {
      for (const fn of this.listeners) {
        try { fn(event, data); } catch (e) { console.error('Listener error:', e); }
      }
    }

    async request(endpoint, options = {}) {
      if (!this.isConfigured || !this.baseUrl) {
        const msg = this.diagnosticError || 'Render Backend API URL is not configured. Go to Settings (⚙) to enter your backend URL.';
        const configErr = new Error(msg);
        configErr.code = 'CONFIG_ERROR';
        this.notifyListeners('offline', { url: endpoint, error: msg });
        throw configErr;
      }

      const url = `${this.baseUrl}${endpoint.startsWith('/') ? endpoint : '/' + endpoint}`;
      const method = (options.method || 'GET').toUpperCase();
      const requestId = options.requestId || `${method}_${endpoint}`;

      // Cancel any ongoing identical request if needed
      if (options.cancelPrevious && this.activeRequests.has(requestId)) {
        this.activeRequests.get(requestId).abort();
        this.activeRequests.delete(requestId);
      }

      const controller = new AbortController();
      this.activeRequests.set(requestId, controller);

      const timeoutId = setTimeout(() => {
        controller.abort();
      }, options.timeout || this.timeoutMs);

      const headers = { ...options.headers };
      if (!options.isFormData && !headers['Content-Type'] && options.body && typeof options.body === 'string') {
        headers['Content-Type'] = 'application/json';
      }
      if (!headers['Accept']) {
        headers['Accept'] = options.isBlob ? '*/*' : 'application/json';
      }

      const fetchOptions = {
        method,
        headers,
        signal: controller.signal,
      };

      if (options.body) {
        fetchOptions.body = options.body;
      }

      const execute = async (retryCount = 0) => {
        try {
          const response = await fetch(url, fetchOptions);
          clearTimeout(timeoutId);
          this.activeRequests.delete(requestId);

          this.isOnline = true;
          this.notifyListeners('online', { url });

          if (!response.ok) {
            let errorData;
            try {
              errorData = await response.json();
            } catch {
              errorData = { error: { message: `HTTP ${response.status} ${response.statusText}` } };
            }
            const err = new Error(errorData.error?.message || errorData.detail || `Request failed with status ${response.status}`);
            err.status = response.status;
            err.code = errorData.error?.code || 'API_ERROR';
            err.details = errorData.error?.details || null;
            err.requestId = response.headers.get('X-Request-ID');
            throw err;
          }

          if (options.isBlob) {
            return await response.blob();
          }
          if (options.isText) {
            return await response.text();
          }
          const data = await response.json();
          if (data && data.pagination && data.pagination.total_items !== undefined) {
            data.pagination.total = data.pagination.total_items;
          }
          return data;
        } catch (err) {
          clearTimeout(timeoutId);
          this.activeRequests.delete(requestId);

          if (err.name === 'AbortError') {
            const timeoutErr = new Error(`Request timed out after ${this.timeoutMs}ms: ${endpoint}`);
            timeoutErr.code = 'TIMEOUT';
            throw timeoutErr;
          }

          // Retry once on network failures for idempotent GET requests
          if (method === 'GET' && retryCount < 1 && err.status === undefined) {
            await new Promise(r => setTimeout(r, 800));
            return execute(retryCount + 1);
          }

          if (err.status === undefined) {
            this.isOnline = false;
            this.notifyListeners('offline', { url, error: err.message });
          }
          throw err;
        }
      };

      return execute();
    }

    // 1. Health & Metadata
    async checkHealth() {
      return this.request('/health', { timeout: 4000 });
    }

    async getMetadata() {
      return this.request('/metadata');
    }

    async listDatasets() {
      return this.request('/datasets');
    }

    async getDataset(datasetId) {
      return this.request(`/datasets/${encodeURIComponent(datasetId)}`);
    }

    // 2. Dataset Ingestion
    async validateDataset(shipmentsFile, notesFile = null) {
      const formData = new FormData();
      formData.append('shipments_file', shipmentsFile);
      if (notesFile) formData.append('notes_file', notesFile);

      return this.request('/datasets/validate', {
        method: 'POST',
        body: formData,
        isFormData: true,
        timeout: 45000,
      });
    }

    async importDataset(shipmentsFile, notesFile = null, datasetName = 'Imported Dataset', setActive = true) {
      const formData = new FormData();
      formData.append('shipments_file', shipmentsFile);
      if (notesFile) formData.append('notes_file', notesFile);
      formData.append('dataset_name', datasetName);
      formData.append('set_active', String(setActive));

      return this.request('/datasets/import', {
        method: 'POST',
        body: formData,
        isFormData: true,
        timeout: 45000,
      });
    }

    // 3. Analysis Runs
    async runAnalysis(config = {}) {
      return this.request('/analysis/run', {
        method: 'POST',
        body: JSON.stringify({
          threshold_pct: config.threshold_pct ?? 20.0,
          max_history_weeks: config.max_history_weeks ?? 8,
          note_window_days: config.note_window_days ?? 42,
          dataset_id: config.dataset_id || null,
        }),
      });
    }

    async listRuns() {
      return this.request('/analysis/runs');
    }

    async getRun(runId) {
      return this.request(`/analysis/runs/${encodeURIComponent(runId)}`);
    }

    async getRunMetrics(runId) {
      return this.request(`/analysis/runs/${encodeURIComponent(runId)}/metrics`);
    }

    async getRunResults(runId, params = {}) {
      const qs = new URLSearchParams();
      if (params.route) qs.set('route', params.route);
      if (params.route_type) qs.set('route_type', params.route_type);
      if (params.flagged) qs.set('flagged', params.flagged);
      if (params.evidence) qs.set('evidence', params.evidence);
      if (params.search) qs.set('search', params.search);
      if (params.page) qs.set('page', params.page);
      if (params.page_size) qs.set('page_size', params.page_size);
      if (params.sort_by) qs.set('sort_by', params.sort_by);
      if (params.sort_dir) qs.set('sort_dir', params.sort_dir);

      return this.request(`/analysis/runs/${encodeURIComponent(runId)}/results?${qs.toString()}`);
    }

    // 4. Dashboard & Analytics
    async getDashboardSummary() {
      return this.request('/dashboard/summary');
    }

    async getWeeklyCosts(params = {}) {
      const qs = new URLSearchParams();
      if (params.route) qs.set('route', params.route);
      if (params.route_type) qs.set('route_type', params.route_type);
      if (params.limit) qs.set('limit', params.limit);

      return this.request(`/analytics/weekly-costs?${qs.toString()}`);
    }

    async getRoutes() {
      return this.request('/analytics/routes');
    }

    async getRouteTimeline(routeId) {
      return this.request(`/analytics/routes/${encodeURIComponent(routeId)}`);
    }

    // 5. Shipments
    async getShipments(params = {}) {
      const qs = new URLSearchParams();
      if (params.search) qs.set('search', params.search);
      if (params.route) qs.set('route', params.route);
      if (params.route_type && params.route_type !== 'all') qs.set('route_type', params.route_type);
      if (params.origin && params.origin !== 'all') qs.set('origin', params.origin);
      if (params.destination && params.destination !== 'all') qs.set('destination', params.destination);
      if (params.material && params.material !== 'all') qs.set('material', params.material);
      if (params.page) qs.set('page', params.page);
      if (params.page_size) qs.set('page_size', params.page_size);
      if (params.sort_by) qs.set('sort_by', params.sort_by);
      if (params.sort_dir) qs.set('sort_dir', params.sort_dir);

      return this.request(`/shipments?${qs.toString()}`);
    }

    async getShipmentDetail(shipmentId) {
      return this.request(`/shipments/${encodeURIComponent(shipmentId)}`);
    }

    // 6. Anomalies & Evidence
    async getAnomalies(params = {}) {
      const qs = new URLSearchParams();
      if (params.search) qs.set('search', params.search);
      if (params.route) qs.set('route', params.route);
      if (params.route_type && params.route_type !== 'all') qs.set('route_type', params.route_type);
      if (params.evidence && params.evidence !== 'all') qs.set('evidence', params.evidence);
      if (params.flagged) qs.set('flagged', params.flagged);
      if (params.min_deviation) qs.set('min_deviation', params.min_deviation);
      if (params.page) qs.set('page', params.page);
      if (params.page_size) qs.set('page_size', params.page_size);
      if (params.sort_by) qs.set('sort_by', params.sort_by);
      if (params.sort_dir) qs.set('sort_dir', params.sort_dir);

      return this.request(`/anomalies?${qs.toString()}`);
    }

    async getAnomalyDetail(anomalyId) {
      return this.request(`/anomalies/${encodeURIComponent(anomalyId)}`);
    }

    async getAnomalyEvidence(anomalyId) {
      return this.request(`/anomalies/${encodeURIComponent(anomalyId)}/evidence`);
    }

    // 7. Context Notes
    async getContextNotes(params = {}) {
      const qs = new URLSearchParams();
      if (params.search) qs.set('search', params.search);
      if (params.scope && params.scope !== 'all') qs.set('scope', params.scope);

      return this.request(`/context-notes?${qs.toString()}`);
    }

    async getContextNoteDetail(noteId) {
      return this.request(`/context-notes/${encodeURIComponent(noteId)}`);
    }

    // 8. AI Assistant
    async queryAssistant(query, route = null, weekOf = null) {
      return this.request('/assistant/query', {
        method: 'POST',
        body: JSON.stringify({ query, route, week_of: weekOf }),
      });
    }

    // 9. Evaluation & Reproducibility
    async runReproducibility() {
      return this.request('/evaluation/reproducibility', { method: 'POST', timeout: 30000 });
    }

    async runEvaluationTests() {
      return this.request('/evaluation/tests', { method: 'POST', timeout: 30000 });
    }

    async getUsageAccounting(runId) {
      return this.request(`/usage/runs/${encodeURIComponent(runId)}`);
    }

    // 10. Machine Learning Pipeline & Governance
    async getMLStatus() {
      return this.request('/ml/status');
    }

    async trainMLModel(params = {}) {
      return this.request('/ml/train', {
        method: 'POST',
        body: JSON.stringify(params),
        timeout: 45000,
      });
    }

    async scoreMLAnomalies(params = {}) {
      return this.request('/ml/score', {
        method: 'POST',
        body: JSON.stringify(params),
      });
    }

    async getMLEvaluation() {
      return this.request('/ml/evaluation');
    }

    async getMLDriftReport(datasetId = 'default') {
      return this.request(`/ml/monitoring/drift?dataset_id=${encodeURIComponent(datasetId)}`);
    }

    // 11. Direct Export URL generators
    getContractExportUrl(runId) {
      return this.baseUrl ? `${this.baseUrl}/analysis/runs/${encodeURIComponent(runId)}/export.csv` : '';
    }

    getShipmentsExportUrl(params = {}) {
      if (!this.baseUrl) return '';
      const qs = new URLSearchParams();
      if (params.route) qs.set('route', params.route);
      if (params.route_type) qs.set('route_type', params.route_type);
      return `${this.baseUrl}/shipments/export.csv?${qs.toString()}`;
    }

    getAnomaliesExportUrl(params = {}) {
      if (!this.baseUrl) return '';
      const qs = new URLSearchParams();
      if (params.flagged_only !== undefined) qs.set('flagged_only', String(params.flagged_only));
      if (params.evidence) qs.set('evidence', params.evidence);
      return `${this.baseUrl}/anomalies/export.csv?${qs.toString()}`;
    }
  }

  window.FreightIQAPI = new ApiClient();
})(window);
