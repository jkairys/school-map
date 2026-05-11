/**
 * PropertyDetailPage — /properties/:id
 *
 * Shows:
 *  1. Header: formatted_address + postcode/suburb/state badges + "Back" link
 *  2. Metadata strip: postcode, suburb_id link, first_seen_at, oth_property_id
 *  3. Listings list: every listing campaign, sorted by first_seen_at DESC
 *     - Category pill, open/closed status, dates, latest snapshot summary
 *     - Each listing card links to /listings/:id
 *  4. Re-listing notice when listings.length > 1
 */
import { useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'

import { getProperty } from '../api/properties.js'
import useAdaptivePoll from '../hooks/useAdaptivePoll.js'
import { formatPrice } from '../utils/format.js'
import { timeAgo } from '../utils/time.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format a Date-like ISO string as an absolute date string, e.g. "7 Jan 2025".
 */
function fmtDate(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

/**
 * Category pill colours.
 */
const CATEGORY_STYLES = {
  forsale: 'bg-blue-100 text-blue-700 border-blue-200',
  forrent: 'bg-purple-100 text-purple-700 border-purple-200',
  recentlysold: 'bg-green-100 text-green-700 border-green-200',
}

const CATEGORY_LABELS = {
  forsale: 'For sale',
  forrent: 'For rent',
  recentlysold: 'Recently sold',
}

function CategoryPill({ category }) {
  const style = CATEGORY_STYLES[category] ?? 'bg-neutral-100 text-neutral-600 border-neutral-200'
  const label = CATEGORY_LABELS[category] ?? category
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${style}`}>
      {label}
    </span>
  )
}

function StatusPill({ closedAt }) {
  if (!closedAt) {
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-emerald-100 text-emerald-700 border-emerald-200">
        Open
      </span>
    )
  }
  return (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border bg-neutral-100 text-neutral-500 border-neutral-200">
      Closed
    </span>
  )
}

// ---------------------------------------------------------------------------
// ListingCard
// ---------------------------------------------------------------------------

function ListingCard({ listing }) {
  const snap = listing.latest_snapshot

  return (
    <Link
      to={`/listings/${listing.id}`}
      className="block bg-white rounded-lg border border-neutral-200 p-4 hover:border-blue-300 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3 flex-wrap">
        {/* Left: category + status */}
        <div className="flex items-center gap-2 flex-wrap">
          <CategoryPill category={listing.category} />
          <StatusPill closedAt={listing.closed_at} />
          {listing.closure_reason && (
            <span className="text-xs text-neutral-500">({listing.closure_reason})</span>
          )}
        </div>

        {/* Right: latest price */}
        {snap && snap.price != null && (
          <span className="text-base font-semibold text-neutral-900 tabular-nums">
            {formatPrice(snap.price)}
          </span>
        )}
      </div>

      {/* Dates strip */}
      <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
        <div>
          <p className="text-neutral-400 uppercase tracking-wide font-medium mb-0.5">First seen</p>
          <p className="text-neutral-700">{fmtDate(listing.first_seen_at)}</p>
          <p className="text-neutral-400">{timeAgo(listing.first_seen_at)}</p>
        </div>
        <div>
          <p className="text-neutral-400 uppercase tracking-wide font-medium mb-0.5">Last seen</p>
          <p className="text-neutral-700">{fmtDate(listing.last_seen_at)}</p>
          <p className="text-neutral-400">{timeAgo(listing.last_seen_at)}</p>
        </div>
        <div>
          <p className="text-neutral-400 uppercase tracking-wide font-medium mb-0.5">Closed</p>
          <p className="text-neutral-700">{fmtDate(listing.closed_at)}</p>
        </div>
      </div>

      {/* Latest snapshot summary */}
      {snap && (
        <div className="mt-3 flex items-center gap-3 text-xs text-neutral-600 flex-wrap">
          {snap.status && (
            <span className="bg-neutral-100 border border-neutral-200 px-2 py-0.5 rounded text-neutral-600">
              {snap.status}
            </span>
          )}
        </div>
      )}
    </Link>
  )
}

// ---------------------------------------------------------------------------
// PropertyDetailPage
// ---------------------------------------------------------------------------

export default function PropertyDetailPage() {
  const { id } = useParams()

  const fetcher = useCallback(() => getProperty(id), [id])
  const { data, error, isLoading, refetch } = useAdaptivePoll(fetcher, {
    shouldPoll: () => false,
  })

  const property = data?.property
  const listings = data?.listings ?? []

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (isLoading && !data) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <Link to="/areas" className="p-1 rounded text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
            <ArrowLeft size={16} />
          </Link>
          <div className="h-6 w-64 bg-neutral-200 rounded animate-pulse" />
        </div>
        <div className="h-20 bg-neutral-200 rounded-lg animate-pulse" />
        <div className="h-32 bg-neutral-200 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="-1" className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800">
          <ArrowLeft size={14} />
          Back
        </Link>
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          Failed to load property: {error}
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Full render
  // ---------------------------------------------------------------------------

  const address = property?.formatted_address ?? '—'
  const postcode = property?.postcode ?? ''
  const suburbId = property?.suburb_id
  const firstSeenAt = property?.first_seen_at
  const othPropertyId = property?.oth_property_id

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <Link
            to={suburbId ? `/suburbs/${suburbId}` : '/areas'}
            className="mt-0.5 p-1 rounded text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100"
            title="Back to suburb"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <h1 className="text-xl font-semibold text-neutral-900">{address}</h1>
            <div className="flex items-center gap-2 mt-1 flex-wrap">
              {postcode && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-neutral-100 text-neutral-600 border border-neutral-200">
                  {postcode}
                </span>
              )}
              {suburbId && (
                <Link
                  to={`/suburbs/${suburbId}`}
                  className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-50 text-blue-600 border border-blue-100 hover:bg-blue-100 hover:text-blue-700"
                >
                  Suburb #{suburbId}
                </Link>
              )}
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

      {/* Metadata strip */}
      <div className="bg-white rounded-lg border border-neutral-200 px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Postcode</p>
          <p className="text-neutral-800">{postcode || '—'}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Suburb</p>
          {suburbId ? (
            <Link to={`/suburbs/${suburbId}`} className="text-blue-600 hover:underline">
              #{suburbId}
            </Link>
          ) : (
            <p className="text-neutral-800">—</p>
          )}
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">First seen</p>
          <p className="text-neutral-800">{fmtDate(firstSeenAt)}</p>
          <p className="text-neutral-400 text-xs">{timeAgo(firstSeenAt)}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">OTH ID</p>
          <p className="font-mono text-xs text-neutral-700 break-all">{othPropertyId ?? '—'}</p>
        </div>
      </div>

      {/* Re-listing notice */}
      {listings.length > 1 && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-3 text-sm text-amber-800">
          This property has been listed {listings.length} times.
        </div>
      )}

      {/* Listings */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Listing campaigns ({listings.length})
        </h2>
        {listings.length === 0 ? (
          <p className="text-sm text-neutral-400">No listings found for this property.</p>
        ) : (
          <div className="flex flex-col gap-3">
            {listings.map((listing) => (
              <ListingCard key={listing.id} listing={listing} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
