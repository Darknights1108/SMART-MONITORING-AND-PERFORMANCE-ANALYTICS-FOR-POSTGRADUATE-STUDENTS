import { getToken, clearAuth } from './auth'

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...opts.headers,
    },
  })
  if (!res.ok) {
    // Token expired or invalid — clear session and redirect to login
    if (res.status === 401) {
      clearAuth()
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
      throw new Error('Session expired. Please log in again.')
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  return res.json()
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const login = (staff_id: string, password: string) =>
  req<{ access_token: string; user: any }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ staff_id, password }),
  })

// ── Dashboard ─────────────────────────────────────────────────────────────────
export const getMySummary = () =>
  req<{
    total_students: number
    high_risk: number
    medium_risk: number
    low_risk: number
    overdue_students: number
    upcoming_30_days: number
  }>('/api/dashboard/my-summary')

export const getUpcomingDeadlines = (days = 30) =>
  req<any[]>(`/api/dashboard/upcoming-deadlines?days=${days}`)

export const getEmailLog = (limit = 20) =>
  req<any[]>(`/api/dashboard/email-log?limit=${limit}`)

// ── Students ──────────────────────────────────────────────────────────────────
export const getStudents = () => req<any[]>('/api/students/')

export const getStudent = (id: number) => req<any>(`/api/students/${id}`)

// ── Supervisors ───────────────────────────────────────────────────────────────
export const getSupervisors = () => req<any[]>('/api/supervisors/')

// ── Risk predictions ──────────────────────────────────────────────────────────
export const getPredictions = () => req<any[]>('/api/predictions/')

export const getRiskDistribution = () =>
  req<{
    distribution: Record<string, number>
    total: number
    high_risk_count: number
    medium_risk_count: number
    low_risk_count: number
  }>('/api/predictions/distribution')

export const getDriftReport = () => req<any>('/api/predictions/drift')

export const getMlflowRuns = () => req<any>('/api/predictions/runs')

export const retrain = () =>
  req<any>('/api/predictions/retrain', { method: 'POST' })

export const getModelMetrics = () => req<any>('/api/predictions/metrics')

// ── Analytics ─────────────────────────────────────────────────────────────────
export const getAnalyticsData = () =>
  req<{ students: any[]; total: number }>('/api/analytics/data')

export const getMilestoneMatrix = () =>
  req<any[]>('/api/analytics/milestones')

// ── Admin — Lookups ───────────────────────────────────────────────────────────
export const getPrograms     = () => req<any[]>('/api/lookups/programs')
export const getFaculties    = () => req<any[]>('/api/lookups/faculties')
export const getCountries    = () => req<any[]>('/api/lookups/countries')
export const getDisciplines  = () => req<any[]>('/api/lookups/disciplines')
export const getFundingTypes = () => req<any[]>('/api/lookups/funding-types')
export const getCampuses     = () => req<any[]>('/api/lookups/campuses')

// ── Admin — Create ────────────────────────────────────────────────────────────
export const createStudent    = (data: any) =>
  req<any>('/api/students/',    { method: 'POST', body: JSON.stringify(data) })
export const updateStudent    = (id: number, data: any) =>
  req<any>(`/api/students/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const createSupervisor = (data: any) =>
  req<any>('/api/supervisors/', { method: 'POST', body: JSON.stringify(data) })
export const updateSupervisor = (id: number, data: any) =>
  req<any>(`/api/supervisors/${id}`, { method: 'PUT', body: JSON.stringify(data) })

// ── WebSocket URL ─────────────────────────────────────────────────────────────
export function wsUrl(): string {
  const base = (process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000')
  return `${base}/ws/chat`
}
