/** API base URL and fetch helper for scraper-mcp.
 *
 * Browser (dev):  Vite proxies /api/* → http://127.0.0.1:10998
 * Tauri (prod):   Direct fetch to http://127.0.0.1:10998 (no Vite proxy)
 */

const BACKEND_PORT = 10998;

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export const API_BASE = isTauri()
  ? `http://127.0.0.1:${BACKEND_PORT}`
  : "";

export async function apiFetch<T = unknown>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const resp = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!resp.ok) {
    const text = await resp.text().catch(() => resp.statusText);
    throw new Error(`${resp.status} ${text}`);
  }
  return resp.json() as Promise<T>;
}

export default API_BASE;
