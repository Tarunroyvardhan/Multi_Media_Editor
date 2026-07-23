import React, { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Scissors, Crop, SlidersHorizontal, Download, Eraser, MousePointerClick, Square, Loader2, RotateCw, FlipHorizontal2, FlipVertical2, Maximize2, Gauge, Volume2, VolumeX, Type } from 'lucide-react'
import TopBar from '../components/TopBar'
import { mediaApi } from '../api/client'

const FILTERS = [
  { id: 'grayscale', label: 'Grayscale' },
  { id: 'brightness', label: 'Brightness' },
  { id: 'contrast', label: 'Contrast' },
  { id: 'blur', label: 'Blur' },
  { id: 'sepia', label: 'Sepia' },
  { id: 'saturation', label: 'Saturation' },
  { id: 'sharpen', label: 'Sharpen' },
]

function formatTime(seconds) {
  const s = Math.max(0, Math.floor(seconds))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, '0')}`
}

export default function Editor() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [media, setMedia] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [tool, setTool] = useState('crop')

  // trim
  const [duration, setDuration] = useState(0)
  const [start, setStart] = useState(0)
  const [end, setEnd] = useState(0)
  const trackRef = useRef(null)
  const draggingRef = useRef(null)

  // crop
  const [x, setX] = useState(0)
  const [y, setY] = useState(0)
  const [width, setWidth] = useState(200)
  const [height, setHeight] = useState(200)

  // filter
  const [filterName, setFilterName] = useState('grayscale')
  const [intensity, setIntensity] = useState(1.0)

  // resize
  const [resizeWidth, setResizeWidth] = useState(640)
  const [resizeHeight, setResizeHeight] = useState(480)

  // speed / volume (video)
  const [speedFactor, setSpeedFactor] = useState(1.0)
  const [volumeLevel, setVolumeLevel] = useState(1.0)
  const [volumeMute, setVolumeMute] = useState(false)

  // watermark
  const [watermarkText, setWatermarkText] = useState('')
  const [watermarkX, setWatermarkX] = useState(10)
  const [watermarkY, setWatermarkY] = useState(10)
  const [watermarkFontSize, setWatermarkFontSize] = useState(32)
  const [watermarkColor, setWatermarkColor] = useState('#FFFFFF')

  // remove object
  const frameRef = useRef(null)
  const imgRef = useRef(null)
  const [removalMode, setRemovalMode] = useState('point') // point | box
  const [imgBox, setImgBox] = useState(null) // {left, top, width, height} in container px
  const [dragStart, setDragStart] = useState(null)
  const [dragBox, setDragBox] = useState(null) // {x, y, w, h} in container px
  const [maskId, setMaskId] = useState(null)
  const [maskScore, setMaskScore] = useState(null)
  const [maskOverlayUrl, setMaskOverlayUrl] = useState(null)
  const [segmenting, setSegmenting] = useState(false)
  const [videoProcessing, setVideoProcessing] = useState(false)
  const [videoProgress, setVideoProgress] = useState(0)
  const [firstFrameLoading, setFirstFrameLoading] = useState(false)

  const loadMedia = async () => {
    const res = await mediaApi.list()
    const found = res.data.find((f) => f.id === Number(id))
    setMedia(found)
    if (found?.media_type === 'video') setTool('trim')
  }

  useEffect(() => {
    loadMedia()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const runAction = async (action) => {
    setBusy(true)
    setError('')
    try {
      await action()
      await loadMedia()
    } catch (err) {
      setError(err.response?.data?.detail || 'Operation failed')
    } finally {
      setBusy(false)
    }
  }

  const onVideoLoaded = (e) => {
    const d = e.target.duration || 0
    setDuration(d)
    setEnd(d)
  }

  const measureImgBox = () => {
    if (!imgRef.current || !frameRef.current) return
    const imgRect = imgRef.current.getBoundingClientRect()
    const frameRect = frameRef.current.getBoundingClientRect()
    setImgBox({
      left: imgRect.left - frameRect.left,
      top: imgRect.top - frameRect.top,
      width: imgRect.width,
      height: imgRect.height,
    })
  }

  useEffect(() => {
    if (tool !== 'remove') return
    if (media?.media_type === 'video') setFirstFrameLoading(true)
    measureImgBox()
    window.addEventListener('resize', measureImgBox)
    return () => window.removeEventListener('resize', measureImgBox)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tool, media])

  const clearSelection = () => {
    setDragStart(null)
    setDragBox(null)
    setMaskId(null)
    setMaskScore(null)
    setMaskOverlayUrl(null)
  }

  const toImageCoords = (clientX, clientY) => {
    const rect = imgRef.current.getBoundingClientRect()
    const scaleX = imgRef.current.naturalWidth / rect.width
    const scaleY = imgRef.current.naturalHeight / rect.height
    const x = Math.round((clientX - rect.left) * scaleX)
    const y = Math.round((clientY - rect.top) * scaleY)
    return [x, y]
  }

  const runSegment = async (payload) => {
    setSegmenting(true)
    setError('')
    try {
      const apiCall = media.media_type === 'video' ? mediaApi.videoSegment : mediaApi.segment
      const res = await apiCall(media.id, payload)
      setMaskId(res.data.mask_id)
      setMaskScore(res.data.score)
      setMaskOverlayUrl(`data:image/png;base64,${res.data.overlay_png_base64}`)
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not detect that object')
    } finally {
      setSegmenting(false)
    }
  }

  const handleOverlayClick = (e) => {
    if (removalMode !== 'point' || segmenting) return
    const [x, y] = toImageCoords(e.clientX, e.clientY)
    setDragBox(null)
    runSegment({ mode: 'point', points: [[x, y]] })
  }

  const handleOverlayMouseDown = (e) => {
    if (removalMode !== 'box') return
    const frameRect = frameRef.current.getBoundingClientRect()
    setDragStart({ x: e.clientX - frameRect.left, y: e.clientY - frameRect.top })
    setDragBox({ x: e.clientX - frameRect.left, y: e.clientY - frameRect.top, w: 0, h: 0 })
  }

  const handleOverlayMouseMove = (e) => {
    if (!dragStart || removalMode !== 'box') return
    const frameRect = frameRef.current.getBoundingClientRect()
    const curX = e.clientX - frameRect.left
    const curY = e.clientY - frameRect.top
    setDragBox({
      x: Math.min(dragStart.x, curX),
      y: Math.min(dragStart.y, curY),
      w: Math.abs(curX - dragStart.x),
      h: Math.abs(curY - dragStart.y),
    })
  }

  const handleOverlayMouseUp = () => {
    if (!dragStart || removalMode !== 'box') return
    setDragStart(null)
    if (!dragBox || dragBox.w < 8 || dragBox.h < 8) {
      setDragBox(null)
      return
    }
    const [x1, y1] = toImageCoords(
      dragBox.x + frameRef.current.getBoundingClientRect().left,
      dragBox.y + frameRef.current.getBoundingClientRect().top
    )
    const [x2, y2] = toImageCoords(
      dragBox.x + dragBox.w + frameRef.current.getBoundingClientRect().left,
      dragBox.y + dragBox.h + frameRef.current.getBoundingClientRect().top
    )
    runSegment({ mode: 'box', box: [x1, y1, x2, y2] })
  }

  const pollVideoJob = (jobId) =>
    new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const res = await mediaApi.videoRemoveObjectJob(media.id, jobId)
          setVideoProgress(res.data.progress)
          if (res.data.status === 'done') {
            clearInterval(interval)
            resolve()
          } else if (res.data.status === 'failed') {
            clearInterval(interval)
            reject(new Error(res.data.error || 'Video processing failed'))
          }
        } catch (err) {
          clearInterval(interval)
          reject(err)
        }
      }, 2000)
    })

  const applyRemoveObject = async () => {
    if (media.media_type !== 'video') {
      return runAction(async () => {
        await mediaApi.removeObject(media.id, maskId)
        clearSelection()
      })
    }

    setVideoProcessing(true)
    setVideoProgress(0)
    setError('')
    try {
      const res = await mediaApi.videoRemoveObject(media.id, maskId)
      await pollVideoJob(res.data.job_id)
      clearSelection()
      await loadMedia()
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Video processing failed')
    } finally {
      setVideoProcessing(false)
    }
  }

  const startDrag = (handle) => (e) => {
    e.preventDefault()
    draggingRef.current = handle
    window.addEventListener('mousemove', onDrag)
    window.addEventListener('mouseup', stopDrag)
  }

  const onDrag = (e) => {
    if (!trackRef.current || !draggingRef.current || !duration) return
    const rect = trackRef.current.getBoundingClientRect()
    const ratio = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
    const seconds = ratio * duration
    if (draggingRef.current === 'start') {
      setStart(Math.min(seconds, end - 0.1 < 0 ? 0 : end - 0.1))
    } else {
      setEnd(Math.max(seconds, start + 0.1))
    }
  }

  const stopDrag = () => {
    draggingRef.current = null
    window.removeEventListener('mousemove', onDrag)
    window.removeEventListener('mouseup', stopDrag)
  }

  if (!media) {
    return (
      <div className="app-shell">
        <TopBar />
        <div className="loading-screen">Loading…</div>
      </div>
    )
  }

  const startPct = duration ? (start / duration) * 100 : 0
  const endPct = duration ? (end / duration) * 100 : 100

  return (
    <div className="app-shell">
      <TopBar />

      <div className="editor-shell">
        <div className="editor-topbar">
          <div className="left">
            <button className="btn-icon btn" onClick={() => navigate('/')} disabled={videoProcessing}>
              <ArrowLeft size={16} />
            </button>
            <span className="project-name">{media.original_filename}</span>
          </div>
          <a
            href={mediaApi.fileUrl(media.id, media.current_filename)}
            download
            className="btn btn-primary"
            style={videoProcessing ? { pointerEvents: 'none', opacity: 0.5 } : undefined}
          >
            <Download size={15} />
            Export
          </a>
        </div>

        <div className="editor-body">
          <div className="tool-rail">
            {media.media_type === 'video' && (
              <button
                className={`tool-btn ${tool === 'trim' ? 'active' : ''}`}
                onClick={() => setTool('trim')}
                disabled={videoProcessing}
              >
                <span className="icon"><Scissors size={18} /></span>
                Trim
              </button>
            )}
            <button
              className={`tool-btn ${tool === 'crop' ? 'active' : ''}`}
              onClick={() => setTool('crop')}
              disabled={videoProcessing}
            >
              <span className="icon"><Crop size={18} /></span>
              Crop
            </button>
            {(media.media_type === 'photo' || media.media_type === 'video') && (
              <button
                className={`tool-btn ${tool === 'remove' ? 'active' : ''}`}
                onClick={() => setTool('remove')}
                disabled={videoProcessing}
              >
                <span className="icon"><Eraser size={18} /></span>
                Remove
              </button>
            )}
            {(media.media_type === 'photo' || media.media_type === 'video') && (
              <button
                className={`tool-btn ${tool === 'transform' ? 'active' : ''}`}
                onClick={() => setTool('transform')}
                disabled={videoProcessing}
              >
                <span className="icon"><RotateCw size={18} /></span>
                Transform
              </button>
            )}
            {media.media_type === 'video' && (
              <button
                className={`tool-btn ${tool === 'adjust' ? 'active' : ''}`}
                onClick={() => setTool('adjust')}
                disabled={videoProcessing}
              >
                <span className="icon"><Gauge size={18} /></span>
                Speed/Vol
              </button>
            )}
            {(media.media_type === 'photo' || media.media_type === 'video') && (
              <button
                className={`tool-btn ${tool === 'watermark' ? 'active' : ''}`}
                onClick={() => setTool('watermark')}
                disabled={videoProcessing}
              >
                <span className="icon"><Type size={18} /></span>
                Watermark
              </button>
            )}
            {media.media_type === 'photo' && (
              <button
                className={`tool-btn ${tool === 'filter' ? 'active' : ''}`}
                onClick={() => setTool('filter')}
              >
                <span className="icon"><SlidersHorizontal size={18} /></span>
                Filters
              </button>
            )}
          </div>

          <div className="preview-pane">
            <div className="preview-frame" ref={frameRef}>
              {media.media_type === 'photo' ? (
                <img
                  ref={imgRef}
                  key={media.current_filename}
                  src={mediaApi.fileUrl(media.id, media.current_filename)}
                  alt={media.original_filename}
                  onLoad={measureImgBox}
                  draggable={false}
                />
              ) : tool === 'remove' ? (
                <img
                  ref={imgRef}
                  key={`${media.current_filename}-firstframe`}
                  src={mediaApi.firstFrameUrl(media.id)}
                  alt="First frame"
                  onLoad={() => {
                    measureImgBox()
                    setFirstFrameLoading(false)
                  }}
                  draggable={false}
                />
              ) : (
                <video key={media.current_filename} src={mediaApi.fileUrl(media.id, media.current_filename)} controls onLoadedMetadata={onVideoLoaded} />
              )}

              {tool === 'remove' && (media.media_type === 'photo' || media.media_type === 'video') && imgBox && (
                <div
                  className="removal-overlay"
                  style={{ left: imgBox.left, top: imgBox.top, width: imgBox.width, height: imgBox.height }}
                  onClick={handleOverlayClick}
                  onMouseDown={handleOverlayMouseDown}
                  onMouseMove={handleOverlayMouseMove}
                  onMouseUp={handleOverlayMouseUp}
                />
              )}

              {dragBox && (
                <div
                  className="box-draft"
                  style={{ left: dragBox.x, top: dragBox.y, width: dragBox.w, height: dragBox.h }}
                />
              )}

              {maskOverlayUrl && imgBox && (
                <img
                  className="mask-preview-img"
                  src={maskOverlayUrl}
                  alt="Selected object"
                  style={{ left: imgBox.left, top: imgBox.top, width: imgBox.width, height: imgBox.height }}
                />
              )}

              {(firstFrameLoading || segmenting || busy || videoProcessing) && (
                <div className="loading-overlay">
                  <Loader2 size={28} className="spin" />
                  <span>
                    {firstFrameLoading
                      ? 'Extracting video frame…'
                      : segmenting
                      ? 'Detecting object…'
                      : videoProcessing
                      ? `Processing video… ${Math.round(videoProgress * 100)}%`
                      : 'Applying changes…'}
                  </span>
                  {firstFrameLoading && (
                    <span className="sub">Longer videos take a bit longer here</span>
                  )}
                  {videoProcessing && (
                    <span className="sub">Don't close this tab</span>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="side-panel">
            {error && <div className="error-banner">{error}</div>}

            {tool === 'trim' && media.media_type === 'video' && (
              <>
                <h4>Trim</h4>
                <div className="field-group">
                  <label>Start <span className="val">{formatTime(start)}</span></label>
                  <label>End <span className="val">{formatTime(end)}</span></label>
                </div>
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.trim(media.id, start, end))}
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    Apply trim
                  </button>
                </div>
              </>
            )}

            {tool === 'crop' && (
              <>
                <h4>Crop</h4>
                <div className="field-row">
                  <div className="field-group">
                    <label>X <span className="val">{x}</span></label>
                    <input type="number" value={x} onChange={(e) => setX(Number(e.target.value))} />
                  </div>
                  <div className="field-group">
                    <label>Y <span className="val">{y}</span></label>
                    <input type="number" value={y} onChange={(e) => setY(Number(e.target.value))} />
                  </div>
                </div>
                <div className="field-row">
                  <div className="field-group">
                    <label>Width <span className="val">{width}</span></label>
                    <input type="number" value={width} onChange={(e) => setWidth(Number(e.target.value))} />
                  </div>
                  <div className="field-group">
                    <label>Height <span className="val">{height}</span></label>
                    <input type="number" value={height} onChange={(e) => setHeight(Number(e.target.value))} />
                  </div>
                </div>
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.crop(media.id, x, y, width, height))}
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    Apply crop
                  </button>
                </div>
              </>
            )}

            {tool === 'remove' && (media.media_type === 'photo' || media.media_type === 'video') && (
              <>
                <h4>Remove object</h4>
                {media.media_type === 'video' && (
                  <p className="hint-text">
                    Select the object on this first frame — it'll be tracked and removed
                    across the whole video.
                  </p>
                )}
                <p className="hint-text">
                  Click the object to remove it, or draw a box around it.
                </p>
                <div className="mode-toggle">
                  <button
                    className={`btn ${removalMode === 'point' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => {
                      setRemovalMode('point')
                      clearSelection()
                    }}
                    disabled={videoProcessing}
                  >
                    <MousePointerClick size={14} />
                    Point
                  </button>
                  <button
                    className={`btn ${removalMode === 'box' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => {
                      setRemovalMode('box')
                      clearSelection()
                    }}
                    disabled={videoProcessing}
                  >
                    <Square size={14} />
                    Box
                  </button>
                </div>

                {maskScore !== null && !segmenting && (
                  <div className="score-chip">Match confidence: {(maskScore * 100).toFixed(0)}%</div>
                )}

                {videoProcessing && (
                  <div className="field-group">
                    <label>
                      Processing video…
                      <span className="val">{Math.round(videoProgress * 100)}%</span>
                    </label>
                    <div className="progress-track">
                      <div className="progress-fill" style={{ width: `${videoProgress * 100}%` }} />
                    </div>
                    <p className="hint-text">
                      Tracking and removing the object across every frame — this can take
                      a while for longer videos. Please don't close this tab.
                    </p>
                  </div>
                )}

                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy || !maskId || videoProcessing}
                    onClick={applyRemoveObject}
                  >
                    {busy || videoProcessing ? <Loader2 size={15} className="spin" /> : <Eraser size={15} />}
                    {videoProcessing ? 'Processing…' : 'Remove selected object'}
                  </button>
                  {(maskId || dragBox) && !videoProcessing && (
                    <button
                      className="btn btn-ghost"
                      style={{ width: '100%', justifyContent: 'center', marginTop: '0.5rem' }}
                      onClick={clearSelection}
                    >
                      Clear selection
                    </button>
                  )}
                </div>
              </>
            )}

            {tool === 'transform' && (
              <>
                <h4>Rotate &amp; Flip</h4>
                <div className="mode-toggle">
                  <button
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.rotate(media.id, 90))}
                  >
                    <RotateCw size={14} />
                    Rotate 90°
                  </button>
                </div>
                <div className="mode-toggle">
                  <button
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.flip(media.id, 'horizontal'))}
                  >
                    <FlipHorizontal2 size={14} />
                    Flip H
                  </button>
                  <button
                    className="btn btn-ghost"
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.flip(media.id, 'vertical'))}
                  >
                    <FlipVertical2 size={14} />
                    Flip V
                  </button>
                </div>

                <h4 style={{ marginTop: '1.25rem' }}>Resize</h4>
                <div className="field-row">
                  <div className="field-group">
                    <label>Width <span className="val">{resizeWidth}</span></label>
                    <input type="number" value={resizeWidth} onChange={(e) => setResizeWidth(Number(e.target.value))} />
                  </div>
                  <div className="field-group">
                    <label>Height <span className="val">{resizeHeight}</span></label>
                    <input type="number" value={resizeHeight} onChange={(e) => setResizeHeight(Number(e.target.value))} />
                  </div>
                </div>
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.resize(media.id, resizeWidth, resizeHeight))}
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    <Maximize2 size={15} />
                    Apply resize
                  </button>
                </div>
              </>
            )}

            {tool === 'adjust' && media.media_type === 'video' && (
              <>
                <h4>Speed</h4>
                <div className="field-group">
                  <label>Speed factor <span className="val">{speedFactor.toFixed(2)}x</span></label>
                  <input
                    type="range"
                    min="0.25"
                    max="4"
                    step="0.05"
                    value={speedFactor}
                    onChange={(e) => setSpeedFactor(Number(e.target.value))}
                  />
                </div>
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.speed(media.id, speedFactor))}
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    Apply speed
                  </button>
                </div>

                <h4 style={{ marginTop: '1.25rem' }}>Volume</h4>
                <div className="field-group">
                  <label>Level <span className="val">{volumeMute ? 'Muted' : `${volumeLevel.toFixed(1)}x`}</span></label>
                  <input
                    type="range"
                    min="0"
                    max="3"
                    step="0.1"
                    value={volumeLevel}
                    disabled={volumeMute}
                    onChange={(e) => setVolumeLevel(Number(e.target.value))}
                  />
                </div>
                <div className="mode-toggle">
                  <button
                    className={`btn ${volumeMute ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setVolumeMute(!volumeMute)}
                  >
                    {volumeMute ? <VolumeX size={14} /> : <Volume2 size={14} />}
                    {volumeMute ? 'Muted' : 'Mute'}
                  </button>
                </div>
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.volume(media.id, volumeLevel, volumeMute))}
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    Apply volume
                  </button>
                </div>
              </>
            )}

            {tool === 'watermark' && (
              <>
                <h4>Watermark</h4>
                <div className="field-group">
                  <label>Text</label>
                  <input
                    type="text"
                    value={watermarkText}
                    onChange={(e) => setWatermarkText(e.target.value)}
                    placeholder="Your text here"
                  />
                </div>
                <div className="field-row">
                  <div className="field-group">
                    <label>X <span className="val">{watermarkX}</span></label>
                    <input type="number" value={watermarkX} onChange={(e) => setWatermarkX(Number(e.target.value))} />
                  </div>
                  <div className="field-group">
                    <label>Y <span className="val">{watermarkY}</span></label>
                    <input type="number" value={watermarkY} onChange={(e) => setWatermarkY(Number(e.target.value))} />
                  </div>
                </div>
                <div className="field-group">
                  <label>Font size <span className="val">{watermarkFontSize}</span></label>
                  <input
                    type="range"
                    min="10"
                    max="120"
                    step="1"
                    value={watermarkFontSize}
                    onChange={(e) => setWatermarkFontSize(Number(e.target.value))}
                  />
                </div>
                {media.media_type === 'photo' && (
                  <div className="field-group">
                    <label>Color</label>
                    <input type="color" value={watermarkColor} onChange={(e) => setWatermarkColor(e.target.value)} />
                  </div>
                )}
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy || !watermarkText.trim()}
                    onClick={() =>
                      runAction(() =>
                        mediaApi.watermark(media.id, {
                          text: watermarkText,
                          x: watermarkX,
                          y: watermarkY,
                          font_size: watermarkFontSize,
                          color: watermarkColor,
                          opacity: 1.0,
                        })
                      )
                    }
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    <Type size={15} />
                    Apply watermark
                  </button>
                </div>
              </>
            )}

            {tool === 'filter' && media.media_type === 'photo' && (
              <>
                <h4>Filters</h4>
                <div className="filter-swatches">
                  {FILTERS.map((f) => (
                    <div
                      key={f.id}
                      className={`filter-swatch ${filterName === f.id ? 'active' : ''}`}
                      onClick={() => setFilterName(f.id)}
                    >
                      {f.label}
                    </div>
                  ))}
                </div>
                <div className="field-group">
                  <label>Intensity <span className="val">{intensity.toFixed(1)}</span></label>
                  <input
                    type="range"
                    min="0"
                    max="3"
                    step="0.1"
                    value={intensity}
                    onChange={(e) => setIntensity(Number(e.target.value))}
                  />
                </div>
                <div className="apply-bar">
                  <button
                    className="btn btn-primary"
                    style={{ width: '100%', justifyContent: 'center' }}
                    disabled={busy}
                    onClick={() => runAction(() => mediaApi.filter(media.id, filterName, intensity))}
                  >
                    {busy && <Loader2 size={15} className="spin" />}
                    Apply filter
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

        {media.media_type === 'video' && (
          <div className="timeline">
            <div className="timeline-ruler">
              <span>0:00</span>
              <span>{formatTime(duration)}</span>
            </div>
            <div className="timeline-track" ref={trackRef}>
              <div
                className="timeline-clip"
                style={{ left: `${startPct}%`, width: `${Math.max(0, endPct - startPct)}%` }}
              />
              <div
                className="timeline-handle start"
                style={{ left: `calc(${startPct}% - 5px)` }}
                onMouseDown={startDrag('start')}
              />
              <div
                className="timeline-handle end"
                style={{ left: `calc(${endPct}% - 5px)` }}
                onMouseDown={startDrag('end')}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}