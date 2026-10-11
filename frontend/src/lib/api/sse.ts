// Server-sent events over fetch(). The browser's EventSource cannot send an Authorization
// header and cannot POST, and the backend uses Bearer tokens, so we parse the stream ourselves.

export interface SseEvent {
  event: string
  data: unknown
}

/** Splits a text stream into SSE messages. Comment lines (": keepalive") are skipped. */
export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const message = parseMessage(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        if (message) yield message
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parseMessage(raw: string): SseEvent | null {
  let event = 'message'
  const data: string[] = []
  for (const line of raw.split('\n')) {
    if (line.startsWith(':')) continue
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
  }
  if (data.length === 0) return null
  try {
    return { event, data: JSON.parse(data.join('\n')) }
  } catch {
    return null
  }
}
