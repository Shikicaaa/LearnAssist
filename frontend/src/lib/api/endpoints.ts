import { request, openStream, authFetch, ApiError, tokens } from './client'
import { parseSse } from './sse'
import type { Chunk, Message, Page, Session, Source, TokenPair, User } from './types'

// ---- auth ------------------------------------------------------------------------------

export const authApi = {
  register: (email: string, password: string) =>
    request<User>('/auth/register', { json: { email, password }, auth: false }),
  login: (email: string, password: string) =>
    request<TokenPair>('/auth/login', { json: { email, password }, auth: false }),
  me: () => request<User>('/auth/me'),
  logout: () => {
    const refresh_token = tokens.refresh
    return refresh_token ? request('/auth/logout', { json: { refresh_token } }) : Promise.resolve()
  },
}

// ---- sessions --------------------------------------------------------------------------

export const sessionsApi = {
  list: () => request<Page<Session>>('/sessions?limit=50'),
  create: (title: string) => request<Session>('/sessions', { json: { title } }),
  get: (sid: string) => request<Session>(`/sessions/${sid}`),
  update: (sid: string, patch: { title?: string; cache_enabled?: boolean }) =>
    request<Session>(`/sessions/${sid}`, { method: 'PATCH', json: patch }),
  remove: (sid: string) => request(`/sessions/${sid}`, { method: 'DELETE' }),
  clearCache: (sid: string) => request(`/sessions/${sid}/cache/clear`, { method: 'POST' }),
}

// ---- sources ---------------------------------------------------------------------------

export const sourcesApi = {
  list: (sid: string) => request<Source[]>(`/sessions/${sid}/sources`),
  upload: (sid: string, files: File[]) => {
    const form = new FormData()
    files.forEach((f) => form.append('files', f))
    return request<Source[]>(`/sessions/${sid}/sources/files`, { form })
  },
  addText: (sid: string, title: string, content: string) =>
    request<Source>(`/sessions/${sid}/sources/text`, { json: { title, content } }),
  reindex: (id: string) => request<Source>(`/sources/${id}/reindex`, { method: 'POST' }),
  remove: (id: string) => request(`/sources/${id}`, { method: 'DELETE' }),
  /** Downloads the original file through fetch, since a plain link cannot carry the token. */
  async download(source: Source) {
    const res = await authFetch(`/sources/${source.id}/file`)
    if (!res.ok) throw new ApiError(res.status, 'download_failed', 'Could not download the file')
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = source.filename ?? `${source.title}.txt`
    a.click()
    URL.revokeObjectURL(url)
  },
  events: async (sid: string, signal: AbortSignal) =>
    parseSse(await openStream(`/sessions/${sid}/sources/events`, { signal })),
}

// ---- chat ------------------------------------------------------------------------------

export const chatApi = {
  /** Newest message first (the backend's order). */
  history: (sid: string, offset = 0) =>
    request<Page<Message>>(`/sessions/${sid}/messages?limit=50&offset=${offset}`),
  clear: (sid: string) => request(`/sessions/${sid}/messages`, { method: 'DELETE' }),
  ask: async (sid: string, question: string, useCache: boolean, allowGeneral: boolean, signal: AbortSignal) =>
    parseSse(
      await openStream(`/sessions/${sid}/messages?stream=true`, {
        json: { question, use_cache: useCache, allow_general: allowGeneral },
        signal,
      }),
    ),
  chunk: (id: string) => request<Chunk>(`/chunks/${id}`),
}
