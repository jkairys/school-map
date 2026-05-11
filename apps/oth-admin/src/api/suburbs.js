/**
 * API client for suburb endpoints.
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
