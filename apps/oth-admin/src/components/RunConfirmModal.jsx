import Modal from './Modal.jsx'

/**
 * RunConfirmModal — a generic confirm dialog built on Modal.
 *
 * Props:
 *   open          {boolean}   - controls visibility
 *   onClose       {function}  - called on cancel or backdrop click
 *   onConfirm     {function}  - called when user clicks the confirm button
 *   title         {string}    - dialog title
 *   body          {ReactNode} - dialog body / description text
 *   confirmLabel  {string}    - label for the confirm button (default: 'Confirm')
 *   danger        {boolean}   - use red styling for confirm button (default: false)
 *   disabled      {boolean}   - disable the confirm button (e.g. while loading)
 */
export default function RunConfirmModal({
  open,
  onClose,
  onConfirm,
  title,
  body,
  confirmLabel = 'Confirm',
  danger = false,
  disabled = false,
}) {
  const confirmClass = danger
    ? 'bg-red-600 hover:bg-red-700 text-white'
    : 'bg-blue-600 hover:bg-blue-700 text-white'

  return (
    <Modal open={open} onClose={onClose} title={title}>
      <div className="text-sm text-neutral-700 mb-5">{body}</div>
      <div className="flex items-center justify-end gap-2">
        <button
          onClick={onClose}
          className="px-3 py-1.5 text-sm text-neutral-600 border border-neutral-200 rounded hover:bg-neutral-50 hover:border-neutral-300 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={disabled}
          className={`px-3 py-1.5 text-sm font-medium rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${confirmClass}`}
        >
          {confirmLabel}
        </button>
      </div>
    </Modal>
  )
}
