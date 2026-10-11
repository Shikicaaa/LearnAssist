import { useState } from 'react'
import type { Source } from '../../lib/api/types'
import { Button, CloseIcon, PlusIcon, FileIcon } from '../../components/ui'
import { AddSourcesModal } from './AddSourcesModal'
import { SourceItem } from './SourceItem'
import './sources.css'

interface Props {
  sid: string
  sources: Source[]
  loading: boolean
  onAdded: (sources: Source[]) => void
  onChanged: (source: Source) => void
  onRemoved: (id: string) => void
  onClose: () => void
}

export function SourcesPanel({ sid, sources, loading, onAdded, onChanged, onRemoved, onClose }: Props) {
  const [adding, setAdding] = useState(false)

  return (
    <div className="sources">
      <div className="sources__head">
        <h2>Sources</h2>
        <span className="mono sources__count">{sources.length}/20</span>
        <button className="icon-btn sources__close" onClick={onClose} aria-label="Close sources">
          <CloseIcon />
        </button>
      </div>

      <Button variant="ghost" block onClick={() => setAdding(true)}>
        <PlusIcon /> Add sources
      </Button>

      <div className="sources__scroll">
        {loading ? (
          <p className="sources__empty">Loading…</p>
        ) : sources.length === 0 ? (
          <div className="sources__empty">
            <FileIcon size={30} />
            <strong>Saved sources will appear here</strong>
            <span>Add files or paste text, then ask questions about them.</span>
          </div>
        ) : (
          <ul className="sources__list">
            {sources.map((s) => (
              <SourceItem key={s.id} source={s} onChanged={onChanged} onRemoved={onRemoved} />
            ))}
          </ul>
        )}
      </div>

      {adding && <AddSourcesModal sid={sid} onClose={() => setAdding(false)} onAdded={onAdded} />}
    </div>
  )
}
