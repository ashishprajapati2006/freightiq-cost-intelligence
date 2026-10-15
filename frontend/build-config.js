/**
 * FreightIQ Frontend Build Script
 *
 * Runs during deployment (e.g., on Vercel) to inject environment variables
 * into js/config.js. Uses only built-in Node.js modules (fs, path).
 * Zero npm dependencies required.
 */
const fs = require('fs');
const path = require('path');

const configPath = path.join(__dirname, 'js', 'config.js');
let apiUrl = (
  process.env.FREIGHTIQ_API_BASE_URL ||
  process.env.VITE_API_BASE_URL ||
  process.env.API_BASE_URL ||
  ""
).trim();

// Normalize URL: remove trailing slash and ensure /api/v1 suffix if not present
if (apiUrl) {
  apiUrl = apiUrl.replace(/\/+$/, '');
  if (!apiUrl.endsWith('/api/v1') && !apiUrl.includes('/api/')) {
    apiUrl += '/api/v1';
  }
}

const content = `/**
 * FreightIQ Runtime Frontend Configuration
 *
 * Generated/updated during build.
 */
window.__FREIGHTIQ_CONFIG__ = {
  // Render Backend URL
  API_BASE_URL: ${JSON.stringify(apiUrl)},
  // Local development fallback
  DEFAULT_LOCAL_URL: "http://127.0.0.1:8001/api/v1",
  TIMEOUT_MS: 15000
};
`;

try {
  fs.writeFileSync(configPath, content, 'utf8');
  console.log(`[FreightIQ Build] Injected API_BASE_URL: "${apiUrl || '(empty; runtime will auto-detect)'}"`);
} catch (err) {
  console.error('[FreightIQ Build] Failed to write config.js:', err.message);
  process.exit(1);
}
