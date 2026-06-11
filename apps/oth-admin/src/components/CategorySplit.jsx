/**
 * CategorySplit — three small badges showing active listing counts per category.
 *
 * Props:
 *   forsale       {number}  - for-sale count
 *   forrent       {number}  - for-rent count
 *   recentlysold  {number}  - sold count
 */
export default function CategorySplit({ forsale = 0, forrent = 0, recentlysold = 0 }) {
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-sky-50 text-sky-700 border border-sky-200">
        <span className="font-semibold tabular-nums">{forsale}</span>
        <span className="text-sky-500">for sale</span>
      </span>
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-violet-50 text-violet-700 border border-violet-200">
        <span className="font-semibold tabular-nums">{forrent}</span>
        <span className="text-violet-500">for rent</span>
      </span>
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200">
        <span className="font-semibold tabular-nums">{recentlysold}</span>
        <span className="text-teal-500">sold</span>
      </span>
    </div>
  )
}
