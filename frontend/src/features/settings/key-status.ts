import { CheckCircle2, Clock, Loader2, OctagonAlert, type LucideIcon } from 'lucide-react'

import type { KeyStatus, ProviderKey } from '@/features/settings/api'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function keyStatusLabel(key: ProviderKey): string {
  switch (key.status) {
    case 'valid':
      return 'Valid'
    case 'invalid':
      return 'Invalid key'
    case 'quota_exhausted':
      return key.quota_reset_at ? `Quota used until ${formatTime(key.quota_reset_at)}` : 'Quota used'
    case 'unverified':
      return 'Checking…'
  }
}

/** Chip look per status: an icon always accompanies the colour. Classes use semantic tokens only. */
export const keyStatusChip: Record<KeyStatus, { icon: LucideIcon; className: string; spin?: boolean }> = {
  valid: { icon: CheckCircle2, className: 'bg-success-muted text-success-muted-foreground' },
  invalid: { icon: OctagonAlert, className: 'bg-destructive-muted text-destructive-muted-foreground' },
  quota_exhausted: { icon: Clock, className: 'bg-warning-muted text-warning-muted-foreground' },
  unverified: { icon: Loader2, className: 'bg-secondary text-secondary-foreground', spin: true },
}
