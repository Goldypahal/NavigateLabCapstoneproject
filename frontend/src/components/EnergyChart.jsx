import React from 'react'
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine
} from 'recharts'

export default function EnergyChart({ anomalies = [], thresholdPct = 20 }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="card text-center text-gray-400 py-12">
        No energy anomaly data available to plot.
      </div>
    )
  }

  // Format data for time-series chart
  const data = anomalies.map(a => {
    const dateLabel = a.timestamp ? a.timestamp.split('T')[0] : a.anomaly_id
    const baseline = a.baseline_value || 0
    const upperThreshold = baseline * (1 + (thresholdPct / 100))
    return {
      name: `${dateLabel} (${a.shift || ''})`,
      actual: a.actual_value,
      baseline: baseline,
      upperBand: upperThreshold,
      excess: a.excess_value > 0 ? a.excess_value : 0,
      deviationPct: a.deviation_pct,
      isFlagged: a.deviation_pct > thresholdPct
    }
  }).reverse()

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">Energy Consumption vs. 4-Week Baseline Band</h3>
        <span className="text-xs text-gray-500">Unit: kWh per shift</span>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} interval="preserveStartEnd" angle={-15} textAnchor="end" />
            <YAxis tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
            <Tooltip
              formatter={(value, name) => {
                if (name === 'actual') return [`${Number(value).toFixed(1)} kWh`, 'Actual Use']
                if (name === 'baseline') return [`${Number(value).toFixed(1)} kWh`, 'Baseline Average']
                if (name === 'upperBand') return [`${Number(value).toFixed(1)} kWh`, `Threshold (+${thresholdPct}%)`]
                return [value, name]
              }}
            />
            <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 12 }} />
            <Area
              type="monotone"
              dataKey="upperBand"
              name="Threshold Band"
              stroke="#fbbf24"
              fill="#fef3c7"
              fillOpacity={0.4}
            />
            <Line
              type="monotone"
              dataKey="baseline"
              name="Baseline (Code)"
              stroke="#6b7280"
              strokeDasharray="4 4"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="actual"
              name="Actual Reading"
              stroke="#2563eb"
              strokeWidth={2}
              dot={props => {
                const { cx, cy, payload } = props
                if (payload.isFlagged) {
                  return <circle cx={cx} cy={cy} r={5} fill="#ef4444" stroke="#fff" strokeWidth={2} key={cx} />
                }
                return <circle cx={cx} cy={cy} r={3} fill="#2563eb" key={cx} />
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-gray-400">
        Red dots denote anomalies flagged by code when exceeding max({thresholdPct}%, 2σ).
      </p>
    </div>
  )
}

