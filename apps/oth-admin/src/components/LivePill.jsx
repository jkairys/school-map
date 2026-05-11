/**
 * LivePill — a small green indicator shown while adaptive polling is active.
 *
 * Props: none (render it or don't)
 */
export default function LivePill() {
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-700 border border-green-200">
      <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
      Live
    </span>
  )
}
