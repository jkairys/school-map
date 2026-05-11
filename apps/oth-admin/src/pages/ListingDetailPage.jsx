/**
 * ListingDetailPage — /listings/:id
 *
 * Shows:
 *  1. Header: category pill + status pill + property link (→ /properties/:id)
 *  2. Metadata strip: agent, agency, dates, closure_reason, oth_listing_id, sale_date
 *  3. Price chart: Recharts LineChart over snapshot history (null-price snapshots excluded)
 *  4. Snapshot table: all snapshots with changed_fields chips
 *  5. Raw payload viewer: latest snapshot's raw_payload, collapsed by default
 */
import { useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw } from 'lucide-react'

import { getListing, listSnapshots } from '../api/listings.js'
import useAdaptivePoll from '../hooks/useAdaptivePoll.js'
import PriceChart from '../components/PriceChart.jsx'
import RawPayloadViewer from '../components/RawPayloadViewer.jsx'
import { formatPrice } from '../utils/format.js'
import { timeAgo } from '../utils/time.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDate(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
}

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

/**
 * Render a list of changed_fields as small badge chips.
 */
function ChangedFieldChips({ fields }) {
  if (!fields || fields.length === 0) {
    return <span className="text-neutral-400 text-xs">—</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {fields.map((f, i) => (
        <span
          key={i}
          className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono bg-neutral-100 text-neutral-600 border border-neutral-200"
        >
          {f}
        </span>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ListingDetailPage
// ---------------------------------------------------------------------------

export default function ListingDetailPage() {
  const { id } = useParams()

  // Listing detail (includes latest_snapshot for raw payload)
  const listingFetcher = useCallback(() => getListing(id), [id])
  const {
    data: listing,
    error: listingError,
    isLoading: listingLoading,
    refetch: refetchListing,
  } = useAdaptivePoll(listingFetcher, { shouldPoll: () => false })

  // Snapshot history
  const snapshotsFetcher = useCallback(() => listSnapshots(id), [id])
  const {
    data: snapshots,
    error: snapshotsError,
    isLoading: snapshotsLoading,
    refetch: refetchSnapshots,
  } = useAdaptivePoll(snapshotsFetcher, { shouldPoll: () => false })

  const snapshotList = snapshots ?? []
  const latestSnapshot = listing?.latest_snapshot ?? null

  function handleRefresh() {
    refetchListing()
    refetchSnapshots()
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (listingLoading && !listing) {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <Link to="/areas" className="p-1 rounded text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100">
            <ArrowLeft size={16} />
          </Link>
          <div className="h-6 w-64 bg-neutral-200 rounded animate-pulse" />
        </div>
        <div className="h-20 bg-neutral-200 rounded-lg animate-pulse" />
        <div className="h-64 bg-neutral-200 rounded-lg animate-pulse" />
      </div>
    )
  }

  if (listingError && !listing) {
    return (
      <div className="flex flex-col gap-4">
        <Link to="/areas" className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800">
          <ArrowLeft size={14} />
          Back
        </Link>
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700">
          Failed to load listing: {listingError}
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Full render
  // ---------------------------------------------------------------------------

  const propertyId = listing?.property_id
  const category = listing?.category
  const closedAt = listing?.closed_at
  const isLoading = listingLoading || snapshotsLoading

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <Link
            to={propertyId ? `/properties/${propertyId}` : '/areas'}
            className="mt-0.5 p-1 rounded text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100"
            title="Back to property"
          >
            <ArrowLeft size={16} />
          </Link>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <CategoryPill category={category} />
              <StatusPill closedAt={closedAt} />
            </div>
            {propertyId && (
              <Link
                to={`/properties/${propertyId}`}
                className="mt-1 block text-base font-medium text-blue-600 hover:underline"
              >
                Property #{propertyId}
              </Link>
            )}
            <p className="text-xs text-neutral-500 mt-0.5">Listing #{listing?.id}</p>
          </div>
        </div>
        <button
          onClick={handleRefresh}
          disabled={isLoading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded border border-neutral-200 text-sm font-medium text-neutral-600 hover:bg-neutral-50 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw size={13} className={isLoading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Metadata strip */}
      <div className="bg-white rounded-lg border border-neutral-200 px-4 py-3 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 text-sm">
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Agent</p>
          <p className="text-neutral-800">{listing?.agent_name ?? '—'}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Agency</p>
          <p className="text-neutral-800">{listing?.agency_name ?? '—'}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">First seen</p>
          <p className="text-neutral-800">{fmtDate(listing?.first_seen_at)}</p>
          <p className="text-neutral-400 text-xs">{timeAgo(listing?.first_seen_at)}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Last seen</p>
          <p className="text-neutral-800">{fmtDate(listing?.last_seen_at)}</p>
          <p className="text-neutral-400 text-xs">{timeAgo(listing?.last_seen_at)}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Closed at</p>
          <p className="text-neutral-800">{fmtDate(closedAt)}</p>
        </div>
        {listing?.closure_reason && (
          <div>
            <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Closure reason</p>
            <p className="text-neutral-800">{listing.closure_reason}</p>
          </div>
        )}
        <div>
          <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">OTH listing ID</p>
          <p className="font-mono text-xs text-neutral-700 break-all">{listing?.oth_listing_id ?? '—'}</p>
        </div>
        {listing?.sale_date && (
          <div>
            <p className="text-xs font-medium text-neutral-400 uppercase tracking-wide mb-0.5">Sale date</p>
            <p className="text-neutral-800">{fmtDate(listing.sale_date)}</p>
          </div>
        )}
      </div>

      {/* Price chart */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Price history
        </h2>
        {snapshotsLoading && snapshotList.length === 0 ? (
          <div className="h-64 bg-neutral-200 rounded-lg animate-pulse" />
        ) : (
          <div className="bg-white rounded-lg border border-neutral-200 p-4">
            <PriceChart snapshots={snapshotList} />
          </div>
        )}
      </div>

      {/* Snapshot table */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Snapshots ({snapshotList.length})
        </h2>
        {snapshotsError && (
          <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-3 text-sm text-red-700 mb-3">
            Failed to load snapshots: {snapshotsError}
          </div>
        )}
        {snapshotList.length === 0 && !snapshotsLoading ? (
          <p className="text-sm text-neutral-400">No snapshots recorded.</p>
        ) : (
          <div className="bg-white rounded-lg border border-neutral-200 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200 bg-neutral-50">
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide whitespace-nowrap">
                    Observed at
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide whitespace-nowrap">
                    Price
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                    Beds
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                    Baths
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                    Park
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide whitespace-nowrap">
                    Land (m²)
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide whitespace-nowrap">
                    Type
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide">
                    Status
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-semibold text-neutral-500 uppercase tracking-wide whitespace-nowrap">
                    Changed fields
                  </th>
                </tr>
              </thead>
              <tbody>
                {snapshotList.map((snap) => (
                  <tr key={snap.id} className="border-b border-neutral-100 hover:bg-neutral-50">
                    <td className="px-4 py-2 whitespace-nowrap">
                      <p className="text-neutral-800">{fmtDate(snap.observed_at)}</p>
                      <p className="text-xs text-neutral-400">{timeAgo(snap.observed_at)}</p>
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap font-medium text-neutral-900 tabular-nums">
                      {formatPrice(snap.price)}
                    </td>
                    <td className="px-4 py-2 text-neutral-700 tabular-nums">
                      {snap.bedrooms ?? '—'}
                    </td>
                    <td className="px-4 py-2 text-neutral-700 tabular-nums">
                      {snap.bathrooms ?? '—'}
                    </td>
                    <td className="px-4 py-2 text-neutral-700 tabular-nums">
                      {snap.parking ?? '—'}
                    </td>
                    <td className="px-4 py-2 text-neutral-700 tabular-nums">
                      {snap.land_size_sqm ?? '—'}
                    </td>
                    <td className="px-4 py-2 text-neutral-700">
                      {snap.property_type ?? '—'}
                    </td>
                    <td className="px-4 py-2">
                      {snap.status ? (
                        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs bg-neutral-100 border border-neutral-200 text-neutral-600">
                          {snap.status}
                        </span>
                      ) : (
                        <span className="text-neutral-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      <ChangedFieldChips fields={snap.changed_fields} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Raw payload viewer (latest snapshot) */}
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
          Debug
        </h2>
        <RawPayloadViewer payload={latestSnapshot?.raw_payload ?? null} />
      </div>
    </div>
  )
}
