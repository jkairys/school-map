import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  RefreshCw,
  Play,
  Pencil,
  Trash2,
  Plus,
  ChevronDown,
  ChevronRight,
  MapPin,
  AlertCircle,
} from 'lucide-react'

import { getAreaSummary, getArea, updateArea, deleteArea, runArea, addSuburb, removeSuburb } from '../api/areas.js'
import { listRuns } from '../api/runs.js'
import useAdaptivePoll from '../hooks/useAdaptivePoll.js'
import RunStatusPill from '../components/RunStatusPill.jsx'
import CategorySplit from '../components/CategorySplit.jsx'
import LivePill from '../components/LivePill.jsx'
import Modal from '../components/Modal.jsx'
import RunConfirmModal from '../components/RunConfirmModal.jsx'
import SuburbAutocomplete from '../components/SuburbAutocomplete.jsx'
import Toast from '../components/Toast.jsx'
import { timeAgo } from '../utils/time.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(triggeredAt, completedAt) {
  if (!triggeredAt) return '—'
  if (!completedAt) return 'in progress'
  const ms = new Date(completedAt) - new Date(triggeredAt)
  if (ms < 0) return '—'
  const totalSeconds = Math.floor(ms / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`
}

function fmtValue(val) {
  return val == null ? 'Any' : String(val)
}

function fmtPrice(val) {
  if (val == null) return 'Any'
  return `$${Number(val).toLocaleString()}`
}

const PROPERTY_TYPES = ['House', 'Townhouse', 'Unit', 'Apartment', 'Land']

// ---------------------------------------------------------------------------
// JobCountBadge
// ---------------------------------------------------------------------------
function JobCountBadge({ label, count, colour }) {
  if (!count) return null
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${colour}`}>
      <span className="tabular-nums">{count}</span>
      <span className="opacity-75">{label}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// FiltersBlock — read-only display
// ---------------------------------------------------------------------------
function FiltersBlock({ filters }) {
  if (!filters) return null
  const { beds_min, beds_max, property_types, price_min, price_max } = filters

  return (
    <div className="bg-white rounded-lg border border-neutral-200 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 mb-3">
        Filters
      </h3>
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 text-sm">
        <div>
          <dt className="text-xs text-neutral-400">Beds min</dt>
          <dd className="font-medium text-neutral-800">{fmtValue(beds_min)}</dd>
        </div>
        <div>
          <dt className="text-xs text-neutral-400">Beds max</dt>
          <dd className="font-medium text-neutral-800">{fmtValue(beds_max)}</dd>
        </div>
        <div>
          <dt className="text-xs text-neutral-400">Price min</dt>
          <dd className="font-medium text-neutral-800">{fmtPrice(price_min)}</dd>
        </div>
        <div>
          <dt className="text-xs text-neutral-400">Price max</dt>
          <dd className="font-medium text-neutral-800">{fmtPrice(price_max)}</dd>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <dt className="text-xs text-neutral-400">Property types</dt>
          <dd className="font-medium text-neutral-800">
            {property_types && property_types.length > 0
              ? property_types.join(', ')
              : 'Any'}
          </dd>
        </div>
      </dl>
    </div>
  )
}

// ---------------------------------------------------------------------------
// SuburbCard
// ---------------------------------------------------------------------------
function SuburbCard({ suburb, onRemove }) {
  return (
    <div className="bg-white rounded-lg border border-neutral-200 p-4 flex flex-col gap-1.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-neutral-900 truncate">{suburb.name}</p>
          <p className="text-xs text-neutral-400 mt-0.5">
            {suburb.postcode} {suburb.state}
          </p>
        </div>
        <button
          onClick={() => onRemove(suburb)}
          className="shrink-0 text-neutral-300 hover:text-red-400 transition-colors mt-0.5"
          title={`Remove ${suburb.name}`}
          aria-label={`Remove ${suburb.name}`}
        >
          <Trash2 size={13} />
        </button>
      </div>
      <Link
        to={`/suburbs/${suburb.id}`}
        className="text-xs text-blue-600 hover:text-blue-800 transition-colors mt-0.5"
      >
        View details →
      </Link>
    </div>
  )
}

// ---------------------------------------------------------------------------
// AddSuburbModal
// State is batched into a single reducer so useEffect can reset in one
// dispatch (avoids the react-hooks/set-state-in-effect lint rule).
// ---------------------------------------------------------------------------
const ADD_SUBURB_INITIAL = {
  selected: null,
  submitting: false,
  inlineError: null,
  inlineCandidates: null,
}

function addSuburbReducer(state, action) {
  switch (action.type) {
    case 'RESET':
      return ADD_SUBURB_INITIAL
    case 'SELECT':
      return { ...state, selected: action.candidate, inlineError: null, inlineCandidates: null }
    case 'SUBMIT_START':
      return { ...state, submitting: true, inlineError: null, inlineCandidates: null }
    case 'SUBMIT_ERROR':
      return { ...state, submitting: false, inlineError: action.error, inlineCandidates: action.candidates ?? null }
    case 'SUBMIT_DONE':
      return { ...state, submitting: false }
    default:
      return state
  }
}

function AddSuburbModal({ open, onClose, areaId, areaName, onAdded }) {
  const [state, dispatch] = useReducer(addSuburbReducer, ADD_SUBURB_INITIAL)
  const { selected, submitting, inlineError, inlineCandidates } = state

  // Reset in a single dispatch when modal opens.
  useEffect(() => {
    if (open) dispatch({ type: 'RESET' })
  }, [open])

  const handleSelect = (candidate) => {
    dispatch({ type: 'SELECT', candidate })
  }

  const handleSubmit = async () => {
    if (!selected) return
    dispatch({ type: 'SUBMIT_START' })
    try {
      await addSuburb(areaId, selected)
      dispatch({ type: 'SUBMIT_DONE' })
      onAdded(selected.name)
      onClose()
    } catch (e) {
      if (e.status === 409) {
        const body = e.body
        // Ambiguous match — candidates returned.
        if (body && typeof body === 'object' && body.detail && body.detail.candidates) {
          dispatch({ type: 'SUBMIT_ERROR', error: null, candidates: body.detail.candidates })
        } else if (body && typeof body === 'object' && body.detail) {
          // "already in list" message.
          const msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
          dispatch({ type: 'SUBMIT_ERROR', error: msg })
        } else {
          const msg = typeof body === 'string' ? body : 'Suburb already in this area.'
          dispatch({ type: 'SUBMIT_ERROR', error: msg })
        }
      } else if (e.status === 503) {
        dispatch({ type: 'SUBMIT_ERROR', error: 'Autocomplete unavailable — try again shortly.' })
      } else {
        dispatch({ type: 'SUBMIT_ERROR', error: e.message || 'Failed to add suburb.' })
      }
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`Add suburb to "${areaName}"`} maxWidth="max-w-md">
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-neutral-600 mb-1">Search suburb</label>
          <SuburbAutocomplete
            onSelect={handleSelect}
            disabled={submitting}
            placeholder="e.g. Mount Coolum"
          />
        </div>

        {selected && !inlineError && !inlineCandidates && (
          <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 border border-blue-100 rounded text-sm text-blue-800">
            <MapPin size={13} className="shrink-0 text-blue-400" />
            <span className="font-medium">{selected.name}</span>
            <span className="px-1.5 py-0.5 text-xs rounded bg-white border border-blue-200 font-mono tabular-nums">
              {selected.postcode}
            </span>
            <span className="px-1.5 py-0.5 text-xs rounded bg-blue-100 text-blue-600 font-medium">
              {selected.state}
            </span>
          </div>
        )}

        {inlineError && (
          <div className="flex items-center gap-2 px-3 py-2 bg-red-50 border border-red-200 rounded text-xs text-red-700">
            <AlertCircle size={12} className="shrink-0" />
            {inlineError}
          </div>
        )}

        {inlineCandidates && inlineCandidates.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-neutral-500">Multiple matches found — please select one:</p>
            {inlineCandidates.map((c) => (
              <button
                key={`${c.name}-${c.postcode}-${c.state}`}
                type="button"
                onClick={() => handleSelect(c)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-left border border-neutral-200 rounded hover:bg-blue-50 hover:border-blue-300 transition-colors"
              >
                <span className="flex-1 font-medium">{c.name}</span>
                <span className="px-1.5 py-0.5 text-xs rounded bg-neutral-100 text-neutral-500 font-mono tabular-nums">
                  {c.postcode}
                </span>
                <span className="px-1.5 py-0.5 text-xs rounded bg-blue-50 text-blue-600 font-medium">
                  {c.state}
                </span>
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !selected}
            className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Adding…' : 'Add suburb'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// LatestRunCard
// ---------------------------------------------------------------------------
function LatestRunCard({ latestRun }) {
  if (!latestRun) {
    return (
      <div className="bg-white rounded-lg border border-neutral-200 p-4 text-sm text-neutral-400">
        No runs yet.
      </div>
    )
  }
  const { id, status, triggered_at, completed_at, counts } = latestRun

  return (
    <div className="bg-white rounded-lg border border-neutral-200 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-neutral-500">
          Latest Run
        </h3>
        <Link
          to={`/runs/${id}`}
          className="text-xs text-blue-600 hover:text-blue-800 transition-colors"
        >
          #{id}
        </Link>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-500">
        <RunStatusPill status={status} />
        <span>Triggered {timeAgo(triggered_at)}</span>
        {completed_at && <span>Completed {timeAgo(completed_at)}</span>}
      </div>
      {counts && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          <JobCountBadge label="queued"     count={counts.queued}     colour="bg-neutral-100 text-neutral-600" />
          <JobCountBadge label="running"    count={counts.running}    colour="bg-blue-100 text-blue-700" />
          <JobCountBadge label="succeeded"  count={counts.succeeded}  colour="bg-green-100 text-green-700" />
          <JobCountBadge label="failed"     count={counts.failed}     colour="bg-red-100 text-red-700" />
          <JobCountBadge label="deadletter" count={counts.deadletter} colour="bg-orange-100 text-orange-700" />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// PastRunsSection — collapsed by default
// ---------------------------------------------------------------------------
function PastRunsSection({ listId }) {
  const [expanded, setExpanded] = useState(false)
  const [runs, setRuns] = useState(null)
  const [loading, setLoading] = useState(false)
  const [fetchErr, setFetchErr] = useState(null)
  const loadedRef = useRef(false)

  const load = useCallback(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    setLoading(true)
    setFetchErr(null)
    listRuns({ list_id: listId, limit: 10 })
      .then((data) => {
        setRuns(data)
        setLoading(false)
      })
      .catch((e) => {
        setFetchErr(e.message)
        setLoading(false)
        loadedRef.current = false
      })
  }, [listId])

  const handleToggle = () => {
    const next = !expanded
    setExpanded(next)
    if (next) load()
  }

  return (
    <div className="bg-white rounded-lg border border-neutral-200">
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-sm font-medium text-neutral-700 hover:bg-neutral-50 transition-colors rounded-lg"
        onClick={handleToggle}
      >
        <span className="flex items-center gap-2">
          {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          Past Runs
        </span>
        <span className="text-xs text-neutral-400 font-normal">last 10</span>
      </button>

      {expanded && (
        <div className="border-t border-neutral-100">
          {loading && (
            <div className="px-4 py-6 text-sm text-neutral-400 text-center">Loading…</div>
          )}
          {fetchErr && (
            <div className="px-4 py-3 text-sm text-red-600 flex items-center gap-2">
              <AlertCircle size={14} />
              {fetchErr}
            </div>
          )}
          {!loading && !fetchErr && runs && runs.length === 0 && (
            <div className="px-4 py-6 text-sm text-neutral-400 text-center">No runs found.</div>
          )}
          {!loading && !fetchErr && runs && runs.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-neutral-100 text-neutral-500">
                    <th className="px-4 py-2 text-left font-medium">Run</th>
                    <th className="px-4 py-2 text-left font-medium">Triggered</th>
                    <th className="px-4 py-2 text-left font-medium">Completed</th>
                    <th className="px-4 py-2 text-left font-medium">Status</th>
                    <th className="px-4 py-2 text-left font-medium">Jobs</th>
                    <th className="px-4 py-2 text-left font-medium">Duration</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => {
                    const counts = run.job_counts ?? {}
                    const total = Object.values(counts).reduce((a, b) => a + b, 0)
                    const succeeded = counts.succeeded ?? 0
                    const failed = (counts.failed ?? 0) + (counts.deadletter ?? 0)
                    return (
                      <tr
                        key={run.id}
                        className="border-b border-neutral-50 hover:bg-neutral-50 transition-colors"
                      >
                        <td className="px-4 py-2.5">
                          <Link
                            to={`/runs/${run.id}`}
                            className="text-blue-600 hover:text-blue-800 font-medium transition-colors"
                          >
                            #{run.id}
                          </Link>
                        </td>
                        <td className="px-4 py-2.5 text-neutral-500">{timeAgo(run.triggered_at)}</td>
                        <td className="px-4 py-2.5 text-neutral-500">
                          {run.completed_at ? timeAgo(run.completed_at) : '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          <RunStatusPill status={run.status} />
                        </td>
                        <td className="px-4 py-2.5 text-neutral-500 tabular-nums">
                          {succeeded}/{total}
                          {failed > 0 && (
                            <span className="ml-1 text-red-500">({failed} failed)</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-neutral-500">
                          {formatDuration(run.triggered_at, run.completed_at)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// EditAreaModal
// Form state is managed as { fields: {...}, err: string|null } so we can
// reset everything in a single dispatch from useEffect (avoiding the
// "multiple setState calls in effect" lint rule).
// ---------------------------------------------------------------------------
function editFormReducer(state, action) {
  switch (action.type) {
    case 'RESET':
      return { fields: action.fields, err: null }
    case 'PATCH':
      return { ...state, fields: { ...state.fields, ...action.patch } }
    case 'SET_ERR':
      return { ...state, err: action.err }
    default:
      return state
  }
}

function EditAreaModal({ open, onClose, area, onSaved }) {
  const [{ fields, err }, dispatchForm] = useReducer(editFormReducer, {
    fields: null,
    err: null,
  })
  const [submitting, setSubmitting] = useState(false)

  // Reset form in a single dispatch when modal opens.
  useEffect(() => {
    if (open && area) {
      const f = area.filters ?? {}
      dispatchForm({
        type: 'RESET',
        fields: {
          name: area.name ?? '',
          description: area.description ?? '',
          beds_min: f.beds_min ?? '',
          beds_max: f.beds_max ?? '',
          price_min: f.price_min ?? '',
          price_max: f.price_max ?? '',
          property_types: f.property_types ?? [],
        },
      })
    }
  }, [open, area])

  if (!open || !fields) return null

  const toggleType = (t) => {
    dispatchForm({
      type: 'PATCH',
      patch: {
        property_types: fields.property_types.includes(t)
          ? fields.property_types.filter((x) => x !== t)
          : [...fields.property_types, t],
      },
    })
  }

  const handleSubmit = async () => {
    setSubmitting(true)
    dispatchForm({ type: 'SET_ERR', err: null })
    try {
      const filters = {}
      if (fields.beds_min !== '' && fields.beds_min != null) filters.beds_min = Number(fields.beds_min)
      if (fields.beds_max !== '' && fields.beds_max != null) filters.beds_max = Number(fields.beds_max)
      if (fields.price_min !== '' && fields.price_min != null) filters.price_min = Number(fields.price_min)
      if (fields.price_max !== '' && fields.price_max != null) filters.price_max = Number(fields.price_max)
      if (fields.property_types.length > 0) filters.property_types = fields.property_types

      await updateArea(area.id, {
        name: fields.name,
        description: fields.description || null,
        filters,
      })
      onSaved()
      onClose()
    } catch (e) {
      dispatchForm({ type: 'SET_ERR', err: e.message })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Edit Area" maxWidth="max-w-lg">
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-neutral-600 mb-1">Name *</label>
          <input
            className="w-full border border-neutral-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
            value={fields.name}
            onChange={(e) => dispatchForm({ type: 'PATCH', patch: { name: e.target.value } })}
            placeholder="Area name"
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-neutral-600 mb-1">Description</label>
          <textarea
            className="w-full border border-neutral-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 resize-none"
            rows={2}
            value={fields.description}
            onChange={(e) => dispatchForm({ type: 'PATCH', patch: { description: e.target.value } })}
            placeholder="Optional description"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-neutral-600 mb-1">Beds min</label>
            <input
              type="number"
              min="0"
              className="w-full border border-neutral-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              value={fields.beds_min}
              onChange={(e) => dispatchForm({ type: 'PATCH', patch: { beds_min: e.target.value } })}
              placeholder="Any"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-neutral-600 mb-1">Beds max</label>
            <input
              type="number"
              min="0"
              className="w-full border border-neutral-200 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
              value={fields.beds_max}
              onChange={(e) => dispatchForm({ type: 'PATCH', patch: { beds_max: e.target.value } })}
              placeholder="Any"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-neutral-600 mb-1">Price min</label>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-neutral-400">$</span>
              <input
                type="number"
                min="0"
                className="w-full border border-neutral-200 rounded pl-6 pr-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                value={fields.price_min}
                onChange={(e) => dispatchForm({ type: 'PATCH', patch: { price_min: e.target.value } })}
                placeholder="Any"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-neutral-600 mb-1">Price max</label>
            <div className="relative">
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-neutral-400">$</span>
              <input
                type="number"
                min="0"
                className="w-full border border-neutral-200 rounded pl-6 pr-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
                value={fields.price_max}
                onChange={(e) => dispatchForm({ type: 'PATCH', patch: { price_max: e.target.value } })}
                placeholder="Any"
              />
            </div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-neutral-600 mb-2">Property types</label>
          <div className="flex flex-wrap gap-2">
            {PROPERTY_TYPES.map((t) => {
              const selected = fields.property_types.includes(t)
              return (
                <button
                  key={t}
                  type="button"
                  onClick={() => toggleType(t)}
                  className={`px-3 py-1 text-xs rounded border transition-colors ${
                    selected
                      ? 'bg-blue-50 border-blue-300 text-blue-700 font-medium'
                      : 'bg-white border-neutral-200 text-neutral-600 hover:border-neutral-300'
                  }`}
                >
                  {t}
                </button>
              )
            })}
          </div>
        </div>

        {err && (
          <p className="text-xs text-red-600 flex items-center gap-1.5">
            <AlertCircle size={12} /> {err}
          </p>
        )}

        <div className="flex items-center justify-end gap-2 pt-1">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !fields.name.trim()}
            className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ---------------------------------------------------------------------------
// AreaDetailPage
// ---------------------------------------------------------------------------
export default function AreaDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [showRunModal, setShowRunModal] = useState(false)
  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [showEditModal, setShowEditModal] = useState(false)
  const [showAddSuburbModal, setShowAddSuburbModal] = useState(false)
  // suburb to confirm removal: { id, name } | null
  const [suburbToRemove, setSuburbToRemove] = useState(null)
  const [removePending, setRemovePending] = useState(false)
  const [runPending, setRunPending] = useState(false)
  const [deletePending, setDeletePending] = useState(false)
  const [toast, setToast] = useState(null)
  const [areaDetail, setAreaDetail] = useState(null)
  // Track how many times we need to re-fetch area detail (incremented by actions).
  const [detailTick, setDetailTick] = useState(0)

  const showToast = useCallback((message, type = 'success') => setToast({ message, type }), [])

  // Fetch full area detail (includes suburbs[]).
  useEffect(() => {
    let cancelled = false
    getArea(id)
      .then((data) => { if (!cancelled) setAreaDetail(data) })
      .catch(() => { /* non-critical */ })
    return () => { cancelled = true }
  }, [id, detailTick])

  // Adaptive polling for the summary DTO.
  const fetcher = useCallback(() => getAreaSummary(id), [id])
  const shouldPoll = useCallback((data) => data?.in_flight === true, [])
  const { data: summary, error, isLoading, isLive, refetch } = useAdaptivePoll(fetcher, {
    shouldPoll,
    intervalMs: 5000,
  })

  // When the summary latestRun changes, also refresh area detail so the
  // suburb list stays in sync.
  const prevRunIdRef = useRef(null)
  useEffect(() => {
    if (!summary) return
    const runId = summary.latest_run?.id ?? null
    if (runId !== prevRunIdRef.current) {
      prevRunIdRef.current = runId
      setDetailTick((t) => t + 1)
    }
  }, [summary])

  const suburbCount = summary?.suburb_count ?? 0
  const latestRun = summary?.latest_run ?? null
  const jobCount = suburbCount * 3

  const handleRun = async () => {
    setRunPending(true)
    try {
      const result = await runArea(id)
      setShowRunModal(false)
      showToast(`Run #${result.run_id} enqueued — ${result.count} job${result.count !== 1 ? 's' : ''} queued.`)
      refetch()
    } catch (e) {
      showToast(`Failed to start run: ${e.message}`, 'error')
    } finally {
      setRunPending(false)
    }
  }

  const handleDelete = async () => {
    setDeletePending(true)
    try {
      await deleteArea(id)
      setShowDeleteModal(false)
      showToast('Area deleted.')
      navigate('/areas')
    } catch (e) {
      showToast(`Failed to delete: ${e.message}`, 'error')
      setDeletePending(false)
    }
  }

  const handleRemoveSuburb = async () => {
    if (!suburbToRemove) return
    setRemovePending(true)
    try {
      await removeSuburb(id, suburbToRemove.id)
      const name = suburbToRemove.name
      setSuburbToRemove(null)
      showToast(`Removed ${name}`)
      setDetailTick((t) => t + 1)
      refetch()
    } catch (e) {
      showToast(`Failed to remove suburb: ${e.message}`, 'error')
    } finally {
      setRemovePending(false)
    }
  }

  // ---------------------------------------------------------------------------
  // Loading / error states
  // ---------------------------------------------------------------------------

  if (isLoading && !summary) {
    return (
      <div>
        <div className="mb-5">
          <Link
            to="/areas"
            className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800 transition-colors"
          >
            <ArrowLeft size={14} /> Back to Areas
          </Link>
        </div>
        <div className="space-y-4 animate-pulse">
          <div className="h-6 bg-neutral-100 rounded w-1/3" />
          <div className="h-4 bg-neutral-100 rounded w-1/2" />
          <div className="h-32 bg-neutral-100 rounded" />
        </div>
      </div>
    )
  }

  if (error && !summary) {
    return (
      <div>
        <div className="mb-5">
          <Link
            to="/areas"
            className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800 transition-colors"
          >
            <ArrowLeft size={14} /> Back to Areas
          </Link>
        </div>
        <div className="flex items-center gap-2 p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <AlertCircle size={16} className="shrink-0" />
          <span>Failed to load area: {error}</span>
        </div>
      </div>
    )
  }

  // ---------------------------------------------------------------------------
  // Main render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-5">
      <div>
        <Link
          to="/areas"
          className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800 transition-colors"
        >
          <ArrowLeft size={14} />
          Back to Areas
        </Link>
      </div>

      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-xl font-bold text-neutral-900 truncate">
              {summary?.name ?? `Area ${id}`}
            </h1>
            {isLive && <LivePill />}
          </div>
          {summary?.description && (
            <p className="mt-1 text-sm text-neutral-500">{summary.description}</p>
          )}
          <p className="mt-1 text-xs text-neutral-400">
            {suburbCount} suburb{suburbCount !== 1 ? 's' : ''}
            {summary?.properties_observed != null && (
              <> · {summary.properties_observed.toLocaleString()} properties observed</>
            )}
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
          <button
            onClick={refetch}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 hover:border-neutral-300 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
            Refresh
          </button>
          <button
            onClick={() => setShowEditModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 hover:border-neutral-300 transition-colors"
          >
            <Pencil size={14} />
            Edit
          </button>
          <button
            onClick={() => setShowAddSuburbModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 hover:border-neutral-300 transition-colors"
          >
            <Plus size={14} />
            Add suburb
          </button>
          <button
            onClick={() => setShowDeleteModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm text-red-600 border border-red-200 rounded hover:bg-red-50 transition-colors"
          >
            <Trash2 size={14} />
            Delete
          </button>
          <button
            onClick={() => setShowRunModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded transition-colors"
          >
            <Play size={14} />
            Run now
          </button>
        </div>
      </div>

      {/* Active listing split */}
      {summary?.active_listings && (
        <CategorySplit
          forsale={summary.active_listings.forsale ?? 0}
          forrent={summary.active_listings.forrent ?? 0}
          recentlysold={summary.active_listings.recentlysold ?? 0}
        />
      )}

      {/* Filters block */}
      <FiltersBlock filters={summary?.filters} />

      {/* Suburbs grid */}
      <div>
        <h2 className="text-sm font-semibold text-neutral-700 mb-3">Suburbs</h2>
        {areaDetail?.suburbs && areaDetail.suburbs.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
            {areaDetail.suburbs.map((s) => (
              <SuburbCard key={s.id} suburb={s} onRemove={setSuburbToRemove} />
            ))}
          </div>
        ) : areaDetail?.suburbs && areaDetail.suburbs.length === 0 ? (
          <p className="text-sm text-neutral-400">No suburbs attached to this area yet.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 animate-pulse">
            {[1, 2, 3].map((i) => (
              <div key={i} className="bg-neutral-100 rounded-lg h-20" />
            ))}
          </div>
        )}
      </div>

      {/* Latest run summary card */}
      <div>
        <h2 className="text-sm font-semibold text-neutral-700 mb-3">Latest Run</h2>
        <LatestRunCard latestRun={latestRun} />
      </div>

      {/* Past runs — collapsed by default */}
      <PastRunsSection listId={id} />

      {/* ---- Modals ---- */}

      <RunConfirmModal
        open={showRunModal}
        onClose={() => setShowRunModal(false)}
        onConfirm={handleRun}
        title="Run this area?"
        body={
          <span>
            This will enqueue{' '}
            <strong>{suburbCount}</strong> suburb{suburbCount !== 1 ? 's' : ''} × 3 categories
            = <strong>{jobCount}</strong> job{jobCount !== 1 ? 's' : ''} against onthehouse.com.au.
          </span>
        }
        confirmLabel="Run"
        disabled={runPending}
      />

      <RunConfirmModal
        open={showDeleteModal}
        onClose={() => setShowDeleteModal(false)}
        onConfirm={handleDelete}
        title={`Delete "${summary?.name ?? 'this area'}"?`}
        body="Suburbs remain. This cannot be undone."
        confirmLabel="Delete"
        danger
        disabled={deletePending}
      />

      <EditAreaModal
        open={showEditModal}
        onClose={() => setShowEditModal(false)}
        area={areaDetail ?? (summary ? { ...summary, suburbs: [] } : null)}
        onSaved={() => {
          showToast('Area updated.')
          refetch()
          setDetailTick((t) => t + 1)
        }}
      />

      <AddSuburbModal
        open={showAddSuburbModal}
        onClose={() => setShowAddSuburbModal(false)}
        areaId={id}
        areaName={summary?.name ?? `Area ${id}`}
        onAdded={(name) => {
          showToast(`Added ${name}`)
          setDetailTick((t) => t + 1)
          refetch()
        }}
      />

      <RunConfirmModal
        open={!!suburbToRemove}
        onClose={() => setSuburbToRemove(null)}
        onConfirm={handleRemoveSuburb}
        title={`Remove "${suburbToRemove?.name}"?`}
        body={
          <span>
            Remove <strong>{suburbToRemove?.name}</strong> from{' '}
            <strong>{summary?.name ?? 'this area'}</strong>? The suburb itself remains in the
            system.
          </span>
        }
        confirmLabel="Remove"
        danger
        disabled={removePending}
      />

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  )
}
