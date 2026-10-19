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

// ---- quizzes (app/modules/artifacts/schemas.py) -----------------------------------------

export type QuestionType = 'mcq' | 'true_false' | 'short_answer'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type QuizScript = 'latin' | 'cyrillic'
export type ArtifactStatus = 'pending' | 'ready' | 'failed'

export interface QuizRequest {
  /** Narrows the material to what matches this text; null/omitted = the whole material. */
  topic?: string | null
  /** Empty/omitted = all sources. */
  source_ids?: string[]
  num_questions?: number
  difficulty?: Difficulty
  types?: QuestionType[]
  script?: QuizScript
  /** Skip the stored quiz for these settings and make a new one. */
  regenerate?: boolean
}

export interface QuizCitation {
  chunk_id: string | null // null once the source text no longer exists
  source_id: string | null
  source_title: string
  page_start: number | null
  page_end: number | null
}

export interface QuizQuestion {
  type: QuestionType
  question: string
  options: string[]
  correct_index: number | null // mcq and true_false
  correct_answer: string | null // short_answer
  explanation: string
  evidence: string
  citation: QuizCitation
}

export interface QuizParams {
  topic: string | null
  source_ids: string[]
  num_questions: number
  difficulty: Difficulty
  types: QuestionType[]
  script: QuizScript
}

export interface Artifact {
  id: string
  session_id: string
  kind: string
  status: ArtifactStatus
  error: string | null
  params: QuizParams
  content: { questions: QuizQuestion[] } | null // null until status is "ready"
  llm_model: string
  tokens_in: number
  tokens_out: number
  created_at: string
}
