import { Loader2 } from 'lucide-react'

import { Section } from '@/components/Section'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import type { Project } from '@/features/projects/api'
import { StyleSummary } from '@/features/style/StyleSummary'

export function PreviewingPanel({ project }: { project: Project }) {
  const run = project.latest_preview
  const total = run?.total_chunks ?? 0
  const done = run?.done_chunks ?? 0
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0

  return (
    <div className="flex flex-col gap-8">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Loader2 className="size-5 text-primary motion-safe:animate-spin" aria-hidden /> Generating a preview
          </CardTitle>
          <CardDescription>
            We&apos;re writing a few sample pairs in your style. This usually takes under a minute. When it&apos;s done you can check them and decide whether to generate everything.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          {total > 0 && (
            <div className="flex flex-col gap-1.5">
              <div className="flex justify-between text-sm">
                <span className="font-medium">Sections read</span>
                <span className="text-metric text-xs text-muted-foreground" role="status" aria-live="polite">
                  {done} of {total}
                </span>
              </div>
              <Progress value={percent} aria-label="Preview progress" />
            </div>
          )}
          <div aria-busy="true" aria-label="Generating sample pairs" className="flex flex-col gap-3">
            <p className="text-sm font-medium">Generating sample pairs…</p>
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </div>
        </CardContent>
      </Card>
      {project.style && (
        <Section title="Your style" description="Locked while the preview runs.">
          <StyleSummary style={project.style} />
        </Section>
      )}
    </div>
  )
}
