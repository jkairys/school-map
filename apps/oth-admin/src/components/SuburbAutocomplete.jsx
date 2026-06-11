import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, Loader2, MapPin } from 'lucide-react'

import { autocomplete } from '../api/suburbs.js'

/**
 * SuburbAutocomplete — debounced suburb search input with a dropdown of candidates.
 *
 * Props:
 *   onSelect  {function}   - called with { name, postcode, state } when a candidate is chosen
 *   disabled  {boolean}    - disable the input (e.g. while a submit is in progress)
 *   placeholder {string}   - input placeholder text
 */
export default function SuburbAutocomplete({ onSelect, disabled = false, placeholder = 'Search suburb…' }) {
  const [query, setQuery] = useState('')
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)

  const debounceRef = useRef(null)
  const containerRef = useRef(null)

  // Close dropdown when clicking outside.
  useEffect(() => {
    const handler = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false)
        setActiveIndex(-1)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const runSearch = useCallback(async (q) => {
    const cleaned = q.trim()
    if (!cleaned) {
      setCandidates([])
      setOpen(false)
      setLoading(false)
      setError(null)
      return
    }

    setLoading(true)
    setError(null)

    try {
      const results = await autocomplete(cleaned)
      setCandidates(results.slice(0, 5))
      setOpen(true)
      setActiveIndex(-1)
    } catch (e) {
      setError(e.message || 'Autocomplete failed')
      setCandidates([])
      setOpen(true)
    } finally {
      setLoading(false)
    }
  }, [])

  const handleChange = (e) => {
    const val = e.target.value
    setQuery(val)

    if (debounceRef.current) clearTimeout(debounceRef.current)

    if (!val.trim()) {
      setOpen(false)
      setCandidates([])
      setError(null)
      setLoading(false)
      return
    }

    // Show loading indicator immediately so the user knows something is happening.
    setLoading(true)
    debounceRef.current = setTimeout(() => {
      runSearch(val)
    }, 250)
  }

  const handleSelect = (candidate) => {
    setQuery('')
    setCandidates([])
    setOpen(false)
    setActiveIndex(-1)
    setError(null)
    onSelect({ name: candidate.name, postcode: candidate.postcode, state: candidate.state })
  }

  const handleKeyDown = (e) => {
    if (!open) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => Math.min(i + 1, candidates.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (activeIndex >= 0 && activeIndex < candidates.length) {
        handleSelect(candidates[activeIndex])
      }
    } else if (e.key === 'Escape') {
      setOpen(false)
      setActiveIndex(-1)
    }
  }

  const showEmptyState = open && !loading && !error && query.trim() && candidates.length === 0

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (candidates.length > 0 || showEmptyState || error) setOpen(true)
          }}
          disabled={disabled}
          placeholder={placeholder}
          className="w-full border border-neutral-200 rounded px-3 py-1.5 pr-8 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400 disabled:opacity-50 disabled:cursor-not-allowed"
          autoComplete="off"
          aria-expanded={open}
          aria-haspopup="listbox"
          role="combobox"
        />
        {loading && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-400 pointer-events-none">
            <Loader2 size={14} className="animate-spin" />
          </span>
        )}
        {!loading && query && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 text-neutral-300 pointer-events-none">
            <MapPin size={14} />
          </span>
        )}
      </div>

      {open && (
        <div
          role="listbox"
          className="absolute z-50 left-0 right-0 mt-1 bg-white border border-neutral-200 rounded-lg shadow-lg overflow-hidden"
        >
          {error && (
            <div className="flex items-center gap-2 px-3 py-2.5 text-xs text-red-600 bg-red-50 border-b border-red-100">
              <AlertCircle size={12} className="shrink-0" />
              <span>{error} — try a different spelling.</span>
            </div>
          )}

          {showEmptyState && (
            <div className="px-3 py-3 text-xs text-neutral-400 text-center">
              No matches — try a different spelling.
            </div>
          )}

          {!error && candidates.map((c, i) => (
            <button
              key={`${c.name}-${c.postcode}-${c.state}`}
              role="option"
              aria-selected={i === activeIndex}
              onMouseDown={(e) => {
                // Use mousedown so click fires before blur closes dropdown.
                e.preventDefault()
                handleSelect(c)
              }}
              onMouseEnter={() => setActiveIndex(i)}
              className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                i === activeIndex
                  ? 'bg-blue-50 text-blue-900'
                  : 'text-neutral-800 hover:bg-neutral-50'
              } ${i < candidates.length - 1 ? 'border-b border-neutral-50' : ''}`}
            >
              <span className="flex-1 font-medium truncate">{c.name}</span>
              <span className="flex items-center gap-1 shrink-0">
                <span className="px-1.5 py-0.5 text-xs rounded bg-neutral-100 text-neutral-500 font-mono tabular-nums">
                  {c.postcode}
                </span>
                <span className="px-1.5 py-0.5 text-xs rounded bg-blue-50 text-blue-600 font-medium">
                  {c.state}
                </span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
