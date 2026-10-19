import type { FetchEventSourceInit } from '@microsoft/fetch-event-source'
import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { ChatStreamError, streamChat, type EventSourceFn } from '@/features/playground/chat-stream'
import { PlaygroundPage } from '@/features/playground/PlaygroundPage'
import { jsonResponse, stubApi, type Handler } from '@/test/api'
import { PROJECT_ID } from '@/test/fixtures'
import { renderRoutes } from '@/test/render'

const status = (over = {}) => ({ available: true, reason: null, state: 'warm', source: 'final', checkpoint_step: null, model: 'Qwen3.5 4B', ...over })
const statusHandler = (over = {}): Handler => (url, req) =>
  url.pathname === `/projects/${PROJECT_ID}/playground/status` && req.method === 'GET' ? jsonResponse(status(over)) : undefined

type Call = { init: FetchEventSourceInit; body: Record<string, unknown>; finish: () => void }

/** Fake fetchEventSource: each call is recorded; the test drives events by hand. */
function fakeConnect() {
  const calls: Call[] = []
  const connect: EventSourceFn = (_url, init) =>
    new Promise<void>((resolve, reject) => {
      const call: Call = { init, body: JSON.parse(String(init.body)), finish: () => resolve() }
      calls.push(call)
      init.signal?.addEventListener('abort', () => resolve())
      const rejectWith = (e: unknown) => reject(e)
      void Promise.resolve(init.onopen?.(new Response(null, { status: 200 }))).catch(rejectWith)
    })
  return { calls, connect }
}

const emit = (call: Call, event: string, data: unknown) =>
  act(() => {
    call.init.onmessage?.({ id: '', event, data: JSON.stringify(data), retry: undefined })
  })

async function ask(text: string) {
  await userEvent.type(await screen.findByLabelText('Your message'), text)
  await userEvent.click(screen.getByRole('button', { name: /Send/ }))
}

describe('PlaygroundPage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('streams tokens into the answer and shows sources under it', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} getToken={async () => 'tok'} />)
    await ask('How do I reset it?')
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]!.body).toMatchObject({ use_rag: true, compare_base: false, temperature: 0.7, max_tokens: 384, messages: [{ role: 'user', content: 'How do I reset it?' }] })
    emit(calls[0]!, 'sources', [{ chunk_id: 'c1', section_path: 'Setup > Reset', excerpt: 'Hold the button.' }])
    emit(calls[0]!, 'token', { text: 'Hold ' })
    emit(calls[0]!, 'token', { text: 'the **button**.' })
    expect(await screen.findByText('button', { selector: 'strong' })).toBeInTheDocument()
    expect(screen.getByText('Sources (1)')).toBeInTheDocument()
    expect(screen.getByText('Setup > Reset', { exact: false })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Stop/ })).toBeInTheDocument()
    emit(calls[0]!, 'done', { usage: {} })
    act(() => calls[0]!.finish())
    expect(await screen.findByRole('button', { name: /Send/ })).toBeInTheDocument()
  })

  it('renders markdown tables in answers', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} getToken={async () => 'tok'} />)
    await ask('Compare plans')
    await waitFor(() => expect(calls).toHaveLength(1))
    emit(calls[0]!, 'token', { text: '| Plan | Price |\n| --- | --- |\n| Free | 0 |\n' })
    const table = await screen.findByRole('table')
    expect(table).toHaveTextContent('Free')
    expect(screen.getByRole('columnheader', { name: 'Price' })).toBeInTheDocument()
  })

  it('sends the Authorization header from the token source', async () => {
    const spy = vi.fn(async () => new Response(null))
    vi.stubGlobal('fetch', spy)
    let init!: FetchEventSourceInit
    const controller = new AbortController()
    void streamChat(
      PROJECT_ID,
      { messages: [{ role: 'user', content: 'hi' }], use_rag: true, compare_base: false, temperature: 0.7, max_tokens: 100 },
      { onToken: () => {} },
      controller.signal,
      { connect: (_u, i) => ((init = i), new Promise<void>(() => {})), getToken: async () => 'abc' },
    )
    await init.fetch!('http://x/chat', { headers: { Accept: 'text/event-stream' } })
    const headers = (spy.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer abc')
    expect(init.method).toBe('POST')
    controller.abort()
  })

  it('stop aborts the request and keeps the partial answer', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} />)
    await ask('Hello')
    await waitFor(() => expect(calls).toHaveLength(1))
    emit(calls[0]!, 'token', { text: 'Partial answer' })
    await userEvent.click(await screen.findByRole('button', { name: /Stop/ }))
    expect(calls[0]!.init.signal!.aborted).toBe(true)
    expect(await screen.findByText('Stopped.')).toBeInTheDocument()
    expect(screen.getByText('Partial answer')).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: /Send/ })).toBeInTheDocument()
  })

  it('does not render model HTML: a script tag is not a script element', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} />)
    const container = document.body
    await ask('x')
    await waitFor(() => expect(calls).toHaveLength(1))
    emit(calls[0]!, 'token', { text: 'Safe <script>window.pwned = 1</script> text <img src=x onerror="window.pwned=1"> [link](javascript:alert(1)) ![i](http://evil/x.png)' })
    expect(await screen.findByText(/Safe/)).toBeInTheDocument()
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('[onerror]')).toBeNull()
    expect(container.querySelector('a[href^="javascript"]')).toBeNull()
  })

  it('keeps model headings out of the page outline and in-page links in the page', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} />)
    await ask('x')
    await waitFor(() => expect(calls).toHaveLength(1))
    emit(calls[0]!, 'token', { text: '# Big title\n\nNote[^1] and [site](https://example.com)\n\n[^1]: The footnote.' })
    expect(await screen.findByText('Big title')).toBeInTheDocument()
    // only the page's own h1 ("Playground") exists; model headings are role=heading level 3 paragraphs, never h1-h6
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
    expect(screen.getByText('Big title').tagName).toBe('P')
    expect(screen.getByText('Big title')).toHaveAttribute('aria-level', '3')
    expect(screen.getByRole('link', { name: 'site' })).toHaveAttribute('target', '_blank')
    const fragment = document.querySelector<HTMLAnchorElement>('a[href^="#"]')
    expect(fragment).not.toBeNull()
    expect(fragment).not.toHaveAttribute('target')
  })

  it('marks the log busy while streaming and idle when done', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} />)
    const log = await screen.findByRole('log', { name: 'Conversation' })
    expect(log).toHaveAttribute('aria-busy', 'false')
    await ask('hi')
    await waitFor(() => expect(calls).toHaveLength(1))
    emit(calls[0]!, 'token', { text: 'partial' })
    expect(log).toHaveAttribute('aria-busy', 'true')
    emit(calls[0]!, 'done', {})
    act(() => calls[0]!.finish())
    await waitFor(() => expect(log).toHaveAttribute('aria-busy', 'false'))
  })

  it('compare mode sends a second, sequential request with compare_base and shows both answers', async () => {
    stubApi(statusHandler())
    const { calls, connect } = fakeConnect()
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} />)
    await userEvent.click(await screen.findByLabelText(/Compare with base model/))
    await ask('Q')
    await waitFor(() => expect(calls).toHaveLength(1))
    expect(calls[0]!.body.compare_base).toBe(false)
    emit(calls[0]!, 'token', { text: 'tuned answer' })
    emit(calls[0]!, 'done', {})
    act(() => calls[0]!.finish())
    await waitFor(() => expect(calls).toHaveLength(2))
    expect(calls[1]!.body.compare_base).toBe(true)
    emit(calls[1]!, 'token', { text: 'base answer' })
    emit(calls[1]!, 'done', {})
    act(() => calls[1]!.finish())
    expect(await screen.findByText('tuned answer')).toBeInTheDocument()
    expect(screen.getByText('base answer')).toBeInTheDocument()
    expect(screen.getByText('Your tuned model')).toBeInTheDocument()
    expect(screen.getByText('Original model')).toBeInTheDocument()
  })

  it('shows a friendly message for 429', async () => {
    stubApi(statusHandler())
    const connect: EventSourceFn = async (_u, init) => {
      await init.onopen!(new Response(JSON.stringify({ error: 'rate_limited', message: 'slow' }), { status: 429 }))
    }
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} connect={connect} />)
    await ask('hi')
    expect(await screen.findByRole('alert')).toHaveTextContent(/only one answer is written at a time/)
  })

  it('warms up on open and polls the status until warm', async () => {
    let polls = 0
    const calls = stubApi(
      (url, req) => {
        if (url.pathname !== `/projects/${PROJECT_ID}/playground/status` || req.method !== 'GET') return undefined
        polls++
        return jsonResponse(polls === 1 ? status({ state: 'cold' }) : polls < 4 ? status({ state: 'warming' }) : status({ state: 'warm' }))
      },
      (url, req) =>
        url.pathname.endsWith('/playground/warmup') && req.method === 'POST' ? jsonResponse(status({ state: 'warming' }), 202) : undefined,
    )
    vi.useFakeTimers({ shouldAdvanceTime: true })
    try {
      renderRoutes(<PlaygroundPage projectId={PROJECT_ID} />)
      expect(await screen.findByText(/Loading your model/)).toBeInTheDocument()
      expect(calls.filter((c) => c.url.pathname.endsWith('/warmup'))).toHaveLength(1)
      expect(screen.getByLabelText('Your message')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Send/ })).toBeDisabled()
      for (let i = 0; i < 4 && !screen.queryByText('Ready'); i++) {
        await act(async () => {
          await vi.advanceTimersByTimeAsync(3100)
        })
      }
      await waitFor(() => expect(screen.getByText('Ready')).toBeInTheDocument())
      expect(calls.filter((c) => c.url.pathname.endsWith('/warmup'))).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('shows the status bar for a checkpoint source and the Ollama link', async () => {
    stubApi(statusHandler({ source: 'checkpoint', checkpoint_step: 340 }))
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} />)
    expect(await screen.findByText('Checkpoint · step 340')).toBeInTheDocument()
    expect(screen.getByText('Qwen3.5 4B')).toBeInTheDocument()
    // one persistent live region holds the state badge
    expect(screen.getAllByRole('status').some((el) => el.textContent?.includes('Ready'))).toBe(true)
    expect(screen.getByRole('link', { name: 'Run it locally with Ollama' })).toHaveAttribute('href', '/docs/ollama')
  })

  it('explains when the model is too big and points to Ollama instead of waiting', async () => {
    stubApi(statusHandler({ available: false, reason: 'Qwen3 8B is bigger than this server can run for chat.', reason_code: 'too_large' }))
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} />)
    expect(await screen.findByText('This model is too big for the playground')).toBeInTheDocument()
    expect(screen.queryByText('The playground is not available yet')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Run it with Ollama' })).toHaveAttribute('href', '/docs/ollama')
  })

  it('shows the reason when the playground is not available', async () => {
    stubApi(statusHandler({ available: false, reason: 'Your model is still training.' }))
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} />)
    expect(await screen.findByText('Your model is still training.')).toBeInTheDocument()
    expect(screen.queryByLabelText('Your message')).not.toBeInTheDocument()
  })

  it('shows an error state when the status fails', async () => {
    stubApi(() => jsonResponse({ error: 'boom', message: 'Status unavailable' }, 500))
    renderRoutes(<PlaygroundPage projectId={PROJECT_ID} />)
    expect(await screen.findByText('Status unavailable')).toBeInTheDocument()
  })
})

describe('streamChat errors', () => {
  const body = { messages: [{ role: 'user' as const, content: 'hi' }], use_rag: true, compare_base: false, temperature: 0.7, max_tokens: 100 }
  const run = (onopen: Response) =>
    streamChat(PROJECT_ID, body, { onToken: () => {} }, new AbortController().signal, {
      connect: async (_u, init) => {
        await init.onopen!(onopen)
      },
    })

  it('maps 409 warming_up to a typed error', async () => {
    await expect(run(new Response(JSON.stringify({ error: 'warming_up', message: 'Loading' }), { status: 409 }))).rejects.toMatchObject({
      kind: 'warming_up',
    })
  })

  it('maps an error event to a failed error', async () => {
    const p = streamChat(PROJECT_ID, body, { onToken: () => {} }, new AbortController().signal, {
      connect: async (_u, init) => {
        init.onmessage?.({ id: '', event: 'error', data: JSON.stringify({ message: 'Out of memory' }), retry: undefined })
      },
    })
    await expect(p).rejects.toBeInstanceOf(ChatStreamError)
    await expect(p).rejects.toThrow('Out of memory')
  })
})
