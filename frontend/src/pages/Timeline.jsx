import React, {
  forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState,
} from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Upload, Film, Image as ImageIcon, Trash2, Music, Play, Pause, Download,
  ArrowLeft, X, Scissors, Plus,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import { mediaApi, projectApi, downloadFile } from '../api/client'

const TRANSITIONS = [
  { value: 'none', label: 'Cut' },
  { value: 'fade', label: 'Fade' },
  { value: 'fadeblack', label: 'Fade to black' },
  { value: 'dissolve', label: 'Dissolve' },
  { value: 'wipeleft', label: 'Wipe left' },
  { value: 'wiperight', label: 'Wipe right' },
  { value: 'slideup', label: 'Slide up' },
  { value: 'slidedown', label: 'Slide down' },
  { value: 'circleopen', label: 'Circle open' },
  { value: 'circleclose', label: 'Circle close' },
]

const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3]
const PX_PER_SECOND = 22
const FALLBACK_VIDEO_SECONDS = 5

function fmt(s) {
  if (s == null || Number.isNaN(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function buildSegments(clips) {
  let t = 0
  return clips.map((c) => {
    const isPhoto = c.media.media_type === 'photo'
    let duration
    if (isPhoto) {
      duration = c.photo_duration_seconds || 3
    } else {
      const speed = c.speed_factor || 1
      // trim_end is always concretized server-side when a clip is added; this
      // fallback only matters if ffprobe was unavailable for every attempt.
      const sourceLen = c.trim_end != null ? c.trim_end - c.trim_start : FALLBACK_VIDEO_SECONDS
      duration = Math.max(0.2, sourceLen / speed)
    }
    const seg = { clip: c, isPhoto, duration, start: t, end: t + duration }
    t += duration
    return seg
  })
}

/** The single, unified preview player — used both for normal playback
 * across the whole timeline and for live-scrubbing while dragging a trim
 * handle, so there's only ever one video on screen. */
const SequencePreview = forwardRef(function SequencePreview({ segments, totalDuration }, ref) {
  const videoRef = useRef(null)
  const photoTimerRef = useRef(null)
  const loadedUrlRef = useRef(null)
  const pendingSeekRef = useRef(null)
  const playheadRef = useRef(0)

  const [activeIndex, setActiveIndex] = useState(0)
  const [playhead, setPlayheadState] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)

  const setPlayhead = (v) => { playheadRef.current = v; setPlayheadState(v) }

  const activeSeg = segments[activeIndex] || null

  useEffect(() => {
    if (activeIndex >= segments.length) setActiveIndex(Math.max(0, segments.length - 1))
  }, [segments, activeIndex])

  const loadSegment = useCallback((idx, seekSourceTime, playAfter) => {
    const seg = segments[idx]
    if (!seg) {
      setIsPlaying(false)
      return
    }
    setActiveIndex(idx)
    clearTimeout(photoTimerRef.current)

    if (seg.isPhoto) {
      setPlayhead(seg.start)
      if (playAfter) {
        photoTimerRef.current = setTimeout(() => loadSegment(idx + 1, null, true), seg.duration * 1000)
      }
      return
    }

    const url = mediaApi.fileUrl(seg.clip.media_id, seg.clip.media.current_filename)
    const targetTime = seekSourceTime ?? seg.clip.trim_start
    if (!videoRef.current) return

    const applySeek = () => {
      videoRef.current.currentTime = targetTime
      videoRef.current.playbackRate = seg.clip.speed_factor || 1
      if (playAfter) videoRef.current.play().catch(() => {})
    }

    if (loadedUrlRef.current !== url) {
      loadedUrlRef.current = url
      pendingSeekRef.current = { time: targetTime, play: playAfter }
      videoRef.current.src = url
    } else {
      applySeek()
    }
  }, [segments])

  const handleLoadedMeta = () => {
    if (pendingSeekRef.current && videoRef.current) {
      const { time, play } = pendingSeekRef.current
      videoRef.current.currentTime = time
      videoRef.current.playbackRate = activeSeg?.clip.speed_factor || 1
      if (play) videoRef.current.play().catch(() => {})
      pendingSeekRef.current = null
    }
  }

  const handleTimeUpdate = () => {
    if (!activeSeg || activeSeg.isPhoto || !videoRef.current) return
    const local = videoRef.current.currentTime - activeSeg.clip.trim_start
    const global = activeSeg.start + local / (activeSeg.clip.speed_factor || 1)
    setPlayhead(global)
    const localEnd = activeSeg.clip.trim_end
    if (localEnd != null && videoRef.current.currentTime >= localEnd - 0.05) {
      loadSegment(activeIndex + 1, null, isPlaying)
    }
  }

  const togglePlay = () => {
    if (isPlaying) {
      setIsPlaying(false)
      videoRef.current?.pause()
      clearTimeout(photoTimerRef.current)
    } else {
      setIsPlaying(true)
      if (!activeSeg) return
      if (activeSeg.isPhoto) {
        const remaining = Math.max(0.05, activeSeg.end - playhead)
        photoTimerRef.current = setTimeout(() => loadSegment(activeIndex + 1, null, true), remaining * 1000)
      } else {
        videoRef.current?.play().catch(() => {})
      }
    }
  }

  const scrubTo = useCallback((t) => {
    const target = Math.max(0, Math.min(t, totalDuration))
    clearTimeout(photoTimerRef.current)
    const idx = segments.findIndex((s) => target >= s.start && target < s.end)
    const targetIdx = idx === -1 ? Math.max(0, segments.length - 1) : idx
    const seg = segments[targetIdx]
    setPlayhead(target)
    if (!seg) return
    if (seg.isPhoto) {
      setActiveIndex(targetIdx)
      if (isPlaying) {
        const remaining = Math.max(0.05, seg.end - target)
        photoTimerRef.current = setTimeout(() => loadSegment(targetIdx + 1, null, true), remaining * 1000)
      }
    } else {
      const localTime = seg.clip.trim_start + (target - seg.start) * (seg.clip.speed_factor || 1)
      loadSegment(targetIdx, localTime, isPlaying)
    }
  }, [segments, totalDuration, isPlaying, loadSegment])

  useImperativeHandle(ref, () => ({
    scrubTo,
    getPlayhead: () => playheadRef.current,
    previewClipAt(clipId, sourceTime) {
      const idx = segments.findIndex((s) => s.clip.id === clipId)
      if (idx === -1) return
      setIsPlaying(false)
      clearTimeout(photoTimerRef.current)
      loadSegment(idx, sourceTime, false)
    },
    jumpToClipStart(clipId) {
      const idx = segments.findIndex((s) => s.clip.id === clipId)
      if (idx === -1) return
      const seg = segments[idx]
      setPlayhead(seg.start)
      loadSegment(idx, null, false)
    },
  }), [segments, loadSegment])

  return (
    <div style={{
      position: 'sticky', top: 0, zIndex: 5, background: 'var(--bg-0)',
      paddingBottom: '0.6rem', marginBottom: '0.6rem', borderBottom: '1px solid var(--border-soft)',
    }}>
      <div style={{
        background: '#000', borderRadius: 'var(--radius-md)', overflow: 'hidden',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        minHeight: 220, maxHeight: 340,
      }}>
        {segments.length === 0 ? (
          <p className="sub" style={{ padding: '2rem' }}>Add clips below to see them here.</p>
        ) : activeSeg?.isPhoto ? (
          <img
            src={mediaApi.fileUrl(activeSeg.clip.media_id, activeSeg.clip.media.current_filename)}
            alt=""
            style={{ maxWidth: '100%', maxHeight: 340, objectFit: 'contain' }}
          />
        ) : (
          <video
            ref={videoRef}
            onLoadedMetadata={handleLoadedMeta}
            onTimeUpdate={handleTimeUpdate}
            style={{ width: '100%', maxHeight: 340 }}
          />
        )}
      </div>

      {segments.length > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginTop: '0.5rem' }}>
          <button className="btn btn-ghost" style={{ padding: '0.4rem' }} onClick={togglePlay}>
            {isPlaying ? <Pause size={16} /> : <Play size={16} />}
          </button>
          <input
            type="range" min="0" max={Math.max(0.1, totalDuration)} step="0.05" value={playhead}
            onChange={(e) => scrubTo(parseFloat(e.target.value))}
            style={{ flex: 1 }}
          />
          <span className="sub" style={{ fontSize: '0.78rem', width: 90, textAlign: 'right' }}>
            {fmt(playhead)} / {fmt(totalDuration)}
          </span>
        </div>
      )}
    </div>
  )
})

export default function Timeline() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [project, setProject] = useState(null)
  const [library, setLibrary] = useState([])
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [renderProgress, setRenderProgress] = useState(0)
  const [dragClipIndex, setDragClipIndex] = useState(null)
  const [editingClipId, setEditingClipId] = useState(null)
  const [sourceDuration, setSourceDuration] = useState(null) // real duration of the selected clip's source file
  const [liveTrim, setLiveTrim] = useState(null) // { trimStart, trimEnd } while dragging a handle
  const [insertAtPosition, setInsertAtPosition] = useState(null)
  const fileInputRef = useRef(null)
  const musicInputRef = useRef(null)
  const pollRef = useRef(null)
  const previewRef = useRef(null)
  const resizingRef = useRef(false)

  const loadAll = useCallback(async () => {
    try {
      const [projRes, mediaRes] = await Promise.all([projectApi.get(id), mediaApi.list()])
      setProject(projRes.data)
      setLibrary(mediaRes.data)
    } catch (err) {
      setError('Could not load this project')
    }
  }, [id])

  useEffect(() => {
    loadAll()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [loadAll])

  const segments = useMemo(() => (project ? buildSegments(project.clips) : []), [project])
  const totalDuration = segments.length ? segments[segments.length - 1].end : 0
  const editingClip = project?.clips.find((c) => c.id === editingClipId) || null

  // The backend now always returns a concrete trim_end and the source file's
  // real duration_seconds, so there's no async probing needed here — this
  // just resets the drag-state snapshot whenever the selected clip changes.
  useEffect(() => {
    if (!editingClip || editingClip.media.media_type !== 'video') {
      setSourceDuration(null)
      setLiveTrim(null)
      return
    }
    setSourceDuration(editingClip.media.duration_seconds ?? editingClip.trim_end ?? null)
    setLiveTrim({ trimStart: editingClip.trim_start || 0, trimEnd: editingClip.trim_end })
  }, [editingClipId, editingClip])

  const handleUpload = async (e) => {
    const chosenFiles = Array.from(e.target.files || [])
    if (chosenFiles.length === 0) return
    setUploading(true)
    setError('')
    try {
      for (const file of chosenFiles) await mediaApi.upload(file)
      await loadAll()
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handlePickFromLibrary = async (mediaId) => {
    setError('')
    try {
      let res
      if (insertAtPosition !== null) {
        res = await projectApi.insertClip(id, { media_id: mediaId, position: insertAtPosition })
        setInsertAtPosition(null)
      } else {
        res = await projectApi.addClip(id, { media_id: mediaId })
      }
      setProject(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not add clip')
    }
  }

  const handleRemoveClip = async (clipId) => {
    const res = await projectApi.removeClip(id, clipId)
    setProject(res.data)
    if (editingClipId === clipId) setEditingClipId(null)
  }

  const handleTransitionChange = async (clip, value) => {
    const res = await projectApi.updateClip(id, clip.id, {
      media_id: clip.media_id, trim_start: clip.trim_start, trim_end: clip.trim_end,
      photo_duration_seconds: clip.photo_duration_seconds, transition_out: value,
      transition_duration: clip.transition_duration, speed_factor: clip.speed_factor,
    })
    setProject(res.data)
  }

  const handleSpeedChange = async (clip, speed) => {
    const res = await projectApi.updateClip(id, clip.id, {
      media_id: clip.media_id, trim_start: clip.trim_start, trim_end: clip.trim_end,
      photo_duration_seconds: clip.photo_duration_seconds, transition_out: clip.transition_out,
      transition_duration: clip.transition_duration, speed_factor: speed,
    })
    setProject(res.data)
  }

  const handleDurationChange = async (clip, seconds) => {
    const res = await projectApi.updateClip(id, clip.id, {
      media_id: clip.media_id, trim_start: clip.trim_start, trim_end: clip.trim_end,
      photo_duration_seconds: seconds, transition_out: clip.transition_out,
      transition_duration: clip.transition_duration, speed_factor: clip.speed_factor,
    })
    setProject(res.data)
  }

  const handleSelectClip = (clip) => {
    if (editingClipId === clip.id) {
      setEditingClipId(null)
    } else {
      setEditingClipId(clip.id)
      previewRef.current?.jumpToClipStart(clip.id)
    }
  }

  const handleSplitAtPlayhead = async () => {
    if (!editingClip) return
    const globalPlayhead = previewRef.current?.getPlayhead()
    const seg = segments.find((s) => s.clip.id === editingClip.id)
    if (!seg || globalPlayhead == null) return
    const speed = editingClip.speed_factor || 1
    const localSourceSeconds = (globalPlayhead - seg.start) * speed
    if (localSourceSeconds <= 0.15 || localSourceSeconds >= seg.duration * speed - 0.15) {
      setError('Move the playhead inside this clip first, then split')
      return
    }
    setError('')
    try {
      await projectApi.splitClip(id, editingClip.id, localSourceSeconds)
      await loadAll()
      setEditingClipId(null)
    } catch (e) {
      setError(e.response?.data?.detail || 'Could not split')
    }
  }

  // --- Drag a clip's edge to trim it directly on the filmstrip ---
  const startTrimDrag = (side, e) => {
    e.stopPropagation()
    e.preventDefault()
    if (!editingClip || !liveTrim) return
    resizingRef.current = true
    const startX = e.clientX
    const speed = editingClip.speed_factor || 1
    let current = { ...liveTrim }

    const onMove = (ev) => {
      const deltaSourceSec = ((ev.clientX - startX) / PX_PER_SECOND) * speed
      if (side === 'left') {
        const newStart = Math.max(0, Math.min(liveTrim.trimStart + deltaSourceSec, current.trimEnd - 0.5))
        current = { ...current, trimStart: newStart }
        previewRef.current?.previewClipAt(editingClip.id, newStart)
      } else {
        const ceiling = sourceDuration ?? current.trimEnd
        const newEnd = Math.min(ceiling, Math.max(liveTrim.trimEnd + deltaSourceSec, current.trimStart + 0.5))
        current = { ...current, trimEnd: newEnd }
        previewRef.current?.previewClipAt(editingClip.id, newEnd)
      }
      setLiveTrim(current)
    }
    const onUp = async () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      resizingRef.current = false
      try {
        const res = await projectApi.updateClip(id, editingClip.id, {
          media_id: editingClip.media_id,
          trim_start: current.trimStart,
          trim_end: current.trimEnd,
          photo_duration_seconds: editingClip.photo_duration_seconds,
          transition_out: editingClip.transition_out,
          transition_duration: editingClip.transition_duration,
          speed_factor: editingClip.speed_factor,
        })
        setProject(res.data)
      } catch (err) {
        setError('Could not save the trim')
      }
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const handleDragStart = (index) => setDragClipIndex(index)
  const handleDragOver = (e) => e.preventDefault()
  const handleDrop = async (index) => {
    if (dragClipIndex === null || dragClipIndex === index) return
    const clips = [...project.clips]
    const [moved] = clips.splice(dragClipIndex, 1)
    clips.splice(index, 0, moved)
    setProject({ ...project, clips })
    setDragClipIndex(null)
    try {
      const res = await projectApi.reorder(id, clips.map((c) => c.id))
      setProject(res.data)
    } catch (err) {
      loadAll()
    }
  }

  const handleSetMusic = async (mediaId) => {
    const res = await projectApi.setMusic(id, mediaId, project.music_volume || 100)
    setProject(res.data)
  }

  const handleMusicUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const res = await mediaApi.upload(file)
      await loadAll()
      await handleSetMusic(res.data.id)
    } catch (err) {
      setError('Music upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleVolumeChange = async (volume) => {
    setProject({ ...project, music_volume: volume })
    if (project.music_media_id) await projectApi.setMusic(id, project.music_media_id, volume)
  }

  const handleRemoveMusic = async () => {
    const res = await projectApi.removeMusic(id)
    setProject(res.data)
  }

  const handleRender = async () => {
    setError('')
    setRendering(true)
    setRenderProgress(0)
    try {
      const res = await projectApi.render(id)
      const jobId = res.data.job_id
      pollRef.current = setInterval(async () => {
        try {
          const statusRes = await projectApi.renderStatus(jobId)
          const status = statusRes.data
          setRenderProgress(status.progress || 0)
          if (status.status === 'done') {
            clearInterval(pollRef.current)
            setRendering(false)
            await loadAll()
          } else if (status.status === 'failed') {
            clearInterval(pollRef.current)
            setRendering(false)
            setError(status.error || 'Render failed')
          }
        } catch (pollErr) {
          clearInterval(pollRef.current)
          setRendering(false)
          setError('Lost track of the render job — try again')
        }
      }, 1500)
    } catch (err) {
      setRendering(false)
      setError(err.response?.data?.detail || 'Could not start render')
    }
  }

  if (!project) {
    return (
      <div className="app-shell">
        <TopBar />
        <div className="loading-screen">Loading…</div>
      </div>
    )
  }

  const musicItem = library.find((m) => m.id === project.music_media_id)

  const InsertSlot = ({ position }) => (
    insertAtPosition === position ? (
      <button className="btn btn-ghost" style={{ padding: '0.2rem', flexShrink: 0, alignSelf: 'center' }} onClick={() => setInsertAtPosition(null)}>
        <X size={12} />
      </button>
    ) : (
      <button
        className="btn btn-ghost"
        style={{ padding: '0.2rem', flexShrink: 0, alignSelf: 'center' }}
        onClick={() => setInsertAtPosition(position)}
        title="Insert a clip here"
      >
        <Plus size={12} />
      </button>
    )
  )

  return (
    <div className="app-shell">
      <TopBar
        right={
          <button className="btn btn-ghost" onClick={() => navigate('/')}>
            <ArrowLeft size={16} />
            Back to projects
          </button>
        }
      />

      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        <div style={{
          width: 240, borderRight: '1px solid var(--border-soft)', padding: '1rem',
          display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ fontSize: '0.95rem' }}>Your media</h3>
            <button className="btn btn-ghost" style={{ padding: '0.35rem' }} onClick={() => fileInputRef.current?.click()} disabled={uploading}>
              <Upload size={15} />
            </button>
            <input ref={fileInputRef} type="file" accept="image/*,video/*" multiple style={{ display: 'none' }} onChange={handleUpload} />
          </div>
          {insertAtPosition !== null && (
            <div className="error-banner" style={{ fontSize: '0.78rem' }}>Click a clip below to insert it there.</div>
          )}
          {uploading && <p className="sub">Uploading…</p>}
          {library.filter((m) => m.media_type !== 'audio').map((m) => (
            <div key={m.id} style={{
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden',
              cursor: 'pointer', background: 'var(--bg-2)',
            }} onClick={() => handlePickFromLibrary(m.id)} title="Click to add to timeline">
              <div style={{ position: 'relative', aspectRatio: '16/9', background: '#000' }}>
                {m.media_type === 'photo' ? (
                  <img src={mediaApi.fileUrl(m.id, m.current_filename)} alt={m.original_filename} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : m.thumbnail_filename ? (
                  <img src={mediaApi.thumbnailUrl(m.id)} alt={m.original_filename} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <video src={mediaApi.fileUrl(m.id, m.current_filename)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                )}
                <span className="type-badge" style={{ position: 'absolute', top: 6, left: 6 }}>
                  {m.media_type === 'video' ? <Film size={11} /> : <ImageIcon size={11} />}
                </span>
              </div>
              <div style={{ padding: '0.4rem 0.5rem', fontSize: '0.78rem', color: 'var(--text-mid)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {m.original_filename}
              </div>
            </div>
          ))}
        </div>

        <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto' }}>
          <SequencePreview ref={previewRef} segments={segments} totalDuration={totalDuration} />

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.6rem' }}>
            <div>
              <h1 style={{ fontSize: '1.3rem' }}>{project.name}</h1>
              <p className="sub">{project.clips.length} clip{project.clips.length !== 1 ? 's' : ''} · {fmt(totalDuration)} total</p>
            </div>
            <button className="btn btn-primary" onClick={handleRender} disabled={rendering || project.clips.length === 0}>
              <Play size={16} />
              {rendering ? `Rendering… ${Math.round(renderProgress * 100)}%` : 'Render video'}
            </button>
          </div>

          {error && <div className="error-banner" style={{ marginBottom: '0.75rem' }}>{error}</div>}

          {project.rendered_filename && !rendering && (
            <div style={{ marginBottom: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                className="btn btn-ghost"
                onClick={() => downloadFile(projectApi.downloadUrl(id), `${project.name || 'project'}.mp4`)}
              >
                <Download size={15} />
                Download rendered video
              </button>
            </div>
          )}

          {project.clips.length === 0 && (
            <div className="empty-state">
              <p>Click any item in "Your media" on the left to add it to this timeline.</p>
            </div>
          )}

          {/* Compact icon-first toolbar for whatever's selected — no boxed panel */}
          {editingClip && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.5rem' }}>
              {editingClip.media.media_type === 'photo' ? (
                <>
                  <span className="sub" style={{ fontSize: '0.75rem' }}>Duration</span>
                  <input
                    type="number" min="1" max="60" value={editingClip.photo_duration_seconds}
                    onChange={(e) => handleDurationChange(editingClip, parseInt(e.target.value, 10) || 3)}
                    style={{ width: 44, background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-hi)', padding: '0.15rem 0.3rem', fontSize: '0.78rem' }}
                  />
                  <span className="sub" style={{ fontSize: '0.75rem' }}>s</span>
                </>
              ) : (
                <>
                  <select
                    value={editingClip.transition_out}
                    onChange={(e) => handleTransitionChange(editingClip, e.target.value)}
                    title="Transition after this clip"
                    style={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-mid)', fontSize: '0.76rem', padding: '0.2rem 0.4rem' }}
                  >
                    {TRANSITIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                  <select
                    value={editingClip.speed_factor}
                    onChange={(e) => handleSpeedChange(editingClip, parseFloat(e.target.value))}
                    title="Speed"
                    style={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-mid)', fontSize: '0.76rem', padding: '0.2rem 0.4rem' }}
                  >
                    {SPEEDS.map((s) => <option key={s} value={s}>{s}x</option>)}
                  </select>
                  <button className="btn btn-ghost" style={{ padding: '0.25rem 0.5rem', fontSize: '0.76rem' }} onClick={handleSplitAtPlayhead} title="Split at playhead">
                    <Scissors size={13} />
                  </button>
                </>
              )}
            </div>
          )}

          {/* Horizontal filmstrip — drag edges of the selected clip to trim */}
          <div style={{ display: 'flex', alignItems: 'stretch', gap: '0.3rem', overflowX: 'auto', paddingBottom: '0.6rem' }}>
            <InsertSlot position={0} />
            {project.clips.map((clip, index) => {
              const seg = segments[index]
              const isSelected = editingClipId === clip.id
              const displayDuration = isSelected && liveTrim && liveTrim.trimEnd != null
                ? (liveTrim.trimEnd - liveTrim.trimStart) / (clip.speed_factor || 1)
                : (seg?.duration || 3)
              const widthPx = Math.max(64, displayDuration * PX_PER_SECOND)
              return (
                <React.Fragment key={clip.id}>
                  <div
                    draggable={!isSelected}
                    onDragStart={() => handleDragStart(index)}
                    onDragOver={handleDragOver}
                    onDrop={() => handleDrop(index)}
                    onClick={() => handleSelectClip(clip)}
                    title={clip.media.original_filename}
                    style={{
                      width: widthPx, flexShrink: 0, borderRadius: 6, overflow: 'hidden', position: 'relative',
                      border: isSelected ? '2px solid var(--accent)' : '1px solid var(--border)',
                      cursor: 'pointer', background: '#000', height: 64,
                      opacity: dragClipIndex === index ? 0.5 : 1,
                    }}
                  >
                    {clip.media.media_type === 'photo' ? (
                      <img src={mediaApi.fileUrl(clip.media.id, clip.media.current_filename)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : clip.media.thumbnail_filename ? (
                      <img src={mediaApi.thumbnailUrl(clip.media.id)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <video src={mediaApi.fileUrl(clip.media.id, clip.media.current_filename)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    )}
                    <span style={{ position: 'absolute', bottom: 2, left: 4, fontSize: 10, color: '#fff', background: 'rgba(0,0,0,0.55)', padding: '0 4px', borderRadius: 3 }}>
                      {fmt(displayDuration)}
                    </span>
                    <button
                      className="btn btn-danger"
                      style={{ position: 'absolute', top: 2, right: 2, padding: '0.15rem' }}
                      onClick={(e) => { e.stopPropagation(); handleRemoveClip(clip.id) }}
                    >
                      <Trash2 size={11} />
                    </button>

                    {isSelected && clip.media.media_type === 'video' && (
                      <>
                        <div
                          onMouseDown={(e) => startTrimDrag('left', e)}
                          style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: 9, cursor: 'ew-resize', background: 'var(--accent)' }}
                        />
                        <div
                          onMouseDown={(e) => startTrimDrag('right', e)}
                          style={{ position: 'absolute', right: 0, top: 0, bottom: 0, width: 9, cursor: 'ew-resize', background: 'var(--accent)' }}
                        />
                      </>
                    )}
                  </div>
                  <InsertSlot position={index + 1} />
                </React.Fragment>
              )
            })}
          </div>

          {/* Music */}
          <div style={{ marginTop: '1.5rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '1rem', background: 'var(--bg-2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <Music size={16} />
              <strong>Background music</strong>
            </div>
            {musicItem ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', flex: 1 }}>{musicItem.original_filename}</span>
                <span className="sub" style={{ fontSize: '0.75rem' }}>Volume</span>
                <input type="range" min="0" max="200" value={project.music_volume} onChange={(e) => handleVolumeChange(parseInt(e.target.value, 10))} />
                <span className="sub" style={{ fontSize: '0.75rem', width: 34 }}>{project.music_volume}%</span>
                <button className="btn btn-ghost" style={{ padding: '0.3rem' }} onClick={handleRemoveMusic}><X size={14} /></button>
              </div>
            ) : (
              <div>
                <button className="btn btn-ghost" onClick={() => musicInputRef.current?.click()} disabled={uploading}>
                  <Upload size={14} />
                  Upload audio track
                </button>
                <input ref={musicInputRef} type="file" accept="audio/*" style={{ display: 'none' }} onChange={handleMusicUpload} />
                {library.filter((m) => m.media_type === 'audio').length > 0 && (
                  <div style={{ marginTop: '0.6rem', display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                    <span className="sub" style={{ fontSize: '0.75rem' }}>Or pick a track you've already uploaded:</span>
                    {library.filter((m) => m.media_type === 'audio').map((m) => (
                      <button key={m.id} className="btn btn-ghost" style={{ justifyContent: 'flex-start' }} onClick={() => handleSetMusic(m.id)}>
                        <Music size={13} />
                        {m.original_filename}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}