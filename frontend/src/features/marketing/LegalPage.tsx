import { TriangleAlert } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { PageHeader } from '@/components/PageHeader'
import { GuideRails } from '@/components/marketing/GuideRails'
import { Prose } from '@/features/marketing/Prose'

export function DraftNotice() {
  return (
    <div
      role="note"
      className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning-muted p-4 text-sm text-warning-muted-foreground"
    >
      <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
      <p>
        <strong>DRAFT.</strong> This text is a plain-language draft and is not legal advice. A lawyer must review it before DocTune launches.
      </p>
    </div>
  )
}

type TocItem = { id: string; text: string }

const slugify = (s: string) =>
  s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')

export function LegalPage({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  const bodyRef = useRef<HTMLDivElement>(null)
  const [toc, setToc] = useState<TocItem[]>([])

  // Build the table of contents from the page's own <h2>s so the copy stays plain JSX.
  useEffect(() => {
    const heads = Array.from(bodyRef.current?.querySelectorAll('h2') ?? [])
    setToc(
      heads.map((h) => {
        const text = h.textContent ?? ''
        if (!h.id) h.id = slugify(text)
        return { id: h.id, text }
      }),
    )
  }, [children])

  return (
    <GuideRails className="max-sm:border-x-0">
      <div className="px-4 py-10 sm:px-6 sm:py-14">
        <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_14rem]">
          <article className="flex min-w-0 flex-col gap-6">
            <PageHeader title={title} description={`Last updated: ${updated}`} />
            <DraftNotice />
            <div ref={bodyRef}>
              <Prose>{children}</Prose>
            </div>
          </article>
          {toc.length > 2 && (
            <nav aria-label="On this page" className="sticky top-24 hidden h-fit flex-col gap-2 lg:flex">
              <div className="text-eyebrow">On this page</div>
              <ul className="flex flex-col border-l">
                {toc.map((item) => (
                  <li key={item.id}>
                    <a
                      href={`#${item.id}`}
                      className="-ml-px block border-l border-transparent py-1 pl-3 text-caption text-muted-foreground transition-colors hover:border-foreground/40 hover:text-foreground"
                    >
                      {item.text}
                    </a>
                  </li>
                ))}
              </ul>
            </nav>
          )}
        </div>
      </div>
    </GuideRails>
  )
}
