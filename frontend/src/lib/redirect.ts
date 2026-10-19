/** Only allow in-app relative paths as the post-login destination (no open redirects). */
export function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\')) return '/projects'
  return raw
}
