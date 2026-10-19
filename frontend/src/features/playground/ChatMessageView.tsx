import { FileText, Square, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import Markdown from 'react-markdown'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'

import { Callout } from '@/components/Callout'
import type { Source } from '@/features/playground/chat-stream'
import { cn } from '@/lib/utils'

/** Streaming caret: a blinking bar after the last block of the answer. */
const caret =
  "[&>*:last-child]:after:ml-0.5 [&>*:last-child]:after:inline-block [&>*:last-child]:after:h-[1.05em] [&>*:last-child]:after:w-[0.4rem] [&>*:last-child]:after:translate-y-[0.15em] [&>*:last-child]:after:rounded-[1px] [&>*:last-child]:after:bg-primary [&>*:last-child]:after:content-[''] motion-safe:[&>*:last-child]:after:animate-pulse"

function ModelHeading({ id, className, children }: { id?: string; className: string; children?: ReactNode }) {
  return (
    <p id={id} role="heading" aria-level={3} className={className}>
      {children}
    </p>
  )
}

/** Model output is untrusted: markdown is parsed without raw HTML, then sanitized. No images (they could leak data). */
export function SafeMarkdown({
  children,
  streaming = false,
  className,
}: {
  children: string
  streaming?: boolean
  className?: string
}) {
  return (
    <div
      className={cn(
        'min-w-0 text-body break-words [&>*+*]:mt-3',
        '[&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_li]:pl-0.5 [&_li+li]:mt-1',
        '[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-3 [&_blockquote]:text-muted-foreground',
        '[&_hr]:border-border [&_strong]:font-semibold',
        '[&_:not(pre)>code]:rounded-md [&_:not(pre)>code]:bg-muted [&_:not(pre)>code]:px-1.5 [&_:not(pre)>code]:py-0.5 [&_:not(pre)>code]:font-mono [&_:not(pre)>code]:text-[0.85em]',
        '[&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:border [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:font-mono [&_pre]:text-[0.8125rem] [&_pre]:leading-relaxed',
        streaming && caret,
        className,
      )}
    >
      <Markdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        disallowedElements={['img']}
        components={{
          // Model output must not add to the page outline (the page owns h1/h2): render every heading as a
          // styled level-3 heading role instead of a real h1-h6.
          h1: ({ children, id }) => <ModelHeading id={id} className="mt-5 text-section-title">{children}</ModelHeading>,
          h2: ({ children, id }) => <ModelHeading id={id} className="mt-4 text-card-title">{children}</ModelHeading>,
          h3: ({ children, id }) => <ModelHeading id={id} className="mt-4 text-card-title">{children}</ModelHeading>,
          h4: ({ children, id }) => <ModelHeading id={id} className="mt-4 text-card-title">{children}</ModelHeading>,
          h5: ({ children, id }) => <ModelHeading id={id} className="mt-4 text-card-title">{children}</ModelHeading>,
          h6: ({ children, id }) => <ModelHeading id={id} className="mt-4 text-card-title">{children}</ModelHeading>,
          a: ({ href, children }) => {
            // in-page links (GFM footnotes) stay in the page; everything else opens in a new tab
            const external = !href?.startsWith('#')
            return (
              <a
                href={href}
                {...(external ? { target: '_blank', rel: 'noopener noreferrer nofollow' } : {})}
                className="font-medium text-primary underline underline-offset-4 hover:text-primary/80"
              >
                {children}
              </a>
            )
          },
          table: ({ children }) => (
            <div className="overflow-x-auto rounded-lg border">
              <table className="w-full border-collapse text-sm">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border-b bg-muted px-3 py-2 text-left font-medium">{children}</th>,
          td: ({ children }) => <td className="border-b px-3 py-2 last:border-b-0">{children}</td>,
        }}
      >
        {children}
      </Markdown>
    </div>
  )
}

/** Numbered source cards under an answer: section path + excerpt. The `[n]` chip matches the order the passages were used. */
export function SourcesList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) return null
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-1.5 text-eyebrow">
        <FileText className="size-3.5" aria-hidden />
        <span>Sources ({sources.length})</span>
      </div>
      <ol className="grid gap-2 sm:grid-cols-2">
        {sources.map((s, i) => (
          <li key={s.chunk_id} className="flex min-w-0 gap-2.5 rounded-lg border bg-card px-3 py-2.5 text-caption shadow-card">
            <span
              aria-hidden
              className="mt-px flex h-5 shrink-0 items-center rounded-md bg-accent px-1.5 font-mono text-[0.6875rem] font-medium text-accent-foreground tabular-nums"
            >
              [{i + 1}]
            </span>
            <div className="min-w-0">
              <div className="truncate font-medium text-foreground">{s.section_path ?? 'Document'}</div>
              <p className="mt-0.5 line-clamp-2 whitespace-pre-wrap text-muted-foreground">{s.excerpt}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

export type AnswerState = {
  content: string
  sources: Source[]
  status: 'streaming' | 'done' | 'stopped' | 'error'
  error?: string
}

function Thinking() {
  return (
    <p className="flex items-center gap-2 text-sm text-muted-foreground">
      <span aria-hidden className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="size-1.5 rounded-full bg-muted-foreground/60 motion-safe:animate-pulse"
            style={{ animationDelay: `${i * 180}ms` }}
          />
        ))}
      </span>
      Thinking…
    </p>
  )
}

function AnswerBody({ answer }: { answer: AnswerState }) {
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {answer.content ? (
        <SafeMarkdown streaming={answer.status === 'streaming'}>{answer.content}</SafeMarkdown>
      ) : answer.status === 'streaming' ? (
        <Thinking />
      ) : null}
      {answer.status === 'stopped' && (
        <p className="flex items-center gap-1.5 text-caption text-muted-foreground">
          <Square className="size-3" aria-hidden /> Stopped.
        </p>
      )}
      {answer.status === 'error' && (
        <Callout tone="destructive" role="alert">
          {answer.error}
        </Callout>
      )}
      <SourcesList sources={answer.sources} />
    </div>
  )
}

export function Avatar() {
  return (
    <span aria-hidden className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground ring-1 ring-primary/15">
      <Sparkles className="size-3.5" />
    </span>
  )
}

/** The user's message: a quiet bubble, right-aligned. */
export function UserMessage({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-[85%] self-end rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-body break-words whitespace-pre-wrap text-secondary-foreground">
      {children}
    </div>
  )
}

/** One assistant answer. With a `label` it is one column of the side-by-side comparison; without, a normal chat row. */
export function AnswerView({ label, answer, accent = false }: { label?: ReactNode; answer: AnswerState; accent?: boolean }) {
  if (label) {
    return (
      <div className="flex min-w-0 flex-col gap-3">
        <div className="flex items-center gap-2 text-eyebrow">
          <span aria-hidden className={cn('size-1.5 rounded-full', accent ? 'bg-primary' : 'bg-muted-foreground/50')} />
          {label}
        </div>
        <AnswerBody answer={answer} />
      </div>
    )
  }
  return (
    <div className="flex min-w-0 gap-3">
      <Avatar />
      <div className="min-w-0 flex-1">
        <AnswerBody answer={answer} />
      </div>
    </div>
  )
}
