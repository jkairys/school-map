/**
 * API client for area (scrape_list) endpoints.
 *
 * API path choice: NO /api prefix.
 * The SPA calls backend paths directly (e.g. /scrape-lists, /jobs).
 * In dev, Vite proxies these paths to http://localhost:8000.
 * In prod, the SPA is served from the same origin as FastAPI, so no CORS
 * or prefix changes are needed. This is the simpler approach — see README.md.
 */

/**
 * Fetch all areas (scrape_lists) from the list endpoint.
 * @returns {Promise<Array>} list of ScrapeListSummary objects
 */
export async function listAreas() {
  const res = await fetch('/scrape-lists')
  if (!res.ok) {
    throw new Error(`listAreas failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * Fetch the full area summary DTO for a single area.
 * @param {number|string} id
 * @returns {Promise<Object>} AreaSummary DTO
 */
export async function getAreaSummary(id) {
  const res = await fetch(`/scrape-lists/${id}/summary`)
  if (!res.ok) {
    throw new Error(`getAreaSummary(${id}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
