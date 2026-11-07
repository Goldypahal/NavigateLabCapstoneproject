import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, AlertTriangle, TrendingUp, Droplets, Zap, Info } from 'lucide-react'
import EnergyChart from '../components/EnergyChart.jsx'
import WaterChart from '../components/WaterChart.jsx'
import { runAnalysis, getAnomalies } from '../api/client.js'

const CAUSE_COLORS = {
  supported: 'text-red-700 bg-red-50 border-red-200',
  partially_supported: 'text-yellow-700 bg-yellow-50 border-yellow-200',
  unknown: 'text-gray-600 bg-gray-50 border-gray-200',
  conflicting: 'text-purple-700 bg-purple-50 border-purple-200',
}

function AnomalyCard({ anomaly }) {
  const [expanded, setExpanded] = useState(false)
  const unit = anomaly.track === 'energy' ? 'kWh' : 'kL'
  const colorClass = CAUSE_COLORS[anomaly.cause_status] || CAUSE_COLORS.unknown

  return (
    <div className={`border rounded-xl p-4 ${colorClass} transition-all`}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            {anomaly.track === 'energy'
              ? <Zap className="w-4 h-4 text-yellow-500" />
              : <Droplets className="w-4 h-4 text-blue-500" />}
            <span className="font-mono text-sm font-semibold">{anomaly.anomaly_id}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${colorClass}`}>
              {anomaly.cause_status || 'pending'}
            </span>
          </div>
          <p className="text-sm font-medium">{anomaly.timestamp?.split('T')[0]} · {anomaly.shift || '—'} shift</p>
        </div>
        <div className="text-right">
          <div className="text-lg font-bold text-red-600">+{anomaly.deviation_pct?.toFixed(1)}%</div>
          <div className="text-xs text-gray-500">vs baseline</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-3 text-sm">
        <div>
          <div className="text-xs text-gray-500">Actual</div>
          <div className="font-semibold">{anomaly.actual_value?.toFixed(1)} {unit}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Baseline</div>
          <div className="font-semibold">{anomaly.baseline_value?.toFixed(1)} {unit}</div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Excess</div>
          <div className="font-semibold text-red-600">{anomaly.excess_value?.toFixed(1)} {unit}</div>
        </div>
      </div>

      {anomaly.estimated_cost != null && (
        <div className="mt-2 text-sm">
          <span className="text-gray-500">Estimated cost: </span>
          <span className="font-semibold">₹{anomaly.estimated_cost?.toFixed(2)}</span>
        </div>
      )}

      {anomaly.likely_cause && (
        <div className="mt-3">
          <button
            onClick={() => setExpanded(e => !e)}
            className="text-xs font-medium underline underline-offset-2 cursor-pointer"
          >
            {expanded ? 'Hide' : 'Show'} AI explanation
          </button>
          {expanded && (
            <div className="mt-2 space-y-2">
              <p className="text-sm"><strong>Likely cause:</strong> {anomaly.likely_cause}</p>
              {anomaly.uncertainty_note && (
                <div className="flex items-start gap-1.5 text-xs text-gray-600 bg-white/60 rounded p-2 border">
                  <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
                  <span><strong>Uncertainty:</strong> {anomaly.uncertainty_note}</span>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="mt-2 text-xs text-gray-500">
        {anomaly.action_count} action{anomaly.action_count !== 1 ? 's' : ''} recommended
      </div>
    </div>
  )
}

export default function AnalysisPage({ uploadId, track }) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [anomalies, setAnomalies] = useState([])
  const [error, setError] = useState(null)
  const [model, setModel] = useState('a')  // A/B model comparison
  const [thresholdPct, setThresholdPct] = useState(20)

  async function handleRun() {
    if (!uploadId) { setError('No upload ID. Go back and upload a CSV first.'); return }
    setLoading(true)
    setError(null)
    try {
      await runAnalysis({
        uploadId,
        track: track || 'energy',
        model,
        thresholdPct,
      })
      const data = await getAnomalies(uploadId)
      setAnomalies(data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    }
    setLoading(false)
  }

  const flagged = anomalies.filter(a => a.deviation_pct > 0)
  const totalExcess = flagged.reduce((s, a) => s + (a.excess_value || 0), 0)
  const totalCost = flagged.reduce((s, a) => s + (a.estimated_cost || 0), 0)
  const unit = track === 'water' ? 'kL' : 'kWh'

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Anomaly Analysis</h1>
          <p className="text-gray-500 mt-1">Baseline computed by code — AI explains causes only.</p>
        </div>
        {uploadId && (
          <span className="text-xs font-mono text-gray-400 bg-gray-100 px-2 py-1 rounded">
            {uploadId.slice(0, 8)}…
          </span>
        )}
      </div>

      {/* Controls */}
      <div className="card flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">Threshold %</label>
          <input
            type="number"
            value={thresholdPct}
            onChange={e => setThresholdPct(Number(e.target.value))}
            className="w-24 border rounded-lg px-3 py-1.5 text-sm"
            min={5} max={100}
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-600 mb-1">LLM Model</label>
          <select
            value={model}
            onChange={e => setModel(e.target.value)}
            className="border rounded-lg px-3 py-1.5 text-sm"
          >
            <option value="a">Model A (Pro)</option>
            <option value="b">Model B (Fast)</option>
          </select>
        </div>
        <button className="btn-primary" onClick={handleRun} disabled={loading}>
          {loading ? <><Loader2 className="w-4 h-4 animate-spin inline mr-1" />Running…</> : '▶ Run Analysis'}
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {/* Summary */}
      {anomalies.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Anomalies Flagged', value: flagged.length, sub: 'of ' + anomalies.length + ' periods' },
            { label: `Total Excess ${unit}`, value: totalExcess.toFixed(1), sub: unit },
            { label: 'Estimated Cost', value: `₹${totalCost.toFixed(0)}`, sub: 'avoidable' },
          ].map(({ label, value, sub }) => (
            <div key={label} className="card text-center">
              <div className="text-3xl font-bold text-gray-900">{value}</div>
              <div className="text-sm font-medium text-gray-600 mt-1">{label}</div>
              <div className="text-xs text-gray-400">{sub}</div>
            </div>
          ))}
        </div>
      )}

      {/* Visual Chart (Stretch Goal) */}
      {anomalies.length > 0 && (
        <div>
          {track === 'water' ? (
            <WaterChart anomalies={anomalies} />
          ) : (
            <EnergyChart anomalies={anomalies} thresholdPct={thresholdPct} />
          )}
        </div>
      )}

      {/* Anomaly list */}
      {anomalies.length > 0 && (
        <div>
          <h2 className="font-semibold text-gray-800 mb-3 flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-red-500" />
            Flagged Anomalies ({flagged.length})
          </h2>
          <div className="space-y-3">
            {flagged.map(a => <AnomalyCard key={a.anomaly_id} anomaly={a} />)}
          </div>
        </div>
      )}

      {anomalies.length > 0 && (
        <div className="flex justify-end">
          <button className="btn-primary" onClick={() => navigate('/review')}>
            Review Actions →
          </button>
        </div>
      )}
    </div>
  )
}

