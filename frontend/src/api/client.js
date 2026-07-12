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
  segment: (id, payload) => client.post(`/media/${id}/segment`, payload),
  removeObject: (id, mask_id) => client.post(`/media/${id}/remove-object`, { mask_id }),
  remove: (id) => client.delete(`/media/${id}`),
}

export default client