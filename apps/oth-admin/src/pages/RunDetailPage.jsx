import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeft,
  RefreshCw,
  RotateCcw,
  AlertCircle,
  ChevronDown,
  ChevronRight,
} from 'lucide-react'

import { getRun, getRunJobs, retryFailed } from '../api/runs.js'
import { runArea } from '../api/areas.js'
import { getSuburb } from '../api/suburbs.js'
import useAdaptivePoll from '../hooks/useAdaptivePoll.js'
import RunStatusPill from '../components/RunStatusPill.jsx'
import LivePill from '../components/LivePill.jsx'
import RunConfirmModal from '../components/RunConfirmModal.jsx'
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

function fmtAbsolute(isoString) {
  if (!isoString) return '—'
  return new Date(isoString).toLocaleString()
}

const TRIGGER_SOURCE_STYLES = {
  api: 'bg-blue-50 text-blue-700 border-blue-200',
  cli: 'bg-purple-50 text-purple-700 border-purple-200',
  scheduler: 'bg-teal-50 text-teal-700 border-teal-200',
  retry: 'bg-amber-50 text-amber-700 border-amber-200',
}

function TriggerSourcePill({ source }) {
  const styles = TRIGGER_SOURCE_STYLES[source] ?? 'bg-neutral-100 text-neutral-600 border-neutral-200'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${styles}`}>
      {source ?? '—'}
    </span>
  )
}

const JOB_STATUS_STYLES = {
  queued: 'bg-neutral-100 text-neutral-600 border-neutral-200',
  running: 'bg-blue-100 text-blue-700 border-blue-200',
  succeeded: 'bg-green-100 text-green-700 border-green-200',
  failed: 'bg-red-100 text-red-700 border-red-200',
  deadletter: 'bg-orange-100 text-orange-700 border-orange-200',
}

function JobStatusPill({ status }) {
  const styles = JOB_STATUS_STYLES[status] ?? 'bg-neutral-100 text-neutral-600 border-neutral-200'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium border ${styles}`}>
      {status === 'running' && (
        <span className="mr-1 h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
      )}
      {status}
    </span>
  )
}

function CountBadge({ label, count, colour }) {
  if (!count) return null
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-medium ${colour}`}>
      <span className="tabular-nums">{count}</span>
      <span className="opacity-75">{label}</span>
    </span>
  )
}

const CATEGORY_LABELS = {
  forsale: 'For Sale',
  forrent: 'For Rent',
  recentlysold: 'Recently Sold',
}

function categoryLabel(cat) {
  return CATEGORY_LABELS[cat] ?? cat
}

function truncate(str, max = 80) {
  if (!str) return null
  if (str.length <= max) return str
  return str.slice(0, max) + '…'
}

// ---------------------------------------------------------------------------
// JobRow
// ---------------------------------------------------------------------------
function JobRow({ job, suburbName, onRetry }) {
  const isFailed = job.status === 'failed' || job.status === 'deadletter'
  const [expanded, setExpanded] = useState(false)
  const hasLongError = job.last_error_message && job.last_error_message.length > 80

  return (
    <tr className="border-b border-neutral-50 hover:bg-neutral-50 transition-colors">
      <td className="px-4 py-2.5 text-xs text-neutral-600">{suburbName}</td>
      <td className="px-4 py-2.5 text-xs text-neutral-600">{categoryLabel(job.category)}</td>
      <td className="px-4 py-2.5">
        <JobStatusPill status={job.status} />
      </td>
      <td className="px-4 py-2.5 text-xs text-neutral-500 tabular-nums">{job.attempts}</td>
      <td className="px-4 py-2.5 text-xs text-neutral-500 font-mono">
        {job.last_error_class ?? '—'}
      </td>
      <td className="px-4 py-2.5 text-xs text-neutral-500 max-w-xs">
        {job.last_error_message ? (
          <span>
            {expanded ? job.last_error_message : truncate(job.last_error_message)}
            {hasLongError && (
              <button
                onClick={() => setExpanded((e) => !e)}
                className="ml-1 text-blue-500 hover:text-blue-700 transition-colors"
              >
                {expanded ? 'less' : 'more'}
              </button>
            )}
          </span>
        ) : (
          <span className="text-neutral-300">—</span>
        )}
      </td>
      <td className="px-4 py-2.5 text-xs text-neutral-500">
        {job.claimed_at ? timeAgo(job.claimed_at) : '—'}
      </td>
      <td className="px-4 py-2.5 text-xs text-neutral-500">
        {job.completed_at ? timeAgo(job.completed_at) : '—'}
      </td>
      <td className="px-4 py-2.5">
        {isFailed && (
          <button
            onClick={() => onRetry(job)}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs text-amber-700 border border-amber-200 bg-amber-50 rounded hover:bg-amber-100 transition-colors"
          >
            <RotateCcw size={10} />
            Retry
          </button>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// SuburbGroup — collapsible group by suburb
// ---------------------------------------------------------------------------
function SuburbGroup({ suburbName, jobs, onRetry }) {
  const [open, setOpen] = useState(true)

  return (
    <>
      <tr
        className="bg-neutral-50 border-b border-neutral-100 cursor-pointer hover:bg-neutral-100 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        <td colSpan={9} className="px-4 py-2">
          <div className="flex items-center gap-2">
            {open
              ? <ChevronDown size={12} className="text-neutral-400" />
              : <ChevronRight size={12} className="text-neutral-400" />
            }
            <span className="text-xs font-semibold text-neutral-700">{suburbName}</span>
            <span className="text-xs text-neutral-400">
              ({jobs.length} job{jobs.length !== 1 ? 's' : ''})
            </span>
          </div>
        </td>
      </tr>
      {open && jobs.map((job) => (
        <JobRow
          key={job.id}
          job={job}
          suburbName={suburbName}
          onRetry={onRetry}
        />
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// RunDetailPage
// ---------------------------------------------------------------------------
export default function RunDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()

  // ---- modal / toast state ----
  const [showRetryAllModal, setShowRetryAllModal] = useState(false)
  const [retryAllPending, setRetryAllPending] = useState(false)
  const [selectedJob, setSelectedJob] = useState(null)
  const [rowRetryPending, setRowRetryPending] = useState(false)
  const [toast, setToast] = useState(null)

  const showToast = useCallback((message, type = 'success') => setToast({ message, type }), [])

  // ---- jobs state ----
  const [jobs, setJobs] = useState(null)
  const [jobsError, setJobsError] = useState(null)
  const [jobsLoading, setJobsLoading] = useState(true)

  // ---- suburb name cache ----
  const [suburbNames, setSuburbNames] = useState({})

  // ---- adaptive polling for run detail ----
  const fetcher = useCallback(() => getRun(id), [id])
  const shouldPoll = useCallback((data) => data?.status === 'running', [])
  const { data: run, error, isLoading, isLive, refetch } = useAdaptivePoll(fetcher, {
    shouldPoll,
    intervalMs: 5000,
  })

  // ---- fetch jobs whenever run id changes or run data refreshes ----
  useEffect(() => {
    let cancelled = false
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading flag pattern
    setJobsLoading(true)
    setJobsError(null)
    getRunJobs(id)
      .then((data) => {
        if (!cancelled) {
          setJobs(data)
          setJobsLoading(false)
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setJobsError(e.message)
          setJobsLoading(false)
        }
      })
    return () => { cancelled = true }
    // Re-fetch jobs when run id changes or run status changes (each poll tick updates status)
  }, [id, run?.status])

  // ---- resolve suburb names when jobs load ----
  useEffect(() => {
    if (!jobs || jobs.length === 0) return
    const unknownIds = [...new Set(jobs.map((j) => j.suburb_id).filter(Boolean))]
      .filter((sid) => !(sid in suburbNames))
    if (unknownIds.length === 0) return

    Promise.allSettled(
      unknownIds.map((sid) => getSuburb(sid).catch(() => null))
    ).then((results) => {
      setSuburbNames((prev) => {
        const next = { ...prev }
        unknownIds.forEach((sid, i) => {
          const result = results[i]
          if (result.status === 'fulfilled' && result.value) {
            const s = result.value
            next[sid] = s.name ? `${s.name} ${s.postcode ?? ''}`.trim() : `Suburb ${sid}`
          } else {
            next[sid] = `Suburb ${sid}`
          }
        })
        return next
      })
    })
  }, [jobs]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---- derived ----
  const jobCounts = run?.job_counts ?? {}
  const failedCount = (jobCounts.failed ?? 0) + (jobCounts.deadletter ?? 0)
  const hasFailures = failedCount > 0
  const totalJobs = Object.values(jobCounts).reduce((a, b) => a + b, 0)

  // Group jobs by suburb_id, failures first
  const groupedJobs = (() => {
    if (!jobs) return []
    const bySuburb = new Map()
    for (const job of jobs) {
      const sid = job.suburb_id ?? 0
      if (!bySuburb.has(sid)) bySuburb.set(sid, [])
      bySuburb.get(sid).push(job)
    }
    return [...bySuburb.entries()].sort(([, aJobs], [, bJobs]) => {
      const aHasFail = aJobs.some((j) => j.status === 'failed' || j.status === 'deadletter') ? 0 : 1
      const bHasFail = bJobs.some((j) => j.status === 'failed' || j.status === 'deadletter') ? 0 : 1
      return aHasFail - bHasFail
    })
  })()

  // ---- handlers ----

  const handleRetryAll = async () => {
    setRetryAllPending(true)
    try {
      const result = await retryFailed(id)
      setShowRetryAllModal(false)
      showToast(
        `Retry queued as run #${result.run_id} — ${result.count} job${result.count !== 1 ? 's' : ''}.`
      )
      navigate(`/runs/${result.run_id}`)
    } catch (e) {
      showToast(`Failed to retry: ${e.message}`, 'error')
    } finally {
      setRetryAllPending(false)
    }
  }

  const handleRowRetry = async () => {
    if (!selectedJob || !run?.scrape_list_id) return
    setRowRetryPending(true)
    try {
      const result = await runArea(run.scrape_list_id, {
        suburb_ids: [selectedJob.suburb_id],
        categories: [selectedJob.category],
        trigger_source: 'retry',
      })
      setSelectedJob(null)
      showToast(`Retry queued as run #${result.run_id}.`)
      navigate(`/runs/${result.run_id}`)
    } catch (e) {
      showToast(`Failed to retry job: ${e.message}`, 'error')
    } finally {
      setRowRetryPending(false)
    }
  }

  const selectedSuburbName = selectedJob
    ? (suburbNames[selectedJob.suburb_id] ?? `Suburb ${selectedJob.suburb_id}`)
    : ''

  // ---- loading / error states ----

  if (isLoading && !run) {
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
          <div className="h-48 bg-neutral-100 rounded" />
        </div>
      </div>
    )
  }

  if (error && !run) {
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
          <span>Failed to load run: {error}</span>
        </div>
      </div>
    )
  }

  // ---- main render ----

  return (
    <div className="space-y-5">
      {/* Back link */}
      <div>
        {run?.scrape_list_id ? (
          <Link
            to={`/areas/${run.scrape_list_id}`}
            className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800 transition-colors"
          >
            <ArrowLeft size={14} /> Back to Area
          </Link>
        ) : (
          <Link
            to="/areas"
            className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800 transition-colors"
          >
            <ArrowLeft size={14} /> Back to Areas
          </Link>
        )}
      </div>

      {/* "Retried from" backlink */}
      {run?.retried_from_run_id && (
        <div className="text-sm text-neutral-500">
          <Link
            to={`/runs/${run.retried_from_run_id}`}
            className="inline-flex items-center gap-1.5 hover:text-neutral-800 transition-colors"
          >
            <ArrowLeft size={12} />
            Retry of run #{run.retried_from_run_id}
          </Link>
        </div>
      )}

      {/* Page header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-xl font-bold text-neutral-900">
              Run #{id}
            </h1>
            {run && <RunStatusPill status={run.status} />}
            {run && <TriggerSourcePill source={run.trigger_source} />}
            {isLive && <LivePill />}
          </div>
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

          {hasFailures && (
            <button
              onClick={() => setShowRetryAllModal(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-amber-600 hover:bg-amber-700 rounded transition-colors"
            >
              <RotateCcw size={14} />
              Retry all failed
            </button>
          )}
        </div>
      </div>

      {/* Metadata strip */}
      {run && (
        <div className="bg-white rounded-lg border border-neutral-200 p-4">
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-3">
            <div>
              <dt className="text-xs text-neutral-400 mb-0.5">Triggered</dt>
              <dd className="text-xs font-medium text-neutral-800">
                {fmtAbsolute(run.triggered_at)}
              </dd>
              <dd className="text-xs text-neutral-500">{timeAgo(run.triggered_at)}</dd>
            </div>
            <div>
              <dt className="text-xs text-neutral-400 mb-0.5">Completed</dt>
              <dd className="text-xs font-medium text-neutral-800">
                {run.completed_at ? fmtAbsolute(run.completed_at) : 'in progress'}
              </dd>
              {run.completed_at && (
                <dd className="text-xs text-neutral-500">{timeAgo(run.completed_at)}</dd>
              )}
            </div>
            <div>
              <dt className="text-xs text-neutral-400 mb-0.5">Duration</dt>
              <dd className="text-xs font-medium text-neutral-800">
                {formatDuration(run.triggered_at, run.completed_at)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-neutral-400 mb-0.5">Source</dt>
              <dd className="mt-0.5">
                <TriggerSourcePill source={run.trigger_source} />
              </dd>
            </div>
          </dl>
        </div>
      )}

      {/* Counts rollup badges */}
      {run && (
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-neutral-500 font-medium">
            {totalJobs} job{totalJobs !== 1 ? 's' : ''}:
          </span>
          <CountBadge label="queued"     count={jobCounts.queued}     colour="bg-neutral-100 text-neutral-600" />
          <CountBadge label="running"    count={jobCounts.running}    colour="bg-blue-100 text-blue-700" />
          <CountBadge label="succeeded"  count={jobCounts.succeeded}  colour="bg-green-100 text-green-700" />
          <CountBadge label="failed"     count={jobCounts.failed}     colour="bg-red-100 text-red-700" />
          <CountBadge label="deadletter" count={jobCounts.deadletter} colour="bg-orange-100 text-orange-700" />
        </div>
      )}

      {/* Job table */}
      <div className="bg-white rounded-lg border border-neutral-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-neutral-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-neutral-700">Jobs</h2>
          {jobsLoading && (
            <span className="text-xs text-neutral-400 animate-pulse">Loading…</span>
          )}
        </div>

        {jobsError && (
          <div className="px-4 py-3 flex items-center gap-2 text-sm text-red-600">
            <AlertCircle size={14} />
            {jobsError}
          </div>
        )}

        {!jobsLoading && !jobsError && jobs && jobs.length === 0 && (
          <div className="px-4 py-8 text-sm text-neutral-400 text-center">
            No jobs found for this run.
          </div>
        )}

        {jobs && jobs.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-neutral-100 text-neutral-500">
                  <th className="px-4 py-2 text-left font-medium">Suburb</th>
                  <th className="px-4 py-2 text-left font-medium">Category</th>
                  <th className="px-4 py-2 text-left font-medium">Status</th>
                  <th className="px-4 py-2 text-left font-medium">Attempts</th>
                  <th className="px-4 py-2 text-left font-medium">Error class</th>
                  <th className="px-4 py-2 text-left font-medium max-w-xs">Error message</th>
                  <th className="px-4 py-2 text-left font-medium">Claimed</th>
                  <th className="px-4 py-2 text-left font-medium">Completed</th>
                  <th className="px-4 py-2 text-left font-medium">Action</th>
                </tr>
              </thead>
              <tbody>
                {groupedJobs.map(([suburbId, suburbJobs]) => {
                  const name = suburbNames[suburbId]
                    ?? (suburbId ? `Suburb ${suburbId}` : 'Unknown')
                  return (
                    <SuburbGroup
                      key={suburbId}
                      suburbName={name}
                      jobs={suburbJobs}
                      onRetry={(job) => setSelectedJob(job)}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ---- Modals ---- */}

      <RunConfirmModal
        open={showRetryAllModal}
        onClose={() => setShowRetryAllModal(false)}
        onConfirm={handleRetryAll}
        title="Retry all failed jobs?"
        body={
          <span>
            This will create a new run with{' '}
            <strong>{failedCount}</strong> job{failedCount !== 1 ? 's' : ''}{' '}
            ({jobCounts.failed ?? 0} failed + {jobCounts.deadletter ?? 0} deadletter).
          </span>
        }
        confirmLabel="Retry all failed"
        disabled={retryAllPending}
      />

      <RunConfirmModal
        open={!!selectedJob}
        onClose={() => setSelectedJob(null)}
        onConfirm={handleRowRetry}
        title="Retry this job?"
        body={
          selectedJob ? (
            <span>
              Will enqueue 1 job for{' '}
              <strong>{selectedSuburbName}</strong> × <strong>{categoryLabel(selectedJob.category)}</strong>.
            </span>
          ) : null
        }
        confirmLabel="Retry job"
        disabled={rowRetryPending}
      />

      <Toast toast={toast} onDismiss={() => setToast(null)} />
    </div>
  )
}
