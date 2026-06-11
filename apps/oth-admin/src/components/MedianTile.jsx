/**
 * MedianTile — displays a labelled median value with an n= subtitle.
 *
 * Props:
 *   label   {string}         - e.g. "Median sold (last 30d)"
 *   value   {string|null}    - pre-formatted currency string, or null/"—" when no data
 *   suffix  {string}         - optional suffix appended after value, e.g. "/wk"
 *   n       {number}         - sample size shown as "(n=X)"
 */
export default function MedianTile({ label, value, suffix, n }) {
  const displayValue = value ?? '—'
  const isBlank = displayValue === '—'

  return (
    <div className="bg-white rounded-lg border border-neutral-200 p-4 flex flex-col gap-1">
      <span className="text-xs font-medium text-neutral-500 uppercase tracking-wide">
        {label}
      </span>
      <span className={`text-2xl font-semibold tabular-nums ${isBlank ? 'text-neutral-400' : 'text-neutral-900'}`}>
        {displayValue}
        {!isBlank && suffix && (
          <span className="text-base font-normal text-neutral-500 ml-0.5">{suffix}</span>
        )}
      </span>
      <span className="text-xs text-neutral-400">n={n ?? 0}</span>
    </div>
  )
}
