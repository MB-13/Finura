import { Loader2 } from 'lucide-react'

export function FullPageSpinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex min-h-[50vh] items-center justify-center gap-2.5 text-sm text-muted-foreground" role="status">
      <Loader2 className="size-5 animate-spin text-primary motion-reduce:animate-none" aria-hidden />
      <span>{label}</span>
    </div>
  )
}
