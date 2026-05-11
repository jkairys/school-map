/**
 * API client for suburb endpoints.
 *
 * No /api prefix — calls backend paths directly.
 * See README.md for the rationale.
 */

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
