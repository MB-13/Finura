import { ArrowRight, Eye, Pencil } from 'lucide-react'
import { useState } from 'react'

import { Callout } from '@/components/Callout'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { Section } from '@/components/Section'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { EstimateDialog } from '@/features/generation/EstimateDialog'
import type { Project } from '@/features/projects/api'
import { useRunPairs } from '@/features/style/api'
import { PairCard } from '@/features/style/PairCard'

type Props = { project: Project; onTweak: () => void }

export function PreviewResults({ project, onTweak }: Props) {
  const run = project.latest_preview
  const [estimateOpen, setEstimateOpen] = useState(false)
  const done = run?.state === 'done'
  const pairs = useRunPairs(project.id, run?.id, done)
  if (!run) return null

  // a preview only counts for the style it was made with
  const stale = run.style_id !== project.style?.id
  const canGenerate = done && !stale

  return (
    <Section
      title={
        <span className="flex flex-wrap items-center gap-2">
          Preview
          {stale && <Badge variant="outline">Out of date</Badge>}
        </span>
      }
      description={
        done
          ? 'Check that these sample pairs sound the way you want before generating everything.'
          : run.state === 'failed'
            ? 'The preview could not be completed.'
            : 'Your preview is being prepared.'
      }
    >
      {stale && (
        <Callout tone="warning" role="status">
          This preview was made with an earlier version of your style. Save &amp; generate a new preview to continue.
        </Callout>
      )}

      {run.state === 'failed' && (
        <Callout tone="destructive" role="alert" title="Preview failed">
          {project.status_message && <p>{project.status_message}</p>}
          {run.error && <p className="text-muted-foreground">{run.error}</p>}
        </Callout>
      )}

      {done &&
        (pairs.isPending ? (
          <div aria-busy="true" aria-label="Loading preview pairs" className="flex flex-col gap-3">
            <Skeleton className="h-40 rounded-xl" />
            <Skeleton className="h-40 rounded-xl" />
          </div>
        ) : pairs.isError ? (
          <ErrorState message={pairs.error.message} onRetry={() => pairs.refetch()} />
        ) : pairs.data.length === 0 ? (
          <EmptyState icon={Eye} title="No sample pairs were produced" description="Try a clearer description or more examples." />
        ) : (
          <ul className="flex flex-col gap-3" aria-label="Preview pairs">
            {pairs.data.map((pair, i) => (
              <PairCard key={pair.id} pair={pair} index={i + 1} />
            ))}
          </ul>
        ))}

      <Card className="border-primary/30 bg-accent/30">
        <CardContent className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h3 className="text-card-title">Happy with how these sound?</h3>
            <p className="text-sm text-muted-foreground">
              Generating the full dataset reads all your documents and can take a while. You can stop at any time.
              {' '}If something is off, tweak the style below and make a new preview.
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button disabled={!canGenerate} onClick={() => setEstimateOpen(true)}>
              Generate full dataset <ArrowRight aria-hidden />
            </Button>
            <Button variant="outline" onClick={onTweak}>
              <Pencil aria-hidden /> Tweak style
            </Button>
          </div>
          {!canGenerate && (
            <p className="text-caption text-muted-foreground">
              {stale ? 'Generate a new preview with your current style to continue.' : 'Available once the preview is done.'}
            </p>
          )}
        </CardContent>
      </Card>
      <EstimateDialog projectId={project.id} open={estimateOpen} onOpenChange={setEstimateOpen} />
    </Section>
  )
}
