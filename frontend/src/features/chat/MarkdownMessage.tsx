import { memo, type ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import rehypeKatex from 'rehype-katex'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import type { Citation } from '../../lib/api/types'
import 'katex/dist/katex.min.css'

// The model writes "[1]", "[2]" ...; turn them into links with a private "#cite-N" target
// that the `a` renderer below recognises and draws as a clickable chip.
const withCitationLinks = (text: string) => text.replace(/\[(\d+)\](?!\()/g, '[$1](#cite-$1)')

interface Props {
  content: string
  citations: Citation[]
  onCitation: (c: Citation) => void
}

export const MarkdownMessage = memo(function MarkdownMessage({ content, citations, onCitation }: Props) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a({ href, children }: { href?: string; children?: ReactNode }) {
            const rank = href?.startsWith('#cite-') ? Number(href.slice(6)) : null
            if (rank === null) {
              return (
                <a href={href} target="_blank" rel="noreferrer noopener">
                  {children}
                </a>
              )
            }
            const citation = citations.find((c) => c.rank === rank)
            return citation ? (
              <button className="cite" onClick={() => onCitation(citation)} title={citation.source_title}>
                {rank}
              </button>
            ) : (
              <span className="cite cite--dead">{rank}</span>
            )
          },
        }}
      >
        {withCitationLinks(content)}
      </ReactMarkdown>
    </div>
  )
})
