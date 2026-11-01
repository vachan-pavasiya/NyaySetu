/**
 * Application Configuration & API URL Helper
 * Reads VITE_API_URL from environment variables for production deployments.
 * Eliminates any hardcoded localhost or port references.
 */

const rawApiUrl = import.meta.env.VITE_API_URL;
export const API_BASE_URL: string = rawApiUrl ? rawApiUrl.replace(/\/+$/, '') : '';

/**
 * Build absolute API URL if VITE_API_URL is configured,
 * otherwise return relative /api path for same-domain or reverse proxy.
 */
export function getApiUrl(endpoint: string): string {
  const clean = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  if (API_BASE_URL) {
    return `${API_BASE_URL}${clean}`;
  }
  return clean.startsWith('/api') ? clean : `/api${clean}`;
}

