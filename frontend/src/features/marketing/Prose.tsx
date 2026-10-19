import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** Long-form typography: ~70ch lines, heading scale, lists, inline code and links. */
export function Prose({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'text-body text-foreground/85 [&>*]:max-w-[70ch] [&>:first-child]:mt-0',
        '[&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:scroll-mt-24 [&_h2]:text-lg [&_h2]:leading-7 [&_h2]:font-semibold [&_h2]:tracking-tight [&_h2]:text-foreground',
        '[&_p]:my-3 [&_p]:leading-7',
        '[&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5',
        '[&_li]:my-1.5 [&_li]:pl-1 [&_li]:leading-7 [&_li]:marker:text-muted-foreground',
        '[&_a]:font-medium [&_a]:text-primary [&_a]:underline [&_a]:underline-offset-4 [&_a:hover]:text-primary/80',
        '[&_code]:rounded-sm [&_code]:border [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[0.85em] [&_code]:break-words',
        '[&_strong]:font-semibold [&_strong]:text-foreground',
        className,
      )}
    >
      {children}
    </div>
  )
}
