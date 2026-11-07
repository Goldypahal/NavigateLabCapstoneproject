import React, { useState } from 'react'
import { CheckCircle, TrendingDown, TrendingUp, Minus, Upload, Loader2, AlertTriangle } from 'lucide-react'
import { verifyFix } from '../api/client.js'

export default function VerifyPage({ uploadId, track }) {
  const [actionId, setActionId] = useState('')
  const [file, setFile] = useState(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function handleVerify() {
    if (!actionId || !file) { setError('Enter action ID and select a post-fix CSV.'); return }
    setLoading(true)
    setError(null)
    try {
      const data = await verifyFix(track === 'water' ? 'water' : 'energy', Number(actionId), file)
      setResult(data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    }
    setLoading(false)
  }

  const verdictIcon = result?.verdict === 'improved'
    ? <TrendingDown className="w-6 h-6 text-green-500" />
    : result?.verdict === 'worsened'
      ? <TrendingUp className="w-6 h-6 text-red-500" />
      : <Minus className="w-6 h-6 text-gray-400" />

  const unit = track === 'water' ? 'kL' : 'kWh'

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Post-Fix Verification</h1>
        <p className="text-gray-500 mt-1">Upload post-fix meter data to verify savings. All calculations are in code.</p>
      </div>

      <div className="card space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Action ID</label>
          <input
            type="number"
            value={actionId}
            onChange={e => setActionId(e.target.value)}
            placeholder="e.g. 3"
            className="border rounded-lg px-3 py-2 text-sm w-32"
          />
          <p className="text-xs text-gray-400 mt-1">Find the ID on the Review page.</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Post-Fix CSV</label>
          <input
            type="file"
            accept=".csv"
            onChange={e => setFile(e.target.files[0])}
            className="text-sm"
          />
          <p className="text-xs text-gray-400 mt-1">Same format as the original meter CSV, covering the post-fix period.</p>
        </div>

        <button className="btn-primary" onClick={handleVerify} disabled={loading}>
          {loading ? <><Loader2 className="w-4 h-4 animate-spin inline mr-1" />Verifying…</> : 'Verify Savings'}
        </button>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
            <AlertTriangle className="w-4 h-4" /> {error}
          </div>
        )}
      </div>

      {result && (
        <div className="card">
          <div className="flex items-center gap-3 mb-4">
            {verdictIcon}
            <div>
              <h2 className="font-bold text-gray-900 capitalize">{result.verdict}</h2>
              <p className="text-sm text-gray-500">{result.note}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Baseline Average', value: `${result.baseline_avg.toFixed(2)} ${unit}`, sub: 'per shift/day' },
              { label: 'Post-Fix Average', value: `${result.postfix_avg.toFixed(2)} ${unit}`, sub: 'per shift/day' },
              { label: 'Change', value: `${result.pct_change >= 0 ? '+' : ''}${result.pct_change.toFixed(1)}%`, sub: result.pct_change < 0 ? 'reduction ✓' : 'increase ✗' },
              { label: 'Value Saved', value: `${result.value_saved.toFixed(2)} ${unit}`, sub: 'avoidable' },
              { label: 'Cost Saved', value: `₹${result.cost_saved.toFixed(2)}`, sub: 'per period' },
            ].map(({ label, value, sub }) => (
              <div key={label} className="bg-gray-50 rounded-lg p-3">
                <div className="text-xs text-gray-500">{label}</div>
                <div className="font-bold text-gray-900 text-lg">{value}</div>
                <div className="text-xs text-gray-400">{sub}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

