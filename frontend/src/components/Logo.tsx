import { cn } from '@/lib/utils'

/** DocTune mark: a document page with a tuning slider through it. Decorative; pair with the wordmark. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cn('size-7 shrink-0', className)}>
      <rect width="32" height="32" rx="9" className="fill-primary" />
      <path
        d="M10.5 7.5h7.2l4.3 4.3v11.2a1.5 1.5 0 0 1-1.5 1.5h-10a1.5 1.5 0 0 1-1.5-1.5v-14a1.5 1.5 0 0 1 1.5-1.5Z"
        className="fill-primary-foreground/20 stroke-primary-foreground"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path d="M12.5 16h7M12.5 20h7" className="stroke-primary-foreground" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="16.5" cy="16" r="1.9" className="fill-primary-foreground stroke-primary" strokeWidth="1" />
    </svg>
  )
}

/** Mark + "DocTune" wordmark. */
export function Logo({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark />
      <span className="text-[1.0625rem] font-semibold tracking-tight max-[420px]:sr-only">DocTune</span>
    </span>
  )
}
