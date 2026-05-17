/**
 * API client for property endpoints.
 *
 * No /api prefix — calls backend paths directly.
 * See README.md for the rationale.
 */

/**
 * List properties with latest-snapshot rollup.
 * @param {Object} params
 * @param {number} [params.suburb]      - filter by suburb_id
 * @param {string} [params.category]    - "forsale" | "forrent" | "recentlysold"
 * @param {string} [params.search]      - address ILIKE filter
 * @param {string} [params.sort]        - "observed_at_desc" | "price_desc" | "price_asc"
 * @param {number} [params.limit=50]
 * @param {number} [params.offset=0]
 * @returns {Promise<Array>} list of PropertyWithRollup objects
 */
export async function listProperties({ suburb, category, search, sort, limit = 50, offset = 0 } = {}) {
  const qs = new URLSearchParams()
  if (suburb != null) qs.set('suburb', suburb)
  if (category != null && category !== '') qs.set('category', category)
  if (search != null && search !== '') qs.set('search', search)
  if (sort != null) qs.set('sort', sort)
  qs.set('limit', limit)
  qs.set('offset', offset)

  const res = await fetch(`/properties?${qs}`)
  if (!res.ok) {
    throw new Error(`listProperties failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * Fetch a single property by id, including all listing campaigns with
 * latest-snapshot summaries.
 * @param {number|string} id
 * @returns {Promise<Object>} PropertyDetail DTO { property, listings }
 */
export async function getProperty(id) {
  const res = await fetch(`/properties/${id}`)
  if (!res.ok) {
    throw new Error(`getProperty(${id}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
