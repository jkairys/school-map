import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

/**
 * Modal — generic dialog primitive.
 *
 * Props:
 *   open         {boolean}    - controls visibility
 *   onClose      {function}   - called when backdrop or Escape is pressed
 *   title        {string}     - dialog title shown in the header
 *   children     {ReactNode}  - dialog body content
 *   maxWidth     {string}     - Tailwind max-width class (default: 'max-w-md')
 */
export default function Modal({ open, onClose, title, children, maxWidth = 'max-w-md' }) {
  const dialogRef = useRef(null)

  // Close on Escape key.
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  // Focus the dialog panel when it opens.
  useEffect(() => {
    if (open && dialogRef.current) {
      dialogRef.current.focus()
    }
  }, [open])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      aria-modal="true"
      role="dialog"
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={`relative z-10 bg-white rounded-lg shadow-xl border border-neutral-200 w-full ${maxWidth} mx-4 outline-none`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-100">
          <h2 className="text-sm font-semibold text-neutral-900">{title}</h2>
          <button
            onClick={onClose}
            className="text-neutral-400 hover:text-neutral-700 transition-colors"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4">
          {children}
        </div>
      </div>
    </div>
  )
}
