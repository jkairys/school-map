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
 * Fetch a single area by id.
 * @param {number|string} id
 * @returns {Promise<Object>} ScrapeListRead DTO (includes suburbs array)
 */
export async function getArea(id) {
  const res = await fetch(`/scrape-lists/${id}`)
  if (!res.ok) {
    throw new Error(`getArea(${id}) failed: ${res.status} ${res.statusText}`)
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

/**
 * Update an area via PUT.
 * @param {number|string} id
 * @param {Object} body - ScrapeListUpdate shape
 * @returns {Promise<Object>} updated ScrapeListRead DTO
 */
export async function updateArea(id, body) {
  const res = await fetch(`/scrape-lists/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`updateArea(${id}) failed: ${res.status} ${detail}`)
  }
  return res.json()
}

/**
 * Delete an area.
 * @param {number|string} id
 * @returns {Promise<void>}
 */
export async function deleteArea(id) {
  const res = await fetch(`/scrape-lists/${id}`, { method: 'DELETE' })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`deleteArea(${id}) failed: ${res.status} ${detail}`)
  }
}

/**
 * Trigger a run for an area.
 * @param {number|string} id
 * @param {Object} [body={}] - optional RunBody (suburb_ids, categories, trigger_source)
 * @returns {Promise<Object>} ScrapeListRunResult { list_id, run_id, job_ids, count }
 */
export async function runArea(id, body = {}) {
  const res = await fetch(`/scrape-lists/${id}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`runArea(${id}) failed: ${res.status} ${detail}`)
  }
  return res.json()
}
