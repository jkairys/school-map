/**
 * PriceChart — Recharts LineChart over listing snapshot history.
 *
 * Props:
 *   snapshots  {Array}  - list of { observed_at, price, changed_fields }
 *                         Snapshots with null price are filtered OUT of the
 *                         chart data but the caller is responsible for showing
 *                         them in the table below.
 *
 * Handles single-point listings gracefully (renders a visible dot with no line).
 * Smoke test: given 5 snapshots (all with prices), renders 5 data points.
 */
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  Dot,
} from 'recharts'
import { formatPrice } from '../utils/format.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Format an ISO datetime as "MMM dd", e.g. "Jan 07".
 * @param {string} isoString
 * @returns {string}
 */
function formatAxisDate(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  return d.toLocaleDateString('en-AU', { month: 'short', day: '2-digit' })
}

/**
 * Custom Tooltip shown on hover.
 */
function ChartTooltip({ active, payload }) {
  if (!active || !payload || payload.length === 0) return null
  const point = payload[0].payload
  const changedFields = Array.isArray(point.changed_fields) ? point.changed_fields : []

  return (
    <div className="bg-white border border-neutral-200 rounded-lg shadow-md px-3 py-2 text-sm">
      <p className="text-neutral-500 text-xs mb-1">{formatAxisDate(point.observed_at)}</p>
      <p className="font-semibold text-neutral-900">{formatPrice(point.price)}</p>
      {changedFields.length > 0 && (
        <p className="text-xs text-neutral-500 mt-1 max-w-[200px] break-words">
          {changedFields.join(', ')}
        </p>
      )}
    </div>
  )
}

/**
 * Custom dot renderer — always renders a visible dot so single-point charts
 * are never blank.
 */
function AlwaysDot(props) {
  const { cx, cy, fill, stroke } = props
  if (cx == null || cy == null) return null
  return <Dot cx={cx} cy={cy} r={4} fill={fill} stroke={stroke} strokeWidth={2} />
}

// ---------------------------------------------------------------------------
// PriceChart
// ---------------------------------------------------------------------------

export default function PriceChart({ snapshots }) {
  // Filter out snapshots with no price.
  const chartData = (snapshots ?? [])
    .filter((s) => s.price != null)
    .map((s) => ({
      observed_at: s.observed_at,
      price: s.price,
      changed_fields: s.changed_fields ?? [],
      // Label for axis: compact date string
      label: formatAxisDate(s.observed_at),
    }))

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-sm text-neutral-400 bg-neutral-50 rounded-lg border border-neutral-200">
        No price data to chart.
      </div>
    )
  }

  // Y-axis domain: add 5% padding so points don't sit on the axis edges.
  const prices = chartData.map((d) => d.price)
  const minPrice = Math.min(...prices)
  const maxPrice = Math.max(...prices)
  const pad = Math.max((maxPrice - minPrice) * 0.05, maxPrice * 0.02, 1000)
  const yDomain = [Math.floor((minPrice - pad) / 1000) * 1000, Math.ceil((maxPrice + pad) / 1000) * 1000]

  return (
    <div className="w-full h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            axisLine={{ stroke: '#e5e7eb' }}
          />
          <YAxis
            tickFormatter={(v) => formatPrice(v)}
            tick={{ fontSize: 11, fill: '#6b7280' }}
            tickLine={false}
            axisLine={false}
            width={80}
            domain={yDomain}
          />
          <Tooltip content={<ChartTooltip />} />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={<AlwaysDot fill="#3b82f6" stroke="#ffffff" />}
            activeDot={{ r: 6, fill: '#1d4ed8', stroke: '#ffffff', strokeWidth: 2 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
