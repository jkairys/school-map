/**
 * Format a datetime string as a human-relative time string, e.g. "2h ago".
 * Returns "never" when the input is null/undefined.
 * No external library — pure inline implementation.
 *
 * @param {string|null} isoString - ISO-8601 date/time string
 * @returns {string}
 */
export function timeAgo(isoString) {
  if (!isoString) return 'never'

  const then = new Date(isoString)
  const diffMs = Date.now() - then.getTime()

  if (diffMs < 0) return 'just now'

  const seconds = Math.floor(diffMs / 1000)
  if (seconds < 60) return `${seconds}s ago`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`

  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`

  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`

  const years = Math.floor(months / 12)
  return `${years}y ago`
}
