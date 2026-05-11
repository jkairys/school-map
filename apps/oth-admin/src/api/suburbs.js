/**
 * API client for suburb endpoints.
 *
 * No /api prefix — calls backend paths directly.
 * See README.md for the rationale.
 */

/**
 * Fetch autocomplete candidates for a suburb query.
 * @param {string} q - Search string. Empty/whitespace returns [] without a network call.
 * @returns {Promise<Array>} Match[] from OTH autocomplete
 */
export async function autocomplete(q) {
  const cleaned = (q ?? '').trim()
  if (!cleaned) return []

  const res = await fetch(`/suburbs/autocomplete?q=${encodeURIComponent(cleaned)}`)
  if (!res.ok) {
    throw new Error(`autocomplete failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * Fetch a single suburb by id.
 * @param {number|string} id
 * @returns {Promise<Object>} Suburb DTO
 */
export async function getSuburb(id) {
  const res = await fetch(`/suburbs/${id}`)
  if (!res.ok) {
    throw new Error(`getSuburb(${id}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

/**
 * Fetch the full suburb summary DTO for a single suburb.
 * @param {number|string} id
 * @returns {Promise<Object>} SuburbSummary DTO
 */
export async function getSuburbSummary(id) {
  const res = await fetch(`/suburbs/${id}/summary`)
  if (!res.ok) {
    throw new Error(`getSuburbSummary(${id}) failed: ${res.status} ${res.statusText}`)
  }
  return res.json()
}
