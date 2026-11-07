import React, { useState } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { Activity, Droplets, Upload, ClipboardCheck, BarChart3, Shield } from 'lucide-react'
import clsx from 'clsx'

import UploadPage from './pages/Upload.jsx'
import AnalysisPage from './pages/Analysis.jsx'
import ReviewPage from './pages/Review.jsx'
import VerifyPage from './pages/Verify.jsx'

const NAV_ITEMS = [
  { to: '/',         label: 'Upload',   icon: Upload },
  { to: '/analysis', label: 'Analysis', icon: BarChart3 },
  { to: '/review',   label: 'Review',   icon: ClipboardCheck },
  { to: '/verify',   label: 'Verify',   icon: Shield },
]

function Nav() {
  return (
    <nav className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-14">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1">
              <Activity className="w-5 h-5 text-blue-600" />
              <Droplets className="w-5 h-5 text-cyan-500" />
            </div>
            <span className="font-bold text-gray-900">ResourceLens</span>
            <span className="text-xs text-gray-400 ml-1">PS-22</span>
          </div>

          {/* Nav links */}
          <div className="flex gap-1">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-blue-50 text-blue-700'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  )
                }
              >
                <Icon className="w-4 h-4" />
                {label}
              </NavLink>
            ))}
          </div>
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  // Global session state — upload_id flows through all pages
  const [uploadId, setUploadId] = useState(null)
  const [track, setTrack] = useState('energy')

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-50">
        <Nav />
        <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <Routes>
            <Route
              path="/"
              element={
                <UploadPage
                  uploadId={uploadId}
                  setUploadId={setUploadId}
                  track={track}
                  setTrack={setTrack}
                />
              }
            />
            <Route
              path="/analysis"
              element={<AnalysisPage uploadId={uploadId} track={track} />}
            />
            <Route
              path="/review"
              element={<ReviewPage uploadId={uploadId} />}
            />
            <Route
              path="/verify"
              element={<VerifyPage uploadId={uploadId} track={track} />}
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

