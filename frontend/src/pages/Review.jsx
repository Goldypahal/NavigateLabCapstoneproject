import React, { useState, useEffect, useRef } from 'react'
import {
  CheckCircle, XCircle, Edit3, Volume2, Loader2,
  AlertTriangle, Info, Shield, ChevronDown, ChevronUp
} from 'lucide-react'
import AudioPlayer from '../components/AudioPlayer.jsx'
import { getActions, decideAction, generateBriefing, getBriefingAudioUrl, getBriefingText } from '../api/client.js'

const URGENCY_BADGE = {
  high:   'badge-high',
  medium: 'badge-medium',
  low:    'badge-low',
}

const STATUS_BADGE = {
  pending:  'bg-gray-100 text-gray-600',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  edited:   'bg-blue-100 text-blue-700',
}

function ActionCard({ action, managerName, onDecide }) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(action.action_text)
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handleDecide(decision) {
    if (!managerName.trim()) { alert('Enter manager name first.'); return }
    setBusy(true)
    await onDecide({
      actionId: action.id,
      decision,
      managerName,
      editedText: decision === 'edited' ? editText : undefined,
    })
    setEditing(false)
    setBusy(false)
  }

  const displayText = action.status === 'edited' ? (action.edited_text || action.action_text) : action.action_text

  return (
    <div className="card border-l-4 border-l-transparent hover:border-l-blue-400 transition-all">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span className="font-mono text-xs text-gray-400">#{action.priority_rank}</span>
            <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${URGENCY_BADGE[action.urgency]}`}>
              {action.urgency.toUpperCase()}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${STATUS_BADGE[action.status]}`}>
              {action.status}
            </span>
            <span className="text-xs text-gray-400">{action.track}</span>
          </div>

          {editing ? (
            <textarea
              value={editText}
              onChange={e => setEditText(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 text-sm font-medium resize-none"
              rows={3}
            />
          ) : (
            <p className="text-sm font-medium text-gray-800">{displayText}</p>
          )}

          {action.equipment && (
            <p className="text-xs text-gray-500 mt-1">Equipment: {action.equipment}</p>
          )}

          <div className="mt-2 flex gap-3 text-xs text-gray-500">
            {action.estimated_loss != null && (
              <span>Estimated loss: {action.estimated_loss.toFixed(1)} {action.track === 'energy' ? 'kWh' : 'kL'}</span>
            )}
            {action.estimated_cost != null && (
              <span>Cost: ₹{action.estimated_cost.toFixed(2)}</span>
            )}
          </div>
        </div>

        {/* Decision buttons */}
        {action.status === 'pending' && (
          <div className="flex flex-col gap-2 flex-shrink-0">
            <button className="btn-success text-xs py-1.5 px-3 flex items-center gap-1" onClick={() => handleDecide('approved')} disabled={busy}>
              <CheckCircle className="w-3.5 h-3.5" /> Approve
            </button>
            <button className="btn-secondary text-xs py-1.5 px-3 flex items-center gap-1" onClick={() => { setEditing(e => !e) }}>
              <Edit3 className="w-3.5 h-3.5" /> {editing ? 'Cancel' : 'Edit'}
            </button>
            {editing && (
              <button className="btn-primary text-xs py-1.5 px-3" onClick={() => handleDecide('edited')} disabled={busy}>
                Save Edit
              </button>
            )}
            <button className="btn-danger text-xs py-1.5 px-3 flex items-center gap-1" onClick={() => handleDecide('rejected')} disabled={busy}>
              <XCircle className="w-3.5 h-3.5" /> Reject
            </button>
          </div>
        )}
      </div>

      {/* Evidence + AI explanation */}
      {action.cause_status && (
        <div className="mt-3">
          <button onClick={() => setExpanded(e => !e)} className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            Evidence & explanation
          </button>
          {expanded && (
            <div className="mt-2 space-y-1 text-xs">
              <div className="flex items-center gap-1">
                <span className="text-gray-500">Cause confidence:</span>
                <span className="font-medium">{action.cause_status}</span>
              </div>
              {action.uncertainty_note && (
                <div className="flex items-start gap-1 text-gray-500">
                  <Info className="w-3.5 h-3.5 mt-0.5" />
                  {action.uncertainty_note}
                </div>
              )}
              {action.evidence_source_ids?.length > 0 && (
                <div>Sources: {action.evidence_source_ids.join(', ')}</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function ReviewPage({ uploadId }) {
  const [actions, setActions] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [managerName, setManagerName] = useState('')
  const [briefingLoading, setBriefingLoading] = useState(false)
  const [briefingUrl, setBriefingUrl] = useState(null)
  const [briefingText, setBriefingText] = useState('')
  const audioRef = useRef()

  useEffect(() => {
    if (uploadId) loadActions()
  }, [uploadId])

  async function loadActions() {
    setLoading(true)
    try {
      const data = await getActions(uploadId)
      setActions(data)
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    }
    setLoading(false)
  }

  async function handleDecide(opts) {
    await decideAction(opts)
    await loadActions()
  }

  async function handleBriefing() {
    setBriefingLoading(true)
    try {
      await generateBriefing(uploadId)
      const { text } = await getBriefingText(uploadId)
      setBriefingText(text)
      setBriefingUrl(getBriefingAudioUrl(uploadId))
    } catch (e) {
      setError(e.response?.data?.detail || e.message)
    }
    setBriefingLoading(false)
  }

  const pending  = actions.filter(a => a.status === 'pending').length
  const approved = actions.filter(a => ['approved', 'edited'].includes(a.status)).length

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Manager Review</h1>
        <p className="text-gray-500 mt-1">Review AI recommendations. Actions must be approved before audio briefing is generated.</p>
      </div>

      {/* Manager name */}
      <div className="card flex items-center gap-4">
        <Shield className="w-5 h-5 text-blue-500 flex-shrink-0" />
        <div className="flex-1">
          <label className="block text-sm font-medium text-gray-700 mb-1">Your Name (for audit log)</label>
          <input
            type="text"
            value={managerName}
            onChange={e => setManagerName(e.target.value)}
            placeholder="e.g. Ramesh Kumar, Plant Manager"
            className="border rounded-lg px-3 py-2 text-sm w-full max-w-md"
          />
        </div>
        <div className="text-sm text-gray-500">
          {pending} pending · {approved} approved
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg text-sm">
          <AlertTriangle className="w-4 h-4" /> {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-2 text-blue-600">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading actions…
        </div>
      )}

      {/* Action list */}
      <div className="space-y-3">
        {actions.map(action => (
          <ActionCard key={action.id} action={action} managerName={managerName} onDecide={handleDecide} />
        ))}
      </div>

      {/* Audio briefing */}
      {approved > 0 && (
        <div className="card bg-blue-50 border-blue-200">
          <h2 className="font-semibold text-blue-900 mb-3 flex items-center gap-2">
            <Volume2 className="w-5 h-5" /> Shift Audio Briefing
          </h2>
          <p className="text-sm text-blue-700 mb-3">
            Generate an audio briefing from the {approved} approved action{approved !== 1 ? 's' : ''}.
            Only approved/edited actions are included.
          </p>
          <button className="btn-primary" onClick={handleBriefing} disabled={briefingLoading}>
            {briefingLoading ? <><Loader2 className="w-4 h-4 animate-spin inline mr-1" />Generating…</> : '🔊 Generate Audio Briefing'}
          </button>

          {briefingUrl && (
            <div className="mt-4 space-y-3">
              <AudioPlayer audioUrl={briefingUrl} />
              {briefingText && (
                <details className="mt-3">
                  <summary className="text-xs text-blue-600 cursor-pointer">View briefing text</summary>
                  <pre className="text-xs text-gray-700 mt-2 whitespace-pre-wrap font-sans bg-white p-3 rounded border">
                    {briefingText}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

