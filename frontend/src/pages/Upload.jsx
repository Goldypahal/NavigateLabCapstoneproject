import React, { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, FileText, Image, Mic, CheckCircle, AlertCircle, Loader2, Zap, Droplets } from 'lucide-react'
import { uploadCSV, uploadEvidence } from '../api/client.js'

function TrackToggle({ track, setTrack }) {
  return (
    <div className="flex gap-2 p-1 bg-gray-100 rounded-lg w-fit">
      <button
        onClick={() => setTrack('energy')}
        className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors
          ${track === 'energy' ? 'bg-white shadow-sm text-blue-700' : 'text-gray-500 hover:text-gray-700'}`}
      >
        <Zap className="w-4 h-4" /> Energy
      </button>
      <button
        onClick={() => setTrack('water')}
        className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors
          ${track === 'water' ? 'bg-white shadow-sm text-cyan-700' : 'text-gray-500 hover:text-gray-700'}`}
      >
        <Droplets className="w-4 h-4" /> Water
      </button>
      <button
        onClick={() => setTrack('both')}
        className={`flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-colors
          ${track === 'both' ? 'bg-white shadow-sm text-purple-700' : 'text-gray-500 hover:text-gray-700'}`}
      >
        Both
      </button>
    </div>
  )
}

function FileDropZone({ label, accept, icon: Icon, onFile, hint }) {
  const ref = useRef()
  const [dragging, setDragging] = useState(false)
  const [files, setFiles] = useState([])

  function handle(fs) {
    const arr = Array.from(fs)
    setFiles(prev => [...prev, ...arr])
    arr.forEach(f => onFile(f))
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => { e.preventDefault(); setDragging(false); handle(e.dataTransfer.files) }}
      onClick={() => ref.current.click()}
      className={`border-2 border-dashed rounded-xl p-6 cursor-pointer transition-colors text-center
        ${dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'}`}
    >
      <input ref={ref} type="file" accept={accept} multiple hidden onChange={e => handle(e.target.files)} />
      <Icon className="w-8 h-8 mx-auto mb-2 text-gray-400" />
      <p className="font-medium text-gray-700">{label}</p>
      <p className="text-xs text-gray-400 mt-1">{hint}</p>
      {files.length > 0 && (
        <div className="mt-3 space-y-1">
          {files.map((f, i) => (
            <div key={i} className="flex items-center justify-center gap-1.5 text-xs text-green-700">
              <CheckCircle className="w-3.5 h-3.5" /> {f.name}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatusBadge({ msg, type }) {
  if (!msg) return null
  return (
    <div className={`flex items-start gap-2 p-3 rounded-lg text-sm mt-3
      ${type === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
      {type === 'error' ? <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" /> : <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />}
      <span>{msg}</span>
    </div>
  )
}

export default function UploadPage({ uploadId, setUploadId, track, setTrack }) {
  const navigate = useNavigate()
  const [csvFile, setCsvFile] = useState(null)
  const [evidenceFiles, setEvidenceFiles] = useState([])
  const [csvStatus, setCsvStatus] = useState(null)
  const [evidenceStatuses, setEvidenceStatuses] = useState([])
  const [loading, setLoading] = useState(false)
  const [currentUploadId, setCurrentUploadId] = useState(uploadId)

  async function handleCSV(file) {
    setCsvFile(file)
    setLoading(true)
    try {
      const res = await uploadCSV(file, track === 'both' ? 'energy' : track)
      if (res.errors.length) {
        setCsvStatus({ msg: res.errors.join('; '), type: 'error' })
      } else {
        const uid = res.upload_id
        setCurrentUploadId(uid)
        setUploadId(uid)
        setCsvStatus({ msg: `✓ ${res.rows_accepted} rows accepted. Upload ID: ${uid}`, type: 'success' })
      }
    } catch (e) {
      setCsvStatus({ msg: `Upload failed: ${e.message}`, type: 'error' })
    }
    setLoading(false)
  }

  async function handleEvidence(file) {
    if (!currentUploadId) {
      setEvidenceStatuses(prev => [...prev, { msg: 'Upload a CSV first to get an Upload ID.', type: 'error' }])
      return
    }
    try {
      const res = await uploadEvidence(file, currentUploadId)
      const warn = res.low_confidence_fields.length
        ? ` ⚠ Low confidence: ${res.low_confidence_fields.join(', ')}`
        : ''
      setEvidenceStatuses(prev => [...prev, {
        msg: `✓ ${res.source_id} — ${file.name}${warn}`,
        type: res.low_confidence_fields.length ? 'warn' : 'success'
      }])
    } catch (e) {
      setEvidenceStatuses(prev => [...prev, { msg: `Failed: ${file.name} — ${e.message}`, type: 'error' }])
    }
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Factory Data</h1>
        <p className="text-gray-500 mt-1">Upload meter readings, inspection sheets and voice notes to begin investigation.</p>
      </div>

      {/* Track selector */}
      <div className="card">
        <h2 className="font-semibold text-gray-800 mb-3">1. Select Track</h2>
        <TrackToggle track={track} setTrack={setTrack} />
        <p className="text-xs text-gray-400 mt-2">
          {track === 'energy' && 'Energy track: 15-min kWh readings. Required columns: timestamp, kwh'}
          {track === 'water' && 'Water track: daily water balance. Required columns: date, intake_kl, process_kl, discharge_kl'}
          {track === 'both' && 'Upload energy CSV first, then water CSV separately.'}
        </p>
      </div>

      {/* CSV Upload */}
      <div className="card">
        <h2 className="font-semibold text-gray-800 mb-3">2. Meter Readings CSV</h2>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-blue-600 mb-3">
            <Loader2 className="w-4 h-4 animate-spin" /> Validating CSV…
          </div>
        )}
        <FileDropZone
          label="Drop CSV file here or click to browse"
          accept=".csv,text/csv"
          icon={FileText}
          onFile={handleCSV}
          hint="Max 50 MB · energy_readings.csv or water_readings.csv"
        />
        {csvStatus && <StatusBadge msg={csvStatus.msg} type={csvStatus.type} />}
      </div>

      {/* Evidence Upload */}
      <div className="card">
        <h2 className="font-semibold text-gray-800 mb-1">3. Inspection Sheets & Voice Notes</h2>
        <p className="text-xs text-gray-400 mb-3">Upload after the CSV. Each file is processed by Nexus AI (vision/STT).</p>
        <div className="grid grid-cols-2 gap-4">
          <FileDropZone
            label="Inspection Sheets / Nameplates"
            accept="image/*"
            icon={Image}
            onFile={handleEvidence}
            hint="JPEG, PNG, WebP · handwritten sheets"
          />
          <FileDropZone
            label="Operator Voice Notes"
            accept="audio/*"
            icon={Mic}
            onFile={handleEvidence}
            hint="WAV, MP3, M4A · timestamped transcription"
          />
        </div>
        {evidenceStatuses.map((s, i) => (
          <StatusBadge key={i} msg={s.msg} type={s.type} />
        ))}
      </div>

      {/* Proceed */}
      {currentUploadId && (
        <div className="flex justify-end">
          <button className="btn-primary" onClick={() => navigate('/analysis')}>
            Run Analysis →
          </button>
        </div>
      )}
    </div>
  )
}

