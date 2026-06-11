/**
 * RawPayloadViewer — collapsible section that pretty-prints a JSON payload.
 *
 * Collapsed by default. Clicking "Raw payload" toggles the pre-formatted JSON.
 *
 * Props:
 *   payload  {Object|null}  - the JSON payload to render
 *   label    {string}       - optional section label (default: "Raw payload")
 */
import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

export default function RawPayloadViewer({ payload, label = 'Raw payload' }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-neutral-200 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-neutral-50 hover:bg-neutral-100 text-sm font-medium text-neutral-700 transition-colors"
        aria-expanded={open}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {label}
        {payload == null && (
          <span className="ml-auto text-xs text-neutral-400 font-normal">no data</span>
        )}
      </button>

      {open && (
        <div className="border-t border-neutral-200 bg-neutral-950 overflow-x-auto">
          {payload == null ? (
            <p className="px-4 py-3 text-sm text-neutral-400 font-mono">null</p>
          ) : (
            <pre className="px-4 py-3 text-xs text-green-300 font-mono whitespace-pre leading-relaxed">
              {JSON.stringify(payload, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
