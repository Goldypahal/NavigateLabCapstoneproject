import React, { useState, useRef, useEffect } from 'react'
import { Play, Pause, RotateCcw, Volume2, Download } from 'lucide-react'

export default function AudioPlayer({ audioUrl, title = 'Shift Audio Briefing' }) {
  const audioRef = useRef(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const updateTime = () => setCurrentTime(audio.currentTime)
    const updateDuration = () => setDuration(audio.duration || 0)
    const handleEnded = () => setIsPlaying(false)

    audio.addEventListener('timeupdate', updateTime)
    audio.addEventListener('loadedmetadata', updateDuration)
    audio.addEventListener('ended', handleEnded)

    return () => {
      audio.removeEventListener('timeupdate', updateTime)
      audio.removeEventListener('loadedmetadata', updateDuration)
      audio.removeEventListener('ended', handleEnded)
    }
  }, [audioUrl])

  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
    } else {
      audioRef.current.play()
      setIsPlaying(true)
    }
  }

  const handleRestart = () => {
    if (!audioRef.current) return
    audioRef.current.currentTime = 0
    audioRef.current.play()
    setIsPlaying(true)
  }

  const handleSeek = (e) => {
    const time = Number(e.target.value)
    if (audioRef.current) {
      audioRef.current.currentTime = time
      setCurrentTime(time)
    }
  }

  const formatTime = (secs) => {
    if (isNaN(secs)) return '0:00'
    const mins = Math.floor(secs / 60)
    const rem = Math.floor(secs % 60)
    return `${mins}:${rem < 10 ? '0' : ''}${rem}`
  }

  return (
    <div className="bg-white rounded-xl border border-blue-200 p-4 shadow-sm space-y-3">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Volume2 className="w-5 h-5 text-blue-600" />
          <span className="font-semibold text-gray-800 text-sm">{title}</span>
        </div>
        <a
          href={audioUrl}
          download="shift_briefing.mp3"
          className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 font-medium"
        >
          <Download className="w-3.5 h-3.5" /> Download MP3
        </a>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={togglePlay}
          className="p-2.5 bg-blue-600 text-white rounded-full hover:bg-blue-700 transition"
          aria-label={isPlaying ? 'Pause' : 'Play'}
        >
          {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
        </button>

        <button
          onClick={handleRestart}
          className="p-2 text-gray-500 hover:text-gray-700 rounded-full hover:bg-gray-100 transition"
          title="Restart from beginning"
        >
          <RotateCcw className="w-4 h-4" />
        </button>

        <span className="text-xs font-mono text-gray-500 w-10 text-right">
          {formatTime(currentTime)}
        </span>

        <input
          type="range"
          min={0}
          max={duration || 100}
          value={currentTime}
          onChange={handleSeek}
          className="flex-1 h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
        />

        <span className="text-xs font-mono text-gray-500 w-10">
          {formatTime(duration)}
        </span>
      </div>
    </div>
  )
}

