import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { describeError } from '../../lib/api/client'
import { sourcesApi } from '../../lib/api/endpoints'
import type { Source } from '../../lib/api/types'
import { Button, Field, Modal, TextIcon, UploadIcon } from '../../components/ui'

type Tab = 'files' | 'text'
const ACCEPT = '.pdf,.docx,.txt,.md'

export function AddSourcesModal({
  sid,
  onClose,
  onAdded,
}: {
  sid: string
  onClose: () => void
  onAdded: (sources: Source[]) => void
}) {
  const [tab, setTab] = useState<Tab>('files')
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const picker = useRef<HTMLInputElement>(null)

  async function submit(action: () => Promise<Source[]>) {
    setBusy(true)
    setError(null)
    try {
      onAdded(await action())
      onClose()
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  const uploadFiles = (files: FileList | File[]) => {
    const list = Array.from(files)
    if (list.length) void submit(() => sourcesApi.upload(sid, list))
  }

  function onDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    uploadFiles(e.dataTransfer.files)
  }

  function onSubmitText(e: FormEvent) {
    e.preventDefault()
    void submit(async () => [await sourcesApi.addText(sid, title.trim(), content)])
  }

  return (
    <Modal title="Add sources" onClose={onClose}>
      <div className="tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'files'} className={tab === 'files' ? 'is-on' : ''} onClick={() => setTab('files')}>
          <UploadIcon size={16} /> Upload files
        </button>
        <button role="tab" aria-selected={tab === 'text'} className={tab === 'text' ? 'is-on' : ''} onClick={() => setTab('text')}>
          <TextIcon size={16} /> Paste text
        </button>
      </div>

      {error && (
        <div className="alert" role="alert" style={{ marginBottom: 14 }}>
          {error}
        </div>
      )}

      {tab === 'files' ? (
        <div
          className={`dropzone ${dragging ? 'is-over' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <UploadIcon size={28} />
          <p>{busy ? 'Uploading…' : 'Drag & drop your files here'}</p>
          <p className="dropzone__hint mono">PDF · DOCX · TXT · MD — up to 25 MB each</p>
          <Button variant="ghost" disabled={busy} onClick={() => picker.current?.click()}>
            {busy ? <span className="spinner" /> : 'Choose files'}
          </Button>
          <input
            ref={picker}
            type="file"
            multiple
            accept={ACCEPT}
            hidden
            onChange={(e) => e.target.files && uploadFiles(e.target.files)}
          />
        </div>
      ) : (
        <form className="textform" onSubmit={onSubmitText}>
          <Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required maxLength={255} placeholder="e.g. Lecture 4 notes" />
          <div className="field">
            <label className="field__label" htmlFor="src-content">
              Text
            </label>
            <textarea
              id="src-content"
              className="input"
              rows={9}
              required
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder="Paste anything you want to study…"
            />
          </div>
          <Button type="submit" disabled={busy || !content.trim()}>
            {busy ? <span className="spinner" /> : 'Add text'}
          </Button>
        </form>
      )}
    </Modal>
  )
}
