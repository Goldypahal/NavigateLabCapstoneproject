import React from 'react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine
} from 'recharts'

export default function WaterChart({ anomalies = [] }) {
  if (!anomalies || anomalies.length === 0) {
    return (
      <div className="card text-center text-gray-400 py-12">
        No water balance data available to plot.
      </div>
    )
  }

  const data = anomalies.map(a => {
    const dateLabel = a.timestamp ? a.timestamp.split('T')[0] : a.anomaly_id
    return {
      name: dateLabel,
      intake: a.actual_value,
      baseline: a.baseline_value,
      unaccounted: a.excess_value,
      conflict: a.cause_status === 'conflicting'
    }
  }).reverse()

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-gray-800">Water Balance & Unaccounted Volume</h3>
        <span className="text-xs text-gray-500">Unit: kL per day</span>
      </div>

      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} angle={-15} textAnchor="end" />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip
              formatter={(val, name) => {
                if (name === 'intake') return [`${Number(val).toFixed(1)} kL`, 'Intake / Unaccounted']
                if (name === 'baseline') return [`${Number(val).toFixed(1)} kL`, 'Baseline Loss']
                if (name === 'unaccounted') return [`${Number(val).toFixed(1)} kL`, 'Excess Unaccounted Loss']
                return [val, name]
              }}
            />
            <Legend verticalAlign="top" height={36} wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={5.0} stroke="#ef4444" strokeDasharray="3 3" label={{ value: '5 kL/d Threshold', fill: '#ef4444', fontSize: 10 }} />
            <Bar dataKey="intake" name="Measured Loss (kL)" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
            <Bar dataKey="unaccounted" name="Excess Unaccounted (kL)" fill="#f97316" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-gray-400">
        Balance calculated as Intake − Process Use − Discharge in code. Bars crossing red line trigger investigation.
      </p>
    </div>
  )
}

