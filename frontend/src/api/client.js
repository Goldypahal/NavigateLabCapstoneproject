import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// ─── Upload ──────────────────────────────────────────────────────────────────

export async function uploadCSV(file, track) {
  const form = new FormData()
  form.append('file', file)
  form.append('track', track)
  const { data } = await api.post('/upload/csv', form)
  return data
}

export async function uploadEvidence(file, uploadId, { date, shift, equipment } = {}) {
  const form = new FormData()
  form.append('file', file)
  form.append('upload_id', uploadId)
  if (date) form.append('date', date)
  if (shift) form.append('shift', shift)
  if (equipment) form.append('equipment', equipment)
  const { data } = await api.post('/upload/evidence', form)
  return data
}

// ─── Analysis ────────────────────────────────────────────────────────────────

export async function runAnalysis({ uploadId, track, model, thresholdPct, sigma, baselineWeeks }) {
  const { data } = await api.post('/analysis/run', {
    upload_id: uploadId,
    track,
    model,
    threshold_pct: thresholdPct,
    sigma,
    baseline_weeks: baselineWeeks,
  })
  return data
}

export async function getAnomalies(uploadId) {
  const { data } = await api.get(`/analysis/${uploadId}/anomalies`)
  return data
}

// ─── Review ──────────────────────────────────────────────────────────────────

export async function getActions(uploadId) {
  const { data } = await api.get(`/review/${uploadId}/actions`)
  return data
}

export async function decideAction({ actionId, decision, managerName, editedText, notes }) {
  const { data } = await api.post('/review/decide', {
    action_id: actionId,
    decision,
    manager_name: managerName,
    edited_text: editedText,
    notes,
  })
  return data
}

export async function generateBriefing(uploadId, language = 'en') {
  const { data } = await api.post(`/review/${uploadId}/briefing?language=${language}`)
  return data
}

export function getBriefingAudioUrl(uploadId) {
  return `/api/review/${uploadId}/briefing/audio`
}

export async function getBriefingText(uploadId) {
  const { data } = await api.get(`/review/${uploadId}/briefing/text`)
  return data
}

// ─── Verify ──────────────────────────────────────────────────────────────────

export async function verifyFix(track, actionId, file) {
  const form = new FormData()
  form.append('action_id', actionId)
  form.append('file', file)
  const { data } = await api.post(`/verify/${track}`, form)
  return data
}

// ─── Config ──────────────────────────────────────────────────────────────────

export async function getThresholds() {
  const { data } = await api.get('/config/thresholds')
  return data
}

