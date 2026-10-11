import { useEffect, useState } from 'react'
import { describeError } from '../../lib/api/client'
import { chatApi } from '../../lib/api/endpoints'
import type { Chunk, Citation } from '../../lib/api/types'
import { Modal } from '../../components/ui'

export function CitationModal({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  const [chunk, setChunk] = useState<Chunk | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!citation.chunk_id) return
    chatApi
      .chunk(citation.chunk_id)
      .then(setChunk)
      .catch((err) => setError(describeError(err)))
  }, [citation.chunk_id])

  const from = citation.page_start
  const pages = from == null ? null : citation.page_end && citation.page_end !== from ? `pages ${from}–${citation.page_end}` : `page ${from}`

  return (
    <Modal title={`[${citation.rank}] ${citation.source_title}`} onClose={onClose}>
      {pages && <p className="mono" style={{ margin: '0 0 12px', color: 'var(--text-dim)', fontSize: '0.8rem' }}>{pages}</p>}
      {!citation.chunk_id ? (
        <p style={{ color: 'var(--text-dim)' }}>This source has since been removed, so its text is no longer available.</p>
      ) : error ? (
        <div className="alert">{error}</div>
      ) : !chunk ? (
        <span className="spinner" />
      ) : (
        <blockquote className="quote">{chunk.text}</blockquote>
      )}
    </Modal>
  )
}
