import axios from 'axios'

const API_BASE_URL = 'http://localhost:8000'

const client = axios.create({ baseURL: API_BASE_URL })

client.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export const authApi = {
  register: (email, password) => client.post('/auth/register', { email, password }),
  login: (email, password) => client.post('/auth/login', { email, password }),
  me: () => client.get('/auth/me'),
}

export const mediaApi = {
  list: () => client.get('/media/list'),
  upload: (file) => {
    const formData = new FormData()
    formData.append('file', file)
    return client.post('/media/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  fileUrl: (id, versionKey = '') => {
    const token = localStorage.getItem('token')
    return `${API_BASE_URL}/media/${id}/file?token=${encodeURIComponent(token)}&v=${encodeURIComponent(versionKey)}`
  },
  trim: (id, start_seconds, end_seconds) =>
    client.post(`/media/${id}/trim`, { start_seconds, end_seconds }),
  crop: (id, x, y, width, height) =>
    client.post(`/media/${id}/crop`, { x, y, width, height }),
  filter: (id, filter_name, intensity) =>
    client.post(`/media/${id}/filter`, { filter_name, intensity }),
  rotate: (id, degrees) => client.post(`/media/${id}/rotate`, { degrees }),
  flip: (id, direction) => client.post(`/media/${id}/flip`, { direction }),
  resize: (id, width, height) => client.post(`/media/${id}/resize`, { width, height }),
  speed: (id, factor) => client.post(`/media/${id}/speed`, { factor }),
  volume: (id, level, mute) => client.post(`/media/${id}/volume`, { level, mute }),
  watermark: (id, payload) => client.post(`/media/${id}/watermark`, payload),
  segment: (id, payload) => client.post(`/media/${id}/segment`, payload),
  removeObject: (id, mask_id) => client.post(`/media/${id}/remove-object`, { mask_id }),
  remove: (id) => client.delete(`/media/${id}`),
  firstFrameUrl: (id) => {
    const token = localStorage.getItem('token')
    return `${API_BASE_URL}/media/${id}/first-frame?token=${encodeURIComponent(token)}`
  },
  videoSegment: (id, payload) => client.post(`/media/${id}/video-segment`, payload),
  videoRemoveObject: (id, mask_id) => client.post(`/media/${id}/video-remove-object`, { mask_id }),
  videoRemoveObjectJob: (id, jobId) => client.get(`/media/${id}/video-remove-object/jobs/${jobId}`),
  thumbnailUrl: (id) => {
    const token = localStorage.getItem('token')
    return `${API_BASE_URL}/media/${id}/thumbnail?token=${encodeURIComponent(token)}`
  },
  versions: (id) => client.get(`/media/${id}/versions`),
  restoreVersion: (id, versionId) => client.post(`/media/${id}/versions/${versionId}/restore`),
  exportGif: (id, payload) => client.post(`/media/${id}/export-gif`, payload, { responseType: 'blob' }),
  denoise: (id, strength) => client.post(`/media/${id}/denoise`, { strength }),
}

export default client