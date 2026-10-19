import { useSyncExternalStore } from 'react'

/**
 * A job token is shown exactly once. It lives only in this in-memory store (never in the TanStack Query
 * cache, localStorage or sessionStorage) and disappears on reload or when the user confirms they copied it.
 */
export type RevealedToken = { token: string; notebookUrl: string | null; expiresAt: string | null }

const tokens = new Map<string, RevealedToken>()
const listeners = new Set<() => void>()

function emit() {
  listeners.forEach((l) => l())
}

export function revealToken(jobId: string, value: RevealedToken) {
  tokens.set(jobId, value)
  emit()
}

export function forgetToken(jobId: string) {
  if (tokens.delete(jobId)) emit()
}

export function clearAllTokens() {
  tokens.clear()
  emit()
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function useRevealedToken(jobId: string | undefined): RevealedToken | null {
  return useSyncExternalStore(subscribe, () => (jobId ? (tokens.get(jobId) ?? null) : null))
}
