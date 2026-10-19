import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from '@/lib/api/schema'
import { env } from '@/lib/env'
import { getAccessToken } from '@/lib/supabase'

/** Error envelope returned by the API: {error, message, details?}. */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: Record<string, unknown> | undefined

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** Field errors from a 422 response, keyed by field name. */
  get fieldErrors(): Record<string, string[]> {
    const fields = this.details?.['fields']
    return fields && typeof fields === 'object' ? (fields as Record<string, string[]>) : {}
  }
}

export function toApiError(status: number, body: unknown): ApiError {
  if (body && typeof body === 'object' && 'error' in body && 'message' in body) {
    const b = body as { error: string; message: string; details?: Record<string, unknown> }
    return new ApiError(status, b.error, b.message, b.details)
  }
  return new ApiError(status, 'http_error', `Request failed (${status})`)
}

type TokenSource = () => Promise<string | null>

export function authMiddleware(getToken: TokenSource): Middleware {
  return {
    async onRequest({ request }) {
      const token = await getToken()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    },
  }
}

export function createApi(baseUrl: string = env.apiUrl, getToken: TokenSource = getAccessToken) {
  // resolve fetch at call time (not import time) so tests and polyfills can replace it
  const client = createClient<paths>({ baseUrl, fetch: (request) => globalThis.fetch(request) })
  client.use(authMiddleware(getToken))
  return client
}

export const api = createApi()

/** Unwrap an openapi-fetch result: return data or throw ApiError. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.error !== undefined || !result.response.ok) {
    throw toApiError(result.response.status, result.error)
  }
  return result.data as T
}
