import { useCallback } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import { ArrowLeft, RefreshCw, AlertCircle, MapPin } from 'lucide-react'

import { getSuburbSummary } from '../api/suburbs.js'
import useAdaptivePoll from '../hooks/useAdaptivePoll.js'
import LivePill from '../components/LivePill.jsx'
import StatCard from '../components/StatCard.jsx'
import MedianTile from '../components/MedianTile.jsx'
import DeltaGrid from '../components/DeltaGrid.jsx'
import PropertyTable from '../components/PropertyTable.jsx'
import { formatPrice } from '../utils/format.js'
import { timeAgo } from '../utils/time.js'

// ---------------------------------------------------------------------------
// URL param keys and defaults
// ---------------------------------------------------------------------------

const DEFAULT_SORT = 'observed_at_desc'
const DEFAULT_PAGE = 1

// ---------------------------------------------------------------------------
// SuburbDetailPage
// ---------------------------------------------------------------------------

export default function SuburbDetailPage() {
  const { id } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()

  // Read URL state
  const page = parseInt(searchParams.get('page') ?? String(DEFAULT_PAGE), 10) || DEFAULT_PAGE
  const sort = searchParams.get('sort') ?? DEFAULT_SORT
  const q = searchParams.get('q') ?? ''

  // URL state writers — use functional update so we never lose other params
  function setPage(newPage) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (newPage === DEFAULT_PAGE) {
        next.delete('page')
      } else {
        next.set('page', String(newPage))
      }
      return next
    })
  }

  function setSort(newSort) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (newSort === DEFAULT_SORT) {
        next.delete('sort')
      } else {
        next.set('sort', newSort)
      }
      // Reset to page 1 when sort changes
      next.delete('page')
      return next
    })
  }

  function setSearch(newQ) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (!newQ) {
        next.delete('q')
      } else {
        next.set('q', newQ)
      }
      // Reset to page 1 when search changes
      next.delete('page')
      return next
    })
  }

  // Adaptive-poll fetcher
  const fetcher = useCallback(() => getSuburbSummary(id), [id])

  const { data: summary, error, isLoading, isLive, refetch } = useAdaptivePoll(fetcher, {
    shouldPoll: (s) => Boolean(s?.in_flight_run),
  })

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  function renderHeader() {
    const name = summary?.name ?? '—'
    const postcode = summary?.postcode ?? ''
    const state = summary?.state ?? ''

    return (
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <Link
            to="/areas"
            className="mt-0.5 p-1 rounded text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100"
            title="Back to areas"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl font-semibold text-neutral-900">{name}</h1>
              {postcode && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-neutral-100 text-neutral-600 border border-neutral-200">
                  <MapPin size={11} />
                  {postcode} {state}
                </span>
              )}
              {isLive && <LivePill />}
            </div>
          </div>
        </div>
        <button
          onClick={refetch}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-neutral-200 text-sm font-medium text-neutral-600 hover:bg-neutral-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>
    )
  }

  function renderInFlightBanner() {
    if (!summary?.in_flight_run) return null
    const run = summary.in_flight_run
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex items-start gap-2 text-sm text-blue-800">
        <AlertCircle size={16} className="mt-0.5 shrink-0 text-blue-500" />
        <span>
          Run{' '}
          <Link to={`/runs/${run.id}`} className="font-semibold underline hover:text-blue-900">
            #{run.id}
          </Link>{' '}
          in progress (triggered {timeAgo(run.triggered_at)}) — numbers will tick up.
        </span>
      </div>
    )
  }

  function renderLastScraped() {
    const lastRun = summary?.last_completed_run

    if (!lastRun) {
      return (
        <p className="text-sm text-neutral-500">Never scraped.</p>
      )
    }

    return (
      <p className="text-sm text-neutral-600">
        Last scraped {timeAgo(lastRun.completed_at)} in run{' '}
        <Link to={`/runs/${lastRun.id}`} className="text-blue-600 hover:underline font-medium">
          #{lastRun.id}
        </Link>
      </p>
    )
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (isLoading && !summary) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <Link to="/areas" className="p-1 rounded text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
            <ArrowLeft size={16} />
          </Link>
          <div className="h-6 w-48 bg-neutral-200 rounded animate-pulse" />
        </div>
        <div className="h-24 bg-neutral-200 rounded-lg animate-pulse" />
        <div className="h-40 bg-neutral-200 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (error && !summary) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/areas" className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800">
          <ArrowLeft size={14} />
          Back to areas
        </Link>
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          Failed to load suburb: {error}
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Full render
  // ---------------------------------------------------------------------------

  const totals = summary?.totals ?? { forsale: 0, forrent: 0, recentlysold: 0 }
  const medians = summary?.medians ?? {
    sold_30d: { value: null, n: 0 },
    asking: { value: null, n: 0 },
    rent: { value: null, n: 0 },
  }

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      {renderHeader()}

      {/* In-flight banner */}
      {renderInFlightBanner()}

      {/* Last scraped */}
      {summary && renderLastScraped()}

      {/* 3×2 delta grid */}
      <DeltaGrid deltas={summary?.deltas} />

      {/* Totals row */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Total listings
        </h2>
        <div className="grid grid-cols-3 gap-3">
          <StatCard label="For sale" value={totals.forsale} />
          <StatCard label="For rent" value={totals.forrent} />
          <StatCard label="Sold" value={totals.recentlysold} />
        </div>
      </div>

      {/* Medians row */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Price medians
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <MedianTile
            label="Median sold (last 30d)"
            value={medians.sold_30d.n > 0 ? formatPrice(medians.sold_30d.value) : null}
            n={medians.sold_30d.n}
          />
          <MedianTile
            label="Median asking (active)"
            value={medians.asking.n > 0 ? formatPrice(medians.asking.value) : null}
            n={medians.asking.n}
          />
          <MedianTile
            label="Median weekly rent (active)"
            value={medians.rent.n > 0 ? formatPrice(medians.rent.value) : null}
            suffix="/wk"
            n={medians.rent.n}
          />
        </div>
      </div>

      {/* Property table */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Properties
        </h2>
        <PropertyTable
          suburbId={id ? parseInt(id, 10) : undefined}
          search={q}
          sort={sort}
          page={page}
          onPageChange={setPage}
          onSortChange={setSort}
          onSearchChange={setSearch}
        />
      </div>
    </div>
  )
}
