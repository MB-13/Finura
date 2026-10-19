import { fetchEventSource, type EventSourceMessage, type FetchEventSourceInit } from '@microsoft/fetch-event-source'

import type { ChatMessage, ChatOptions } from '@/features/playground/api'
import { toApiError } from '@/lib/api/client'
import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

/** Signature of `fetchEventSource`; injectable so tests can replace it. */
export type EventSourceFn = (input: RequestInfo, init: FetchEventSourceInit) => Promise<void>

export type Source = { chunk_id: string; section_path: string | null; excerpt: string }

export type ChatErrorKind = 'warming_up' | 'rate_limited' | 'failed'

export class ChatStreamError extends Error {
  readonly kind: ChatErrorKind
  constructor(kind: ChatErrorKind, message: string) {
    super(message)
    this.name = 'ChatStreamError'
    this.kind = kind
  }
}

export type ChatHandlers = {
  onToken: (text: string) => void
  onSources?: (sources: Source[]) => void
  onDone?: () => void
}

export type ChatBody = ChatOptions & { messages: ChatMessage[] }

type Deps = { connect?: EventSourceFn; getToken?: () => Promise<string | null> }

function parse<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T
  } catch {
    return null
  }
}

async function errorFromResponse(response: Response): Promise<ChatStreamError> {
  const body: unknown = await response.json().catch(() => null)
  const err = toApiError(response.status, body)
  if (response.status === 409 && err.code === 'warming_up') return new ChatStreamError('warming_up', err.message)
  if (response.status === 429) {
    return new ChatStreamError('rate_limited', 'Slow down: only one answer is written at a time. Wait for it to finish, then try again.')
  }
  return new ChatStreamError('failed', err.message)
}

/**
 * POST a chat request and stream the answer. Resolves when the answer is complete or `signal` aborts;
 * rejects with ChatStreamError otherwise. Never retries on its own.
 */
export async function streamChat(
  projectId: string,
  body: ChatBody,
  handlers: ChatHandlers,
  signal: AbortSignal,
  { connect = fetchEventSource, getToken = getAccessToken }: Deps = {},
): Promise<void> {
  let finished = false

  await connect(`${env.apiUrl}/projects/${projectId}/playground/chat`, {
    method: 'POST',
    signal,
    openWhenHidden: true,
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    fetch: async (input, init) => {
      const token = await getToken()
      const headers = new Headers(init?.headers)
      if (token) headers.set('Authorization', `Bearer ${token}`)
      return globalThis.fetch(input, { ...init, headers })
    },
    async onopen(response) {
      if (!response.ok) throw await errorFromResponse(response)
    },
    onmessage(ev: EventSourceMessage) {
      switch (ev.event) {
        case 'token': {
          const t = parse<{ text?: string }>(ev.data)
          if (t?.text) handlers.onToken(t.text)
          return
        }
        case 'sources': {
          const s = parse<Source[]>(ev.data)
          if (Array.isArray(s)) handlers.onSources?.(s)
          return
        }
        case 'done':
          finished = true
          handlers.onDone?.()
          return
        case 'error': {
          const e = parse<{ message?: string }>(ev.data)
          throw new ChatStreamError('failed', e?.message ?? 'The model could not finish this answer.')
        }
      }
    },
    onclose() {
      if (!finished && !signal.aborted) throw new ChatStreamError('failed', 'The connection closed before the answer finished.')
    },
    onerror(err) {
      // never auto-retry: a retry would send the user's message twice
      throw err
    },
  })
}
