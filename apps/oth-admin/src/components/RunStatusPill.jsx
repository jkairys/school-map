/**
 * RunStatusPill — small coloured pill rendering a scrape_run status.
 *
 * Status → colour mapping:
 *   running   → blue
 *   succeeded → green
 *   partial   → amber
 *   failed    → red
 *   (no run)  → neutral grey
 *
 * Props:
 *   status  {string|null}  - one of running | succeeded | partial | failed | null
 */
const STATUS_STYLES = {
  running: 'bg-blue-100 text-blue-700 border-blue-200',
  succeeded: 'bg-green-100 text-green-700 border-green-200',
  partial: 'bg-amber-100 text-amber-700 border-amber-200',
  failed: 'bg-red-100 text-red-700 border-red-200',
}

const STATUS_LABELS = {
  running: 'running',
  succeeded: 'succeeded',
  partial: 'partial',
  failed: 'failed',
}

export default function RunStatusPill({ status }) {
  const styles = STATUS_STYLES[status] ?? 'bg-neutral-100 text-neutral-500 border-neutral-200'
  const label = STATUS_LABELS[status] ?? 'no run'

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${styles}`}
    >
      {status === 'running' && (
        <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
      )}
      {label}
    </span>
  )
}
