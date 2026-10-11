// Mirrors the Pydantic schemas of the backend (app/modules/*/schemas.py).

export interface User {
  id: string
  email: string
  is_active: boolean
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface Session {
  id: string
  title: string
  corpus_version: number
  cache_enabled: boolean
  embedding_model: string
  created_at: string
  updated_at: string
}

export type SourceStatus = 'queued' | 'processing' | 'ready' | 'failed' | 'deleted'

export interface Source {
  id: string
  session_id: string
  type: string
  title: string
  filename: string | null
  mime: string | null
  size_bytes: number
  status: SourceStatus
  page_count: number | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface Citation {
  rank: number
  chunk_id: string | null
  source_id: string | null
  source_title: string
  page_start: number | null
  page_end: number | null
  score: number
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  cached: boolean
  llm_provider: string | null
  llm_model: string | null
  tokens_in: number
  tokens_out: number
  created_at: string
  citations: Citation[]
}

export interface Chunk {
  chunk_id: string
  source_id: string
  session_id: string
  source_title: string
  chunk_index: number
  page_start: number | null
  page_end: number | null
  text: string
}
