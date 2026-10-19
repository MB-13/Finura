import { ArrowRight, BookOpen, Cpu, KeyRound, Layers, Terminal, type LucideIcon } from 'lucide-react'
import { Link, useParams } from 'react-router'

import { PageHeader } from '@/components/PageHeader'
import { DOCS, findDoc } from '@/features/marketing/docs-content'
import { GuideRails } from '@/components/marketing/GuideRails'
import { Prose } from '@/features/marketing/Prose'
import { NotFound } from '@/routes/NotFound'

const icons: Record<string, LucideIcon> = {
  'groq-key': KeyRound,
  'gemini-key': KeyRound,
  'run-notebook': Cpu,
  ollama: Terminal,
  'why-finetune-rag': Layers,
}

export function DocsIndex() {
  return (
    <GuideRails className="max-sm:border-x-0">
      <div className="flex flex-col gap-8 px-4 py-10 sm:px-6 sm:py-14">
        <PageHeader title="Help" description="Short guides for each step, in plain language." />
        <ul className="grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-2">
          {DOCS.map((d) => {
            const Icon = icons[d.slug] ?? BookOpen
            return (
              <li key={d.slug} className="group relative flex gap-4 bg-background p-6 transition-colors focus-within:bg-accent/40 hover:bg-accent/40">
                <Icon className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <Link to={`/docs/${d.slug}`} className="text-card-title after:absolute after:inset-0 focus-visible:outline-none">
                    {d.title}
                  </Link>
                  <p className="mt-1 text-sm text-muted-foreground">{d.summary}</p>
                </div>
                <ArrowRight
                  className="mt-1 size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground"
                  aria-hidden
                />
              </li>
            )
          })}
        </ul>
      </div>
    </GuideRails>
  )
}

export function DocsPage() {
  const { slug } = useParams()
  const doc = findDoc(slug)
  if (!doc) return <NotFound />
  const others = DOCS.filter((d) => d.slug !== doc.slug)
  return (
    <GuideRails className="max-sm:border-x-0">
      <div className="px-4 py-10 sm:px-6 sm:py-14">
        <article className="flex max-w-3xl flex-col gap-6">
          <PageHeader title={doc.title} description={doc.summary} back={{ to: '/docs', label: 'All guides' }} />
          <Prose>{doc.body}</Prose>
        </article>
        <nav aria-label="More guides" className="mt-14 max-w-3xl border-t pt-6">
          <div className="text-eyebrow">More guides</div>
          <ul className="mt-3 flex flex-col gap-1.5">
            {others.map((d) => (
              <li key={d.slug}>
                <Link to={`/docs/${d.slug}`} className="text-sm font-medium text-primary underline-offset-4 hover:underline">
                  {d.title}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </div>
    </GuideRails>
  )
}
