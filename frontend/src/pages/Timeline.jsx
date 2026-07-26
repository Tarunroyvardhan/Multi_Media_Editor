import React, { useEffect, useRef, useState, useCallback } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  Upload, Film, Image as ImageIcon, Trash2, Music, Play, Download,
  GripVertical, ArrowLeft, X,
} from 'lucide-react'
import TopBar from '../components/TopBar'
import { mediaApi, projectApi } from '../api/client'

const TRANSITIONS = [
  { value: 'none', label: 'Cut (no transition)' },
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

export default function Timeline() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [project, setProject] = useState(null)
  const [library, setLibrary] = useState([])
  const [error, setError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [renderProgress, setRenderProgress] = useState(0)
  const [dragIndex, setDragIndex] = useState(null)
  const fileInputRef = useRef(null)
  const musicInputRef = useRef(null)
  const pollRef = useRef(null)

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
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [loadAll])

  const handleUpload = async (e) => {
    const chosenFiles = Array.from(e.target.files || [])
    if (chosenFiles.length === 0) return
    setUploading(true)
    setError('')
    try {
      for (const file of chosenFiles) {
        await mediaApi.upload(file)
      }
      await loadAll()
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleAddClip = async (mediaId) => {
    setError('')
    try {
      const res = await projectApi.addClip(id, { media_id: mediaId })
      setProject(res.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not add clip')
    }
  }

  const handleRemoveClip = async (clipId) => {
    const res = await projectApi.removeClip(id, clipId)
    setProject(res.data)
  }

  const handleTransitionChange = async (clip, value) => {
    const res = await projectApi.updateClip(id, clip.id, {
      media_id: clip.media_id,
      trim_start: clip.trim_start,
      trim_end: clip.trim_end,
      photo_duration_seconds: clip.photo_duration_seconds,
      transition_out: value,
      transition_duration: clip.transition_duration,
    })
    setProject(res.data)
  }

  const handleDurationChange = async (clip, seconds) => {
    const res = await projectApi.updateClip(id, clip.id, {
      media_id: clip.media_id,
      trim_start: clip.trim_start,
      trim_end: clip.trim_end,
      photo_duration_seconds: seconds,
      transition_out: clip.transition_out,
      transition_duration: clip.transition_duration,
    })
    setProject(res.data)
  }

  // --- Drag to reorder ---
  const handleDragStart = (index) => setDragIndex(index)
  const handleDragOver = (e, index) => {
    e.preventDefault()
    if (dragIndex === null || dragIndex === index) return
  }
  const handleDrop = async (index) => {
    if (dragIndex === null || dragIndex === index) return
    const clips = [...project.clips]
    const [moved] = clips.splice(dragIndex, 1)
    clips.splice(index, 0, moved)
    setProject({ ...project, clips })
    setDragIndex(null)
    try {
      const res = await projectApi.reorder(id, clips.map((c) => c.id))
      setProject(res.data)
    } catch (err) {
      loadAll() // reorder failed server-side, resync
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
    if (project.music_media_id) {
      await projectApi.setMusic(id, project.music_media_id, volume)
    }
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
  const totalRoughSeconds = project.clips.reduce((sum, c) => {
    const dur = c.media.media_type === 'photo'
      ? c.photo_duration_seconds
      : (c.trim_end ?? 10) - (c.trim_start ?? 0)
    return sum + dur
  }, 0)

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
        {/* Sidebar: all uploaded media */}
        <div style={{
          width: 260, borderRight: '1px solid var(--border-soft)', padding: '1rem',
          display: 'flex', flexDirection: 'column', gap: '0.75rem', overflowY: 'auto',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ fontSize: '0.95rem' }}>Your media</h3>
            <button className="btn btn-ghost" style={{ padding: '0.35rem' }} onClick={() => fileInputRef.current?.click()} disabled={uploading}>
              <Upload size={15} />
            </button>
            <input ref={fileInputRef} type="file" accept="image/*,video/*" multiple style={{ display: 'none' }} onChange={handleUpload} />
          </div>
          {uploading && <p className="sub">Uploading…</p>}
          {library.length === 0 && <p className="sub">No media yet — upload photos or videos to build your timeline.</p>}
          {library.map((m) => (
            <div key={m.id} style={{
              border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', overflow: 'hidden',
              cursor: 'pointer', background: 'var(--bg-2)',
            }} onClick={() => handleAddClip(m.id)} title="Click to add to timeline">
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

        {/* Main: timeline */}
        <div style={{ flex: 1, padding: '1.5rem', overflowY: 'auto' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
            <div>
              <h1 style={{ fontSize: '1.3rem' }}>{project.name}</h1>
              <p className="sub">{project.clips.length} clip{project.clips.length !== 1 ? 's' : ''} · roughly {Math.round(totalRoughSeconds)}s before transitions</p>
            </div>
            <button className="btn btn-primary" onClick={handleRender} disabled={rendering || project.clips.length === 0}>
              <Play size={16} />
              {rendering ? `Rendering… ${Math.round(renderProgress * 100)}%` : 'Render video'}
            </button>
          </div>

          {error && <div className="error-banner" style={{ marginBottom: '1rem' }}>{error}</div>}

          {project.rendered_filename && !rendering && (
            <div style={{ marginBottom: '1.5rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '1rem', background: 'var(--bg-2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
                <strong>Rendered output</strong>
                <a className="btn btn-ghost" href={projectApi.downloadUrl(id)} download>
                  <Download size={15} />
                  Download
                </a>
              </div>
              <video src={projectApi.downloadUrl(id)} controls style={{ width: '100%', maxHeight: 360, borderRadius: 'var(--radius-sm)' }} />
            </div>
          )}

          {project.clips.length === 0 && (
            <div className="empty-state">
              <p>Click any item in "Your media" on the left to add it to this timeline.</p>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {project.clips.map((clip, index) => (
              <React.Fragment key={clip.id}>
                <div
                  draggable
                  onDragStart={() => handleDragStart(index)}
                  onDragOver={(e) => handleDragOver(e, index)}
                  onDrop={() => handleDrop(index)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.75rem',
                    border: '1px solid var(--border)', borderRadius: 'var(--radius-md)',
                    padding: '0.6rem', background: 'var(--bg-2)',
                    opacity: dragIndex === index ? 0.5 : 1,
                  }}
                >
                  <GripVertical size={16} color="var(--text-low)" style={{ cursor: 'grab', flexShrink: 0 }} />
                  <div style={{ width: 90, height: 56, flexShrink: 0, borderRadius: 6, overflow: 'hidden', background: '#000' }}>
                    {clip.media.media_type === 'photo' ? (
                      <img src={mediaApi.fileUrl(clip.media.id, clip.media.current_filename)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : clip.media.thumbnail_filename ? (
                      <img src={mediaApi.thumbnailUrl(clip.media.id)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <video src={mediaApi.fileUrl(clip.media.id, clip.media.current_filename)} muted style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    )}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {clip.media.original_filename}
                    </div>
                    {clip.media.media_type === 'photo' && (
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginTop: '0.3rem' }}>
                        <span className="sub" style={{ fontSize: '0.75rem' }}>Duration:</span>
                        <input
                          type="number" min="1" max="60" value={clip.photo_duration_seconds}
                          onChange={(e) => handleDurationChange(clip, parseInt(e.target.value, 10) || 3)}
                          style={{ width: 50, background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 4, color: 'var(--text-hi)', padding: '0.15rem 0.3rem' }}
                        />
                        <span className="sub" style={{ fontSize: '0.75rem' }}>sec</span>
                      </div>
                    )}
                  </div>
                  <button className="btn btn-danger" style={{ padding: '0.4rem' }} onClick={() => handleRemoveClip(clip.id)}>
                    <Trash2 size={14} />
                  </button>
                </div>

                {index < project.clips.length - 1 && (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '0.15rem 0' }}>
                    <select
                      value={clip.transition_out}
                      onChange={(e) => handleTransitionChange(clip, e.target.value)}
                      style={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 6, color: 'var(--text-mid)', fontSize: '0.78rem', padding: '0.25rem 0.5rem' }}
                    >
                      {TRANSITIONS.map((t) => (
                        <option key={t.value} value={t.value}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>

          {/* Music */}
          <div style={{ marginTop: '2rem', border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: '1rem', background: 'var(--bg-2)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <Music size={16} />
              <strong>Background music</strong>
            </div>
            {musicItem ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ fontSize: '0.85rem', flex: 1 }}>{musicItem.original_filename}</span>
                <span className="sub" style={{ fontSize: '0.75rem' }}>Volume</span>
                <input
                  type="range" min="0" max="200" value={project.music_volume}
                  onChange={(e) => handleVolumeChange(parseInt(e.target.value, 10))}
                />
                <span className="sub" style={{ fontSize: '0.75rem', width: 34 }}>{project.music_volume}%</span>
                <button className="btn btn-ghost" style={{ padding: '0.3rem' }} onClick={handleRemoveMusic}>
                  <X size={14} />
                </button>
              </div>
            ) : (
              <div>
                <button className="btn btn-ghost" onClick={() => musicInputRef.current?.click()} disabled={uploading}>
                  <Upload size={14} />
                  Upload audio track
                </button>
                <input ref={musicInputRef} type="file" accept="audio/*" style={{ display: 'none' }} onChange={handleMusicUpload} />
                {library.filter((m) => m.media_type !== 'photo' && m.media_type !== 'video').length > 0 && null}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
