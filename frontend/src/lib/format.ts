const rtf = new Intl.RelativeTimeFormat('en', { numeric: 'auto' })

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

/** "3 hours ago", "yesterday", "just now". */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  if (Number.isNaN(seconds)) return ''
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

/** Judge scores: whole numbers stay whole, otherwise one decimal. */
export function formatScore(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

/** "about 25 min", "about 2 h 10 min", "about 3 days" (days win once the run takes longer than one). */
export function formatDuration(minutes: number, days: number): string {
  if (days > 1) return `about ${Math.ceil(days)} days`
  if (minutes < 1) return 'under a minute'
  if (minutes < 60) return `about ${Math.round(minutes)} min`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  return m === 0 ? `about ${h} h` : `about ${h} h ${m} min`
}

/** "12 s ago", "4 min ago", "2 h ago" for live labels (falls back to the relative formatter for days). */
export function formatAgo(iso: string, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (Number.isNaN(seconds)) return ''
  if (seconds < 60) return `${seconds} s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  return formatRelative(iso, now)
}

/** "340 KB", "12.4 MB", "1.2 GB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let i = 0
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024
    i++
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[i]}`
}

/** "about 5 min" / "about 1 h 10 min" from seconds. */
export function formatEta(seconds: number): string {
  return formatDuration(seconds / 60, 0)
}
