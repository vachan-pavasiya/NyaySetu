/**
 * Application Configuration & API URL Helper
 * Reads VITE_API_URL from environment variables for production deployments.
 * Defaults to the live Render deployment if not explicitly configured in production.
 */

const rawApiUrl = import.meta.env.VITE_API_URL;

// If VITE_API_URL is provided, use it. In production, default to live Render backend.
export const API_BASE_URL: string = rawApiUrl
  ? rawApiUrl.replace(/\/+$/, '')
  : (import.meta.env.PROD ? 'https://nyaysetu-backend-dfr6.onrender.com' : '');

/**
 * Build absolute API URL if API_BASE_URL is configured,
 * otherwise return relative /api path for same-domain or Vite reverse proxy.
 */
export function getApiUrl(endpoint: string): string {
  const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  if (API_BASE_URL) {
    return `${API_BASE_URL}${clean}`;
  }
  return clean.startsWith('/api') ? clean : `/api${clean}`;
}
