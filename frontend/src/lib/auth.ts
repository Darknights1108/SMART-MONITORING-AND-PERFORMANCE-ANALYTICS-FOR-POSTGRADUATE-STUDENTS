export interface AuthUser {
  supervisor_id: number
  staff_id: string
  name: string
  role: 'Supervisor' | 'Admin' | 'Both'
}

const TOKEN_KEY = 'datatrain_token'
const USER_KEY  = 'datatrain_user'

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function getUser(): AuthUser | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = localStorage.getItem(USER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setAuth(token: string, user: AuthUser): void {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export function isAdmin(user: AuthUser | null): boolean {
  return user?.role === 'Admin' || user?.role === 'Both'
}

/** Returns true if the stored JWT is present and not yet expired. */
export function isTokenValid(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    // exp is in seconds; Date.now() is in milliseconds
    return payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}
