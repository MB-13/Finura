import { Cpu, FileText, MessageSquare } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router'

import { AppFrame } from '@/components/AppFrame'
import { Logo } from '@/components/Logo'
import { ThemeToggle } from '@/components/theme/ThemeToggle'
import { Decor, ReviewVignette } from '@/features/marketing/vignettes'

const points = [
  {
    icon: FileText,
    text: 'Your documents become training examples you review and approve.',
  },
  { icon: Cpu, text: 'Training runs on a free GPU in your own account.' },
  {
    icon: MessageSquare,
    text: 'Chat with the result, with answers that cite your files.',
  },
]

/** Split sign-in frame: form column on the left, product vignette and value points on the right (lg+ only). */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen bg-background lg:grid-cols-2">
      <div className="flex min-h-screen flex-col lg:min-h-0">
        <header className="flex h-14 w-full items-center justify-between px-4 sm:px-8">
          <Link to="/" aria-label="DocTune home" className="rounded-md">
            <Logo />
          </Link>
          <ThemeToggle />
        </header>
        <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center px-4 py-8 sm:px-0">{children}</main>
        <footer className="flex gap-5 px-4 py-6 text-caption text-muted-foreground sm:px-8">
          <Link to="/privacy" className="rounded-sm hover:text-foreground">
            Privacy
          </Link>
          <Link to="/terms" className="rounded-sm hover:text-foreground">
            Terms
          </Link>
          <Link to="/docs" className="rounded-sm hover:text-foreground">
            Help
          </Link>
        </footer>
      </div>
      <aside className="relative hidden flex-col justify-center gap-10 overflow-hidden border-l bg-muted/30 px-12 py-16 lg:flex">
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-glow" />
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-dots" />
        <div className="relative mx-auto flex w-full max-w-md flex-col gap-8">
          <h2 className="text-display-sm">
            Your documents, <span className="text-muted-foreground">answering your way</span>
          </h2>
          <ul className="flex flex-col gap-3">
            {points.map((p) => (
              <li key={p.text} className="flex items-start gap-3 text-body text-muted-foreground">
                <p.icon className="mt-1 size-4 shrink-0 text-foreground" aria-hidden />
                {p.text}
              </li>
            ))}
          </ul>
          <Decor>
            <AppFrame title="Dataset review" fade className="h-72" bodyClassName="p-5">
              <ReviewVignette />
            </AppFrame>
          </Decor>
        </div>
      </aside>
    </div>
  )
}
