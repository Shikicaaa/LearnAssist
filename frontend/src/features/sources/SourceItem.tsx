import { useState } from 'react'
import { describeError } from '../../lib/api/client'
import { sourcesApi } from '../../lib/api/endpoints'
import type { Source } from '../../lib/api/types'
import { DownloadIcon, FileIcon, Menu, RetryIcon, TextIcon, TrashIcon, type MenuItem } from '../../components/ui'

const STATUS_LABEL: Record<string, string> = {
  queued: 'Queued',
  processing: 'Reading…',
  ready: 'Ready',
  failed: 'Failed',
}

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function SourceItem({
  source,
  onChanged,
  onRemoved,
}: {
  source: Source
  onChanged: (s: Source) => void
  onRemoved: (id: string) => void
}) {
  const [error, setError] = useState<string | null>(null)
  const busy = source.status === 'queued' || source.status === 'processing'

  async function run(action: () => Promise<void>) {
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(describeError(err))
    }
  }

  const items: MenuItem[] = [
    { label: 'Download original', icon: <DownloadIcon size={16} />, onSelect: () => run(() => sourcesApi.download(source)) },
    ...(source.status === 'failed' || source.status === 'ready'
      ? [{ label: 'Re-index', icon: <RetryIcon size={16} />, onSelect: () => run(async () => onChanged(await sourcesApi.reindex(source.id))) }]
      : []),
    {
      label: 'Remove',
      icon: <TrashIcon size={16} />,
      danger: true,
      onSelect: () =>
        run(async () => {
          await sourcesApi.remove(source.id)
          onRemoved(source.id)
        }),
    },
  ]

  const meta = [source.page_count ? `${source.page_count} p.` : null, formatSize(source.size_bytes)]
    .filter(Boolean)
    .join(' · ')

  return (
    <li className={`source source--${source.status}`}>
      <span className="source__icon">{source.filename ? <FileIcon /> : <TextIcon />}</span>
      <div className="source__body">
        <div className="source__title" title={source.title}>
          {source.title}
        </div>
        <div className="source__meta mono">
          <span className={`pill pill--${source.status}`}>
            {busy && <span className="spinner" />}
            {STATUS_LABEL[source.status] ?? source.status}
          </span>
          {meta}
        </div>
        {(source.error || error) && <div className="source__error">{error ?? source.error}</div>}
      </div>
      <Menu items={items} label={`Actions for ${source.title}`} />
    </li>
  )
}
