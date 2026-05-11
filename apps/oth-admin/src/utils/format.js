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
