/**
 * StatCard — a labelled number tile used in summary grids.
 *
 * Props:
 *   label  {string}           - metric name shown above the value
 *   value  {string|number}    - the primary number / value
 *   sub    {string}           - optional small subscript beneath the value
 */
export default function StatCard({ label, value, sub }) {
  return (
    <div className="bg-white rounded-lg border border-neutral-200 p-4 flex flex-col gap-1">
      <span className="text-xs font-medium text-neutral-500 uppercase tracking-wide">
        {label}
      </span>
      <span className="text-2xl font-semibold text-neutral-900 tabular-nums">
        {value}
      </span>
      {sub && (
        <span className="text-xs text-neutral-400">{sub}</span>
      )}
    </div>
  )
}
