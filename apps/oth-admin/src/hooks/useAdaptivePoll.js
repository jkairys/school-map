import { useCallback, useEffect, useReducer, useRef, useState } from 'react'

/**
 * useAdaptivePoll — fetch on mount, then poll every `intervalMs` while
 * `shouldPoll(data)` returns true. Stops polling the moment it returns false.
 * Cleans up timers on unmount.
 *
 * Signature:
 *   useAdaptivePoll(fetcher, { shouldPoll, intervalMs = 5000 })
 *
 * Returns:
 *   { data, error, isLoading, isLive, refetch }
 *
 * - `isLive` is true whenever the polling loop is actively scheduled.
 * - `refetch` cancels any pending timer and immediately triggers a new fetch
 *   (regardless of whether polling is active).
 */

function reducer(state, action) {
  switch (action.type) {
    case 'START':
      return { ...state, isLoading: true, error: null }
    case 'OK':
      return { data: action.data, error: null, isLoading: false, isLive: action.isLive }
    case 'ERR':
      return { ...state, error: action.error, isLoading: false, isLive: false }
    default:
      return state
  }
}

export default function useAdaptivePoll(fetcher, { shouldPoll, intervalMs = 5000 } = {}) {
  const [state, dispatch] = useReducer(reducer, {
    data: null,
    error: null,
    isLoading: true,
    isLive: false,
  })

  // Tick is incremented to trigger a re-fetch (on mount and on refetch()).
  const [tick, setTick] = useState(0)

  // Stable refs for options, updated via useEffect.
  const fetcherRef = useRef(fetcher)
  const shouldPollRef = useRef(shouldPoll)
  const intervalMsRef = useRef(intervalMs)
  const timerRef = useRef(null)
  const mountedRef = useRef(true)

  useEffect(() => { fetcherRef.current = fetcher }, [fetcher])
  useEffect(() => { shouldPollRef.current = shouldPoll }, [shouldPoll])
  useEffect(() => { intervalMsRef.current = intervalMs }, [intervalMs])

  // Cancel any pending timer and bump tick to force a new fetch.
  const refetch = useCallback(() => {
    if (timerRef.current != null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    setTick((t) => t + 1)
  }, [])

  // Fetch effect — runs on mount and whenever tick changes.
  useEffect(() => {
    mountedRef.current = true
    dispatch({ type: 'START' })

    let cancelled = false

    fetcherRef.current()
      .then((data) => {
        if (cancelled || !mountedRef.current) return

        const isLive = !!(shouldPollRef.current && shouldPollRef.current(data))
        dispatch({ type: 'OK', data, isLive })

        if (isLive) {
          timerRef.current = setTimeout(() => {
            if (mountedRef.current) {
              timerRef.current = null
              setTick((t) => t + 1)
            }
          }, intervalMsRef.current)
        }
      })
      .catch((err) => {
        if (cancelled || !mountedRef.current) return
        dispatch({ type: 'ERR', error: err.message ?? String(err) })
      })

    return () => {
      cancelled = true
      if (timerRef.current != null) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [tick]) // tick is the only intended dependency — fetcher/shouldPoll/intervalMs are read from refs

  // Cleanup on unmount.
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  return { ...state, refetch }
}
