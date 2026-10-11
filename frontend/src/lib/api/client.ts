import type { TokenPair } from './types'

const BASE = '/api/v1'
const ACCESS_KEY = 'lofinote.access'
const REFRESH_KEY = 'lofinote.refresh'

export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

// ---- token storage ---------------------------------------------------------------------

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(pair: TokenPair) {
    localStorage.setItem(ACCESS_KEY, pair.access_token)
    localStorage.setItem(REFRESH_KEY, pair.refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

// Called when the session cannot be recovered (refresh failed). AuthContext subscribes to it.
let onSessionExpired: () => void = () => {}
export function setSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn
}

// ---- refresh (single flight) -----------------------------------------------------------

let refreshing: Promise<boolean> | null = null

/** Several requests may get 401 at once; they all wait for one refresh call. */
function refreshTokens(): Promise<boolean> {
  refreshing ??= (async () => {
    const refresh_token = tokens.refresh
    if (!refresh_token) return false
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      })
      if (!res.ok) return false
      tokens.set(await res.json())
      return true
    } catch {
      return false
    } finally {
      refreshing = null
    }
  })()
  return refreshing
}

// ---- requests --------------------------------------------------------------------------

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json()
    if (body?.error) return new ApiError(res.status, body.error.code, body.error.message)
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, 'unknown', res.statusText || 'Request failed')
}

/** fetch() with the Bearer token; on 401 refreshes the token once and retries. */
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => {
    const headers = new Headers(init.headers)
    if (tokens.access) headers.set('Authorization', `Bearer ${tokens.access}`)
    return fetch(`${BASE}${path}`, { ...init, headers })
  }
  let res = await send()
  if (res.status === 401 && tokens.refresh) {
    if (await refreshTokens()) res = await send()
    else {
      tokens.clear()
      onSessionExpired()
    }
  }
  return res
}

interface RequestOptions {
  method?: string
  json?: unknown
  form?: FormData
  signal?: AbortSignal
  auth?: boolean
}

export async function request<T = void>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers = new Headers()
  let body: BodyInit | undefined
  if (opts.json !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(opts.json)
  } else if (opts.form) {
    body = opts.form // the browser sets the multipart boundary itself
  }
  const init: RequestInit = { method: opts.method ?? (body ? 'POST' : 'GET'), headers, body, signal: opts.signal }
  const res = opts.auth === false ? await fetch(`${BASE}${path}`, init) : await authFetch(path, init)
  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

/** Opens a stream (SSE). Throws ApiError for HTTP errors that arrive before the first byte. */
export async function openStream(
  path: string,
  opts: { method?: string; json?: unknown; signal?: AbortSignal } = {},
): Promise<ReadableStream<Uint8Array>> {
  const headers = new Headers({ Accept: 'text/event-stream' })
  if (opts.json !== undefined) headers.set('Content-Type', 'application/json')
  const res = await authFetch(path, {
    method: opts.method ?? (opts.json !== undefined ? 'POST' : 'GET'),
    headers,
    body: opts.json !== undefined ? JSON.stringify(opts.json) : undefined,
    signal: opts.signal,
  })
  if (!res.ok || !res.body) throw await toError(res)
  return res.body
}

/** Maps an error code from the backend to a message for the user. */
export function describeError(err: unknown): string {
  if (!(err instanceof ApiError)) return 'Something went wrong. Check your connection and try again.'
  switch (err.code) {
    case 'rate_limited':
      return 'Slow down a little — too many requests. Try again in a moment.'
    case 'quota_exceeded':
      return err.message
    case 'payload_too_large':
      return 'That file is too large.'
    case 'unsupported_media_type':
      return 'That file type is not supported. Use PDF, DOCX, TXT or MD.'
    case 'unauthorized':
      return 'Your session has expired. Please sign in again.'
    default:
      return err.message
  }
}
