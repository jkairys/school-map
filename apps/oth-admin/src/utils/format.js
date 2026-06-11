/**
 * Price / currency formatting helpers.
 */

/**
 * Format a price value as a currency string, e.g. "$895,000".
 * Returns "—" when value is null or undefined.
 *
 * @param {number|null|undefined} value - price in whole dollars (integer)
 * @returns {string}
 */
export function formatPrice(value) {
  if (value == null) return '—'
  return `$${Number(value).toLocaleString('en-AU')}`
}

/**
 * Format a date string (ISO date or datetime) as a compact, human-readable
 * short absolute date, e.g. "Apr 28, 2026".
 * Returns "—" when value is null or undefined.
 *
 * @param {string|null|undefined} value - ISO-8601 date string (YYYY-MM-DD or datetime)
 * @returns {string}
 */
export function formatDate(value) {
  if (value == null) return '—'
  const d = new Date(value)
  if (isNaN(d.getTime())) return '—'
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}
