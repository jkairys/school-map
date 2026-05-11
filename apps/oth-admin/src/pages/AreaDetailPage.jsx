import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Construction } from 'lucide-react'

/**
 * Area detail page — placeholder stub.
 * Full implementation lands in slice 08.
 */
export default function AreaDetailPage() {
  const { id } = useParams()

  return (
    <div>
      <div className="mb-5">
        <Link
          to="/areas"
          className="inline-flex items-center gap-1.5 text-sm text-neutral-500 hover:text-neutral-800 transition-colors"
        >
          <ArrowLeft size={14} />
          Back to Areas
        </Link>
      </div>
      <div className="flex flex-col items-center justify-center py-20 text-neutral-400">
        <Construction size={40} className="mb-3 opacity-30" />
        <p className="text-sm font-medium text-neutral-500">Area detail — coming in slice 08</p>
        <p className="text-xs mt-1 text-neutral-400">Area ID: {id}</p>
      </div>
    </div>
  )
}
