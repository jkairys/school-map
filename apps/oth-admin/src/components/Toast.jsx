import { useEffect } from 'react'
import { CheckCircle, XCircle, X } from 'lucide-react'

/**
 * Toast — a transient notification banner.
 *
 * Props:
 *   toast      {Object|null}  - { message: string, type: 'success'|'error' } or null
 *   onDismiss  {function}     - called to clear the toast
 *   duration   {number}       - auto-dismiss after ms (default 4000; 0 = no auto-dismiss)
 */
export default function Toast({ toast, onDismiss, duration = 4000 }) {
  useEffect(() => {
    if (!toast || duration === 0) return
    const t = setTimeout(onDismiss, duration)
    return () => clearTimeout(t)
  }, [toast, duration, onDismiss])

  if (!toast) return null

  const isError = toast.type === 'error'
  const containerClass = isError
    ? 'bg-red-50 border-red-200 text-red-800'
    : 'bg-green-50 border-green-200 text-green-800'

  return (
    <div className="fixed bottom-5 right-5 z-50 max-w-sm">
      <div className={`flex items-start gap-2.5 px-4 py-3 rounded-lg border shadow-lg text-sm ${containerClass}`}>
        {isError
          ? <XCircle size={16} className="shrink-0 mt-0.5 text-red-500" />
          : <CheckCircle size={16} className="shrink-0 mt-0.5 text-green-600" />
        }
        <span className="flex-1">{toast.message}</span>
        <button
          onClick={onDismiss}
          className="shrink-0 text-current opacity-60 hover:opacity-100 transition-opacity"
          aria-label="Dismiss"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
