import { vi } from 'vitest'

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

export type Handler = (url: URL, request: Request) => Response | Promise<Response> | undefined

/** Stub global fetch; the first handler returning a response wins, otherwise 404. Returns the call log. */
export function stubApi(...handlers: Handler[]) {
  const calls: { method: string; url: URL; request: Request }[] = []
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const request = input instanceof Request ? input : new Request(input)
    const url = new URL(request.url)
    calls.push({ method: request.method, url, request: request.clone() })
    for (const handler of handlers) {
      const res = await handler(url, request)
      if (res) return res
    }
    return jsonResponse({ error: 'not_found', message: `No stub for ${request.method} ${url.pathname}` }, 404)
  })
  return calls
}

export const META = {
  version: '1',
  notebook_url: 'https://example.com/nb',
  notebook_version: '1',
  limits: { file_mb: 20, project_mb: 50, max_pairs: 2000 },
  providers: [],
}
