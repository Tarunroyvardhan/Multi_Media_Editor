import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Upload, Film, Image as ImageIcon, Pencil, Trash2, FolderOpen, Clapperboard } from 'lucide-react'
import TopBar from '../components/TopBar'
import { mediaApi, projectApi } from '../api/client'

function formatDate(iso) {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function Dashboard() {
  const [files, setFiles] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [modalOpen, setModalOpen] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef(null)
  const navigate = useNavigate()

  const loadFiles = async () => {
    try {
      const res = await mediaApi.list()
      setFiles(res.data)
    } catch (err) {
      setError('Could not load your files')
    } finally {
      setLoaded(true)
    }
  }

  useEffect(() => {
    loadFiles()
  }, [])

  const handleFileChosen = async (e) => {
    const chosenFiles = Array.from(e.target.files || [])
    if (chosenFiles.length === 0) return
    setUploading(true)
    setError('')
    try {
      let lastId = null
      for (const file of chosenFiles) {
        const res = await mediaApi.upload(file)
        lastId = res.data.id
      }
      await loadFiles()
      setModalOpen(false)
      // Single file: jump straight into the editor. Multiple files: stay on
      // the dashboard so the person can see everything land in the grid,
      // then send them into a timeline project instead.
      if (chosenFiles.length === 1) {
        navigate(`/editor/${lastId}`)
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Upload failed')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleNewProject = async () => {
    setError('')
    try {
      const res = await projectApi.create('Untitled project')
      navigate(`/timeline/${res.data.id}`)
    } catch (err) {
      setError('Could not create a new project')
    }
  }

  const handleDelete = async (e, id) => {
    e.stopPropagation()
    await mediaApi.remove(id)
    await loadFiles()
  }

  return (
    <div className="app-shell">
      <TopBar
        right={
          <div style={{ display: 'flex', gap: '0.6rem' }}>
            <button className="btn btn-ghost" onClick={handleNewProject}>
              <Clapperboard size={16} />
              Merge Video
            </button>
            <button className="btn btn-primary" onClick={() => setModalOpen(true)}>
              <Upload size={16} />
              Upload &amp; edit
            </button>
          </div>
        }
      />

      <div className="home">
        <div className="home-header">
          <div>
            <h1>Your projects</h1>
            <p className="sub">Upload a photo or video to start editing.</p>
          </div>
        </div>

        {error && <div className="error-banner">{error}</div>}

        {loaded && files.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">
              <FolderOpen size={24} color="var(--text-mid)" />
            </div>
            <h3>Nothing here yet</h3>
            <p>Upload your first photo or video to start editing.</p>
            <button className="btn btn-primary" onClick={() => setModalOpen(true)}>
              <Upload size={16} />
              Upload &amp; edit
            </button>
          </div>
        )}

        {files.length > 0 && (
          <div className="project-grid">
            {files.map((f) => (
              <div className="project-card" key={f.id} onClick={() => navigate(`/editor/${f.id}`)}>
                <div className="project-thumb">
                  <span className="type-badge">
                    {f.media_type === 'video' ? <Film size={11} /> : <ImageIcon size={11} />}
                  </span>
                  {f.media_type === 'photo' ? (
                    <img src={mediaApi.fileUrl(f.id, f.current_filename)} alt={f.original_filename} />
                  ) : f.thumbnail_filename ? (
                    <img src={mediaApi.thumbnailUrl(f.id)} alt={f.original_filename} />
                  ) : (
                    <video src={mediaApi.fileUrl(f.id, f.current_filename)} muted />
                  )}
                </div>
                <div className="project-meta">
                  <span className="name">{f.original_filename}</span>
                  <span className="date">{formatDate(f.created_at)}</span>
                </div>
                <div className="project-card-actions">
                  <button className="btn btn-ghost" onClick={() => navigate(`/editor/${f.id}`)}>
                    <Pencil size={13} />
                    Edit
                  </button>
                  <button className="btn btn-danger" onClick={(e) => handleDelete(e, f.id)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="modal-overlay" onClick={() => !uploading && setModalOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Upload files</h3>
            <p className="sub">Photos and videos are both supported — select more than one to add them all at once.</p>
            <div className="dropzone" onClick={() => fileInputRef.current?.click()}>
              {uploading ? 'Uploading…' : 'Click to choose photos or videos'}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*,video/*"
                multiple
                onChange={handleFileChosen}
                style={{ display: 'none' }}
                disabled={uploading}
              />
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setModalOpen(false)} disabled={uploading}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}