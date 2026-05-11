/**
 * API client for scrape-run endpoints.
 *
 * No /api prefix — calls backend paths directly.
 * See README.md for the rationale.
 */

/**
 * List runs, optionally filtered.
 * @param {Object} params
 * @param {number} [params.list_id]
 * @param {string} [params.status]
 * @param {number} [params.limit=50]
 * @param {number} [params.offset=0]
 * @returns {Promise<Array>} list of ScrapeRunRead objects
 */
export async function listRuns({ list_id, status, limit = 50, offset = 0 } = {}) {
  const qs = new URLSearchParams()
  if (list_id != null) qs.set('list_id', list_id)
  if (status != null) qs.set('status', status)
  qs.set('limit', limit)
  qs.set('offset', offset)

  const res = await fetch(`/scrape-runs?${qs}`)
  if (!res.ok) {
    throw new Error(`listRuns failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * Fetch a single run with per-status job counts rollup.
 * @param {number|string} id
 * @returns {Promise<Object>} ScrapeRunDetail { ...run, job_counts }
 */
export async function getRun(id) {
  const res = await fetch(`/scrape-runs/${id}`)
  if (!res.ok) {
    throw new Error(`getRun(${id}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
