# FreightIQ — Frontend Dashboard

The user-facing dashboard for **FreightIQ — Smart Freight Cost Intelligence**, built with HTML5, CSS3, and modern vanilla JavaScript.

---

## Architecture Overview

- **Framework**: Semantic HTML5, Vanilla CSS3 (custom dark/light design system), and ES2022 JavaScript.
- **Visualizations**: Responsive charts powered by Chart.js.
- **Routing**: Client-side hash routing (`#/dashboard`, `#/shipments`, `#/analytics`, `#/anomalies`, `#/context-notes`, `#/assistant`, `#/data`, `#/evaluation`, `#/usage`, `#/settings`).
- **API Client**: Centralized HTTP client (`js/api-client.js`) with configurable timeout, retry logic, request cancellation, and URL normalization.
- **Runtime Configuration**: Managed via `js/config.js` and in-app Settings (⚙).

---

## Local Development

From inside the `frontend/` directory:

```bash
# Option A: Built-in Python HTTP server
python -m http.server 8000

# Option B: Node.js static serve
npm run dev
```

Open your browser at `http://localhost:8000`. In local development, the frontend automatically connects to the local FastAPI backend at `http://127.0.0.1:8001/api/v1`.

---

## Vercel Deployment

This frontend is configured for deployment on Vercel:

1. **Root Directory**: `frontend`
2. **Framework Preset**: `Other`
3. **Build Command**: `npm run build` (executes zero-dependency `node build-config.js`)
4. **Output Directory**: `.`
5. **Environment Variable**:
   - `FREIGHTIQ_API_BASE_URL`: `https://YOUR-RENDER-SERVICE.onrender.com/api/v1`

Configuration details, security headers, and clean URLs are governed by [`vercel.json`](file:///frontend/vercel.json).
