import { ArrowUp, BookOpen, Columns2, FileText, MessageSquareDashed, Square, type LucideIcon } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { Link } from 'react-router'

import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { usePlaygroundStatus, useWarmup, type ChatMessage, type PlaygroundStatus } from '@/features/playground/api'
import { Avatar, AnswerView, UserMessage, type AnswerState } from '@/features/playground/ChatMessageView'
import { ChatStreamError, streamChat, type EventSourceFn } from '@/features/playground/chat-stream'
import { ChatSettings } from '@/features/playground/ChatSettings'
import { PlaygroundStatusBar } from '@/features/playground/PlaygroundStatusBar'
import { cn } from '@/lib/utils'

export type Turn = { id: number; question: string; tuned: AnswerState; base: AnswerState | null }

const EMPTY: AnswerState = { content: '', sources: [], status: 'streaming' }

type Props = {
  projectId: string
  /** Replace the SSE implementation (tests). */
  connect?: EventSourceFn
  getToken?: () => Promise<string | null>
  /** Start with a conversation already on screen (tests and the UI preview). */
  initialTurns?: Turn[]
  initialCompare?: boolean
}

const STARTERS = [
  'Summarise the main points of my documents.',
  'What should a new customer know first?',
  'Explain the most important rule in simple words.',
]

const UNAVAILABLE_TITLES: Record<NonNullable<PlaygroundStatus['reason_code']>, string> = {
  no_model: 'The playground is not available yet',
  not_ready: 'The playground is not available yet',
  preparing: 'Getting your model ready for chat',
  prepare_failed: "We couldn't open your model here",
  too_large: 'This model is too big for the playground',
}

export function PlaygroundPage({ projectId, connect, getToken, initialTurns, initialCompare }: Props) {
  const status = usePlaygroundStatus(projectId)
  const warmup = useWarmup(projectId)
  const [turns, setTurns] = useState<Turn[]>(initialTurns ?? [])
  const [input, setInput] = useState('')
  const [useRag, setUseRag] = useState(true)
  const [compare, setCompare] = useState(initialCompare ?? false)
  const [temperature, setTemperature] = useState(0.7)
  const [maxTokens, setMaxTokens] = useState(384)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const nextId = useRef(1)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const warmedUp = useRef(false)

  const data = status.data
  const available = data?.available === true
  const warm = data?.state === 'warm'

  // warm the model up as soon as the page opens (once), then the status query polls until it is warm
  const { mutate: startWarmup } = warmup
  useEffect(() => {
    if (available && data?.state === 'cold' && !warmedUp.current) {
      warmedUp.current = true
      startWarmup()
    }
  }, [available, data?.state, startWarmup])

  useEffect(() => () => abortRef.current?.abort(), [])
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [turns, available])
  // the composer grows with its content (up to a limit)
  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input, available])

  const patch = useCallback((id: number, which: 'tuned' | 'base', fn: (a: AnswerState) => AnswerState) => {
    setTurns((all) =>
      all.map((t) => {
        if (t.id !== id) return t
        const current = which === 'tuned' ? t.tuned : (t.base ?? EMPTY)
        return which === 'tuned' ? { ...t, tuned: fn(current) } : { ...t, base: fn(current) }
      }),
    )
  }, [])

  async function runOne(id: number, which: 'tuned' | 'base', messages: ChatMessage[], signal: AbortSignal): Promise<void> {
    try {
      await streamChat(
        projectId,
        { messages, use_rag: useRag, compare_base: which === 'base', temperature, max_tokens: maxTokens },
        {
          onToken: (t) => {
            patch(id, which, (a) => ({ ...a, content: a.content + t }))
          },
          onSources: (sources) => patch(id, which, (a) => ({ ...a, sources })),
          onDone: () => patch(id, which, (a) => ({ ...a, status: 'done' })),
        },
        signal,
        { connect, getToken },
      )
      if (signal.aborted) patch(id, which, (a) => ({ ...a, status: 'stopped' }))
    } catch (err) {
      const e = err instanceof ChatStreamError ? err : new ChatStreamError('failed', err instanceof Error ? err.message : 'Something went wrong.')
      if (e.kind === 'warming_up') {
        setNotice('Your model is still loading. Try again in a moment.')
        startWarmup()
        patch(id, which, (a) => ({ ...a, status: 'error', error: 'The model was not loaded yet. Send your message again once it says Ready.' }))
      } else {
        patch(id, which, (a) => ({ ...a, status: 'error', error: e.message }))
      }
      throw e
    }
  }

  async function send(e?: FormEvent) {
    e?.preventDefault()
    const question = input.trim()
    if (!question || busy || !warm) return
    const id = nextId.current++
    const history: ChatMessage[] = turns.flatMap((t) =>
      t.tuned.content ? [{ role: 'user' as const, content: t.question }, { role: 'assistant' as const, content: t.tuned.content }] : [],
    )
    const messages: ChatMessage[] = [...history, { role: 'user', content: question }]
    const controller = new AbortController()
    abortRef.current = controller
    setInput('')
    setNotice(null)
    setBusy(true)
    setTurns((all) => [...all, { id, question, tuned: EMPTY, base: compare ? EMPTY : null }])
    try {
      await runOne(id, 'tuned', messages, controller.signal)
      // only one answer at a time is allowed, so the base-model answer is a second, sequential request
      if (compare && !controller.signal.aborted) await runOne(id, 'base', messages, controller.signal)
    } catch {
      // the error is already shown on the answer
    } finally {
      setBusy(false)
      abortRef.current = null
      // an answer that never started (stopped or the first request failed) must not look like it is still loading
      setTurns((all) =>
        all.map((t) => {
          if (t.id !== id) return t
          const stop = (a: AnswerState): AnswerState => (a.status === 'streaming' ? { ...a, status: 'stopped' } : a)
          return { ...t, tuned: stop(t.tuned), base: t.base ? stop(t.base) : null }
        }),
      )
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void send()
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        back={{ to: `/projects/${projectId}`, label: 'Back to project' }}
        title="Playground"
        description="Chat with your fine-tuned model. It answers in your style, using passages from your documents."
      />

      {status.isError ? (
        <ErrorState message={status.error.message} onRetry={() => status.refetch()} />
      ) : !data ? (
        <Skeleton aria-busy="true" aria-label="Loading playground" className="h-[28rem] rounded-xl" />
      ) : !data.available ? (
        <div role="status">
          <EmptyState
            icon={MessageSquareDashed}
            title={UNAVAILABLE_TITLES[data.reason_code ?? 'not_ready']}
            description={data.reason ?? 'It opens once your model is trained, or while training is paused with a saved checkpoint.'}
            className="py-16"
            action={
              // when the playground will never open for this model, running it locally is the way forward
              data.reason_code === 'too_large' || data.reason_code === 'prepare_failed' ? (
                <>
                  <Button asChild>
                    <Link to="/docs/ollama">Run it with Ollama</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to={`/projects/${projectId}`}>Download your model</Link>
                  </Button>
                </>
              ) : (
                <>
                  <Button asChild>
                    <Link to={`/projects/${projectId}`}>Open project</Link>
                  </Button>
                  <Button asChild variant="outline">
                    <Link to="/docs/ollama">Run your model locally with Ollama</Link>
                  </Button>
                </>
              )
            }
          />
        </div>
      ) : (
        <div className="flex h-[calc(100dvh-14rem)] min-h-[30rem] min-w-0 flex-col lg:h-[calc(100dvh-16rem)] lg:min-h-[34rem]">
          <PlaygroundStatusBar status={data} />

          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto py-6" role="log" aria-live="polite" aria-busy={busy} aria-label="Conversation">
            {turns.length === 0 ? (
              <div className="flex min-h-full flex-col items-center justify-center gap-6 text-center">
                <div className="flex flex-col items-center gap-3">
                  <Avatar />
                  <div>
                    <p className="text-section-title">Ask your model a question about your documents.</p>
                    <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
                      It has learned your style. For facts, it looks them up in your documents and shows where each answer came from.
                    </p>
                  </div>
                </div>
                <div className="flex w-full max-w-2xl flex-col items-center gap-2.5">
                  <p className="text-eyebrow">Try asking</p>
                  <div className="flex flex-wrap justify-center gap-2">
                    {STARTERS.map((q) => (
                      <button
                        key={q}
                        type="button"
                        onClick={() => {
                          setInput(q)
                          inputRef.current?.focus()
                        }}
                        className="rounded-full border bg-card px-3.5 py-1.5 text-left text-sm shadow-card transition-colors outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className={cn('mx-auto flex w-full flex-col gap-8', turns.some((t) => t.base) ? 'max-w-5xl' : 'max-w-3xl')}>
                {turns.map((t) => (
                  <div key={t.id} className="flex flex-col gap-5">
                    <UserMessage>{t.question}</UserMessage>
                    {t.base ? (
                      <div className="grid gap-6 md:grid-cols-2 md:gap-0 md:divide-x">
                        <div className="min-w-0 md:pr-6">
                          <AnswerView label="Your tuned model" answer={t.tuned} accent />
                        </div>
                        <div className="min-w-0 border-t pt-6 md:border-t-0 md:pt-0 md:pl-6">
                          <AnswerView label="Original model" answer={t.base} />
                        </div>
                      </div>
                    ) : (
                      <AnswerView answer={t.tuned} />
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          <form onSubmit={send} className="mx-auto flex w-full max-w-3xl flex-col gap-2">
            {notice && (
              <p role="status" className="text-caption text-muted-foreground">
                {notice}
              </p>
            )}
            <Label htmlFor="chat-input" className="sr-only">
              Your message
            </Label>
            <div className="flex flex-col rounded-2xl border border-input bg-card p-2 shadow-card transition-[box-shadow,border-color] focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50">
              <Textarea
                ref={inputRef}
                id="chat-input"
                rows={2}
                placeholder={warm ? 'Type a question. Enter to send, Shift+Enter for a new line.' : 'Waiting for the model to load…'}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={onKeyDown}
                className="field-sizing-fixed max-h-48 min-h-14 w-full resize-none border-0 bg-transparent px-2.5 py-2 shadow-none focus-visible:ring-0 dark:bg-transparent"
              />
              <div className="flex items-center gap-2 pt-1">
                <ToggleChip
                  label="Use my documents"
                  text="Use my documents"
                  shortText="Documents"
                  icon={FileText}
                  checked={useRag}
                  onChange={setUseRag}
                />
                <ToggleChip
                  label="Compare with base model"
                  text="Compare"
                  shortText="Compare"
                  icon={Columns2}
                  checked={compare}
                  onChange={setCompare}
                />
                <ChatSettings temperature={temperature} onTemperature={setTemperature} maxTokens={maxTokens} onMaxTokens={setMaxTokens} />
                <div className="ml-auto">
                  {busy ? (
                    <Button type="button" size="icon" variant="outline" className="rounded-full" aria-label="Stop generating" onClick={() => abortRef.current?.abort()}>
                      <Square aria-hidden className="fill-current" />
                    </Button>
                  ) : (
                    <Button type="submit" size="icon" className="rounded-full" aria-label="Send message" disabled={!warm || !input.trim()}>
                      <ArrowUp aria-hidden />
                    </Button>
                  )}
                </div>
              </div>
            </div>
            <p className="flex items-start gap-1.5 px-1 text-caption text-muted-foreground">
              <BookOpen className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              <span>
                Fine-tuning teaches your model a style. Facts come from your documents, so keep &ldquo;Use my documents&rdquo; on.
                <span className="hidden sm:inline"> Enter to send, Shift+Enter for a new line.</span>
              </span>
            </p>
          </form>
        </div>
      )}
    </div>
  )
}

/** A toggle shown as a small pill on the composer toolbar. */
function ToggleChip({
  label,
  text,
  shortText,
  icon: Icon,
  checked,
  onChange,
}: {
  /** Accessible name. */
  label: string
  text: string
  shortText: string
  icon: LucideIcon
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50',
        checked ? 'border-primary/30 bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
      )}
    >
      <Icon className="size-3.5" aria-hidden />
      <span aria-hidden className="hidden sm:inline">
        {text}
      </span>
      <span aria-hidden className="sm:hidden">
        {shortText}
      </span>
      <span aria-hidden className={cn('ml-0.5 size-1.5 rounded-full', checked ? 'bg-primary' : 'bg-muted-foreground/40')} />
    </button>
  )
}
