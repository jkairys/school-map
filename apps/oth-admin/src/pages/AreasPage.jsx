import { useEffect, useReducer, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { RefreshCw, MapPin, AlertCircle } from 'lucide-react'
import { listAreas, getAreaSummary } from '../api/areas.js'
import RunStatusPill from '../components/RunStatusPill.jsx'
import CategorySplit from '../components/CategorySplit.jsx'
import { timeAgo } from '../utils/time.js'

// ---------------------------------------------------------------------------
// useFetch hook — avoids synchronous setState in effects.
// Uses a counter to re-trigger the effect when refresh is requested.
// ---------------------------------------------------------------------------
function fetchReducer(_state, action) {
  switch (action.type) {
    case 'START':  return { data: null, error: null, loading: true }
    case 'OK':     return { data: action.data, error: null, loading: false }
    case 'ERR':    return { data: null, error: action.error, loading: false }
    default:       return _state
  }
}

function useFetch(fetcher) {
  const [state, dispatch] = useReducer(fetchReducer, { data: null, error: null, loading: true })
  const countRef = useRef(0)
  const [tick, setTick] = useReducer((n) => n + 1, 0)

  const refresh = useCallback(() => setTick(), [])

  useEffect(() => {
    const seq = ++countRef.current
    let cancelled = false
    dispatch({ type: 'START' })
    fetcher()
      .then((data) => {
        if (!cancelled && seq === countRef.current) dispatch({ type: 'OK', data })
      })
      .catch((err) => {
        if (!cancelled && seq === countRef.current) dispatch({ type: 'ERR', error: err.message })
      })
    return () => { cancelled = true }
  }, [fetcher, tick])

  return { ...state, refresh }
}

// ---------------------------------------------------------------------------
// AreaCard
// ---------------------------------------------------------------------------
function AreaCard({ area }) {
  const fetchSummary = useCallback(() => getAreaSummary(area.id), [area.id])
  const { data: summary, error, loading } = useFetch(fetchSummary)

  const latestRun = summary?.latest_run ?? null
  const triggeredAt = latestRun?.triggered_at ?? null

  return (
    <Link
      to={`/areas/${area.id}`}
      className="block bg-white rounded-lg border border-neutral-200 p-5 hover:border-neutral-300 hover:shadow-sm transition-all group"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <h2 className="font-semibold text-neutral-900 text-sm truncate group-hover:text-blue-700 transition-colors">
            {area.name}
          </h2>
          {area.description && (
            <p className="text-xs text-neutral-500 mt-0.5 line-clamp-2">{area.description}</p>
          )}
        </div>
        {loading ? (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-neutral-100 text-neutral-400 border border-neutral-200 shrink-0">
            …
          </span>
        ) : error ? (
          <span className="inline-flex items-center gap-1 text-xs text-red-500 shrink-0">
            <AlertCircle size={12} />
            error
          </span>
        ) : (
          <RunStatusPill status={latestRun?.status ?? null} />
        )}
      </div>

      {/* Metrics */}
      {!loading && !error && summary && (
        <div className="space-y-2">
          <div className="flex items-center gap-4 text-xs text-neutral-500">
            <span className="flex items-center gap-1">
              <MapPin size={11} className="text-neutral-400" />
              <span className="font-medium text-neutral-700 tabular-nums">
                {summary.suburb_count}
              </span>
              {' '}suburb{summary.suburb_count !== 1 ? 's' : ''}
            </span>
            <span>
              <span className="font-medium text-neutral-700 tabular-nums">
                {summary.properties_observed.toLocaleString()}
              </span>
              {' '}properties
            </span>
          </div>

          <CategorySplit
            forsale={summary.active_listings?.forsale ?? 0}
            forrent={summary.active_listings?.forrent ?? 0}
            recentlysold={summary.active_listings?.recentlysold ?? 0}
          />

          <p className="text-xs text-neutral-400">
            Last triggered: <span className="text-neutral-500">{timeAgo(triggeredAt)}</span>
          </p>
        </div>
      )}

      {loading && (
        <div className="space-y-2 animate-pulse">
          <div className="h-3 bg-neutral-100 rounded w-3/4" />
          <div className="h-3 bg-neutral-100 rounded w-1/2" />
        </div>
      )}

      {error && !loading && (
        <p className="text-xs text-red-400 mt-2">Could not load summary: {error}</p>
      )}
    </Link>
  )
}

// ---------------------------------------------------------------------------
// AreasPage
// ---------------------------------------------------------------------------
export default function AreasPage() {
  const fetchAreas = useCallback(() => listAreas(), [])
  const { data: areas, error, loading, refresh } = useFetch(fetchAreas)

  return (
    <div>
      {/* Page header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-lg font-semibold text-neutral-900">Areas</h1>
          {areas && !loading && (
            <p className="text-sm text-neutral-500 mt-0.5">
              {areas.length} area{areas.length !== 1 ? 's' : ''} configured
            </p>
          )}
        </div>
        <button
          onClick={refresh}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 hover:border-neutral-300 transition-colors disabled:opacity-50"
          title="Refresh areas"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 mb-4">
          <AlertCircle size={16} className="shrink-0" />
          <span>Failed to load areas: {error}</span>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !error && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="bg-white rounded-lg border border-neutral-200 p-5 animate-pulse">
              <div className="h-4 bg-neutral-100 rounded w-2/3 mb-3" />
              <div className="h-3 bg-neutral-100 rounded w-1/2 mb-2" />
              <div className="h-3 bg-neutral-100 rounded w-3/4" />
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && areas?.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-neutral-400">
          <MapPin size={40} className="mb-3 opacity-30" />
          <p className="text-sm font-medium text-neutral-500">No areas configured</p>
          <p className="text-xs mt-1">Create an area via the CLI to get started.</p>
        </div>
      )}

      {/* Area cards grid */}
      {!loading && !error && areas?.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {areas.map((area) => (
            <AreaCard key={area.id} area={area} />
          ))}
        </div>
      )}
    </div>
  )
}
