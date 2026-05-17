import { useEffect, useReducer, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import { listProperties } from '../api/properties.js'
import { formatDate, formatPrice } from '../utils/format.js'
import { timeAgo } from '../utils/time.js'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 50

const SORT_OPTIONS = [
  { value: 'observed_at_desc', label: 'Most recent' },
  { value: 'price_desc', label: 'Highest price' },
  { value: 'price_asc', label: 'Lowest price' },
]

const CATEGORY_LABELS = {
  forsale: 'For sale',
  forrent: 'For rent',
  recentlysold: 'Sold',
}

const CATEGORY_STYLES = {
  forsale: 'bg-sky-50 text-sky-700 border border-sky-200',
  forrent: 'bg-violet-50 text-violet-700 border border-violet-200',
  recentlysold: 'bg-teal-50 text-teal-700 border border-teal-200',
}

// ---------------------------------------------------------------------------
// Reducer
// State is kept in a single object so effects can dispatch one action.
// ---------------------------------------------------------------------------

function reducer(state, action) {
  switch (action.type) {
    case 'SYNC_SEARCH':
      return { ...state, localSearch: action.value }
    case 'LOADING':
      return { ...state, isLoading: true, error: null }
    case 'OK':
      return { ...state, rows: action.rows, isLoading: false, error: null }
    case 'ERR':
      return { ...state, isLoading: false, error: action.error }
    default:
      return state
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function CategoryPill({ category }) {
  const label = CATEGORY_LABELS[category] ?? category
  const styles = CATEGORY_STYLES[category] ?? 'bg-neutral-100 text-neutral-600 border border-neutral-200'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${styles}`}>
      {label}
    </span>
  )
}

function StatusPill({ latestStatus }) {
  const isOpen = latestStatus !== 'closed'
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${
        isOpen
          ? 'bg-green-50 text-green-700 border-green-200'
          : 'bg-neutral-100 text-neutral-500 border-neutral-200'
      }`}
    >
      {isOpen ? 'open' : 'closed'}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * PropertyTable — paginated, sortable, searchable property table for a suburb.
 *
 * Props:
 *   suburbId       {number}    - suburb to filter by
 *   search         {string}    - committed search string (controlled via URL params)
 *   sort           {string}    - current sort key (controlled via URL params)
 *   page           {number}    - current page (1-indexed, controlled via URL params)
 *   onPageChange   {Function}  - called with new page number
 *   onSortChange   {Function}  - called with new sort value
 *   onSearchChange {Function}  - called with new debounced search string
 */
export default function PropertyTable({
  suburbId,
  search,
  sort,
  page,
  onPageChange,
  onSortChange,
  onSearchChange,
}) {
  const [state, dispatch] = useReducer(reducer, {
    rows: [],
    isLoading: false,
    error: null,
    localSearch: search ?? '',
  })

  const debounceRef = useRef(null)

  // When the committed search prop changes externally (e.g. browser back),
  // sync it into localSearch so the input reflects the URL.
  // useReducer dispatch is allowed inside effects (unlike useState setters).
  useEffect(() => {
    dispatch({ type: 'SYNC_SEARCH', value: search ?? '' })
  }, [search])

  // Debounce: update local input immediately, flush to parent after 250ms.
  function handleSearchInput(e) {
    const val = e.target.value
    dispatch({ type: 'SYNC_SEARCH', value: val })
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      onSearchChange(val)
    }, 250)
  }

  // Fetch on suburbId / committed search / sort / page changes.
  useEffect(() => {
    if (suburbId == null) return

    let cancelled = false
    dispatch({ type: 'LOADING' })

    const offset = ((page ?? 1) - 1) * PAGE_SIZE

    listProperties({
      suburb: suburbId,
      search: search || undefined,
      sort: sort || 'observed_at_desc',
      limit: PAGE_SIZE,
      offset,
    })
      .then((data) => {
        if (cancelled) return
        dispatch({ type: 'OK', rows: data })
      })
      .catch((err) => {
        if (cancelled) return
        dispatch({ type: 'ERR', error: err.message ?? String(err) })
      })

    return () => { cancelled = true }
  }, [suburbId, search, sort, page])

  const { rows, isLoading, error, localSearch } = state
  const currentPage = page ?? 1
  const hasNextPage = rows.length === PAGE_SIZE

  return (
    <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
      {/* Toolbar */}
      <div className="px-4 py-3 border-b border-neutral-100 flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="text"
            value={localSearch}
            onChange={handleSearchInput}
            placeholder="Search address…"
            className="w-full pl-8 pr-3 py-1.5 text-sm border border-neutral-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        <select
          value={sort ?? 'observed_at_desc'}
          onChange={(e) => onSortChange(e.target.value)}
          className="px-3 py-1.5 text-sm border border-neutral-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        {error && (
          <div className="px-4 py-3 text-sm text-red-700 bg-red-50 border-b border-red-100">
            {error}
          </div>
        )}
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-neutral-50 border-b border-neutral-100">
              <th className="px-4 py-2.5 text-left text-xs font-medium text-neutral-500">Address</th>
              <th className="px-4 py-2.5 text-left text-xs font-medium text-neutral-500">Category</th>
              <th className="px-4 py-2.5 text-right text-xs font-medium text-neutral-500">Latest price</th>
              <th className="px-4 py-2.5 text-left text-xs font-medium text-neutral-500">Last observed / sold</th>
              <th className="px-4 py-2.5 text-left text-xs font-medium text-neutral-500">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-neutral-100">
            {isLoading && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-neutral-400">
                  Loading…
                </td>
              </tr>
            )}
            {!isLoading && !error && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-sm text-neutral-400">
                  No properties found.
                </td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.id} className={`hover:bg-neutral-50 ${isLoading ? 'opacity-60' : ''}`}>
                <td className="px-4 py-2.5">
                  <Link
                    to={`/properties/${row.id}`}
                    className="text-blue-600 hover:text-blue-800 hover:underline font-medium"
                  >
                    {row.formatted_address}
                  </Link>
                </td>
                <td className="px-4 py-2.5">
                  {row.latest_category ? (
                    <CategoryPill category={row.latest_category} />
                  ) : (
                    <span className="text-neutral-400">—</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-neutral-800">
                  {formatPrice(row.latest_price)}
                </td>
                <td className="px-4 py-2.5 text-neutral-500">
                  {row.latest_category === 'recentlysold' && row.latest_sale_date
                    ? `sold ${formatDate(row.latest_sale_date)}`
                    : row.latest_observed_at
                      ? timeAgo(row.latest_observed_at)
                      : '—'}
                </td>
                <td className="px-4 py-2.5">
                  <StatusPill latestStatus={row.latest_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="px-4 py-3 border-t border-neutral-100 flex items-center justify-between text-sm text-neutral-600">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1 || isLoading}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded border border-neutral-200 text-xs font-medium hover:bg-neutral-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <ChevronLeft size={13} />
          Prev
        </button>
        <span className="text-xs text-neutral-500">Page {currentPage}</span>
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!hasNextPage || isLoading}
          className="inline-flex items-center gap-1 px-3 py-1.5 rounded border border-neutral-200 text-xs font-medium hover:bg-neutral-50 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Next
          <ChevronRight size={13} />
        </button>
      </div>
    </div>
  )
}
