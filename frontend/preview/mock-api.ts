/** Stubbed `fetch` for the preview: no backend, no Supabase. First handler that returns a response wins. */
export type Handler = (url: URL, request: Request) => Response | Promise<Response> | undefined

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

/** A request that never resolves: use to preview skeleton / loading states. */
export const pending = (): Promise<Response> => new Promise(() => {})

export function installMockApi(handlers: Handler[]) {
  const realFetch = window.fetch.bind(window)
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init)
    const url = new URL(request.url)
    // only API calls (to the configured API origin, default http://localhost:8000) are stubbed; Vite assets pass through
    if (url.origin === window.location.origin) return realFetch(input, init)
    if (url.pathname.endsWith('/events')) {
      // SSE: stay open and silent
      return new Response(new ReadableStream({ start() {} }), { headers: { 'Content-Type': 'text/event-stream' } })
    }
    for (const handler of handlers) {
      const res = await handler(url, request)
      if (res) return res
    }
    return json({ error: 'not_found', message: `No preview stub for ${request.method} ${url.pathname}` }, 404)
  }
}
