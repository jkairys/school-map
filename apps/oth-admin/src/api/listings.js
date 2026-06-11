/**
 * API client for listing endpoints.
 *
 * No /api prefix — calls backend paths directly.
 * In dev, Vite proxies these paths to http://localhost:8000.
 * In prod, the SPA is served from the same origin as FastAPI.
 */

/**
 * Fetch a single listing by id (includes latest_snapshot).
 * @param {number|string} id
 * @returns {Promise<Object>} ListingDetail DTO
 */
export async function getListing(id) {
  const res = await fetch(`/listings/${id}`)
  if (!res.ok) {
    throw new Error(`getListing(${id}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * Fetch all snapshots for a listing, ordered by observed_at ASC.
 * @param {number|string} listingId
 * @param {Object} [params]
 * @param {number} [params.limit=100]
 * @param {number} [params.offset=0]
 * @returns {Promise<Array>} list of SnapshotRead objects
 */
export async function listSnapshots(listingId, { limit = 100, offset = 0 } = {}) {
  const qs = new URLSearchParams()
  qs.set('limit', limit)
  qs.set('offset', offset)

  const res = await fetch(`/listings/${listingId}/snapshots?${qs}`)
  if (!res.ok) {
    throw new Error(`listSnapshots(${listingId}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
