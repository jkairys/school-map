/**
 * DeltaGrid — 3×2 grid showing new / changed snapshot counts per category.
 *
 * Rows: New, Changed
 * Columns: For sale, For rent, Sold
 *
 * Props:
 *   deltas  {Object}  - SuburbSummary.deltas shape:
 *     { forsale: { new, changed }, forrent: { new, changed }, recentlysold: { new, changed } }
 */

const COLUMNS = [
  { key: 'forsale', label: 'For sale' },
  { key: 'forrent', label: 'For rent' },
  { key: 'recentlysold', label: 'Sold' },
]

const ROWS = [
  { key: 'new', label: 'New' },
  { key: 'changed', label: 'Changed' },
]

function Cell({ value }) {
  return (
    <td className="px-4 py-2.5 text-center tabular-nums text-neutral-800 font-medium">
      {value ?? 0}
    </td>
  )
}

export default function DeltaGrid({ deltas }) {
  const d = deltas ?? {}

  return (
    <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-neutral-100">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Last scrape deltas
        </h3>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-neutral-50 border-b border-neutral-100">
              <th className="px-4 py-2 text-left text-xs font-medium text-neutral-400 w-24" />
              {COLUMNS.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-2 text-center text-xs font-medium text-neutral-500"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100">
            {ROWS.map((row) => (
              <tr key={row.key} className="hover:bg-neutral-50">
                <td className="px-4 py-2.5 text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                  {row.label}
                </td>
                {COLUMNS.map((col) => (
                  <Cell
                    key={col.key}
                    value={(d[col.key] ?? {})[row.key] ?? 0}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
