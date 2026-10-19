import { BadgeCheck, Check, ChevronDown, CircleAlert, ClipboardCheck, Download, ListPlus, PackageCheck, Rocket, Table2, Wand2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { Callout } from '@/components/Callout'
import { ErrorState } from '@/components/ErrorState'
import { StatRow } from '@/components/StatRow'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useApproveDataset, useDatasetStats, useExportDataset, useRestyle, type DatasetStats, type ExportShape } from '@/features/dataset/api'
import { useGenerateMore, useResumeRun } from '@/features/generation/api'
import type { Project } from '@/features/projects/api'
import { PanelHeader } from '@/features/training/PanelHeader'
import { TrainSetupDialog } from '@/features/training/TrainSetupDialog'
import { formatScore } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Formats with a well-known layout of their own, offered as a second export next to the chat messages we train on. */
const NATIVE_EXPORT: Record<string, string | null> = { qa_chat: null, instruction: 'Alpaca format', multi_turn: 'ShareGPT format' }

const score = (v: number | null) => (v === null ? '—' : formatScore(v))
const humanize = (s: string) => s.replace(/_/g, ' ')

function StatsView({ stats }: { stats: DatasetStats }) {
  const dropped = Object.entries(stats.dropped_by_reason)
  const words = Object.entries(stats.answer_words)
  return (
    <div className="flex flex-col gap-5">
      <StatRow
        items={[
          { label: 'Pairs kept', value: stats.kept.toLocaleString(), hint: 'used for training' },
          { label: 'Train / eval', value: `${stats.train.toLocaleString()} / ${stats.eval.toLocaleString()}`, hint: 'eval is held out' },
          { label: 'Avg accuracy', value: score(stats.avg_correctness), hint: 'judge score, out of 5' },
          { label: 'Avg style', value: score(stats.avg_style), hint: 'judge score, out of 5' },
        ]}
      />
      <div className="grid gap-4 border-t pt-5 sm:grid-cols-2">
        <section aria-label="Dropped pairs" className="flex flex-col gap-2">
          <h3 className="text-eyebrow">Dropped</h3>
          {dropped.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nothing was dropped.</p>
          ) : (
            <ul className="flex flex-wrap gap-1.5">
              {dropped.map(([reason, n]) => (
                <li key={reason}>
                  <Badge variant="secondary" className="gap-1.5">
                    {humanize(reason)}
                    <span className="text-metric text-xs">{n}</span>
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </section>
        {words.length > 0 && (
          <section aria-label="Answer length" className="flex flex-col gap-2">
            <h3 className="text-eyebrow">Answer length (words)</h3>
            <ul className="flex flex-wrap gap-1.5">
              {words.map(([k, n]) => (
                <li key={k}>
                  <Badge variant="secondary" className="gap-1.5">
                    {humanize(k)}
                    <span className="text-metric text-xs">{n}</span>
                  </Badge>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </div>
  )
}

type Requirement = { label: string; have: number; need: number; ok: boolean; fix: string }

/** The same rules the API enforces on approve, so the user sees what's missing before they click. */
/** A dataset below the recommended size can be completed (if generation stopped early) or approved on purpose. */
function smallDatasetOptions(stats: DatasetStats) {
  if (stats.kept >= stats.min_pairs) return null
  const canApprove = stats.kept >= stats.small_min_pairs && stats.eval >= stats.min_eval && stats.kept <= stats.max_pairs
  if (!stats.resume && !stats.more && !canApprove) return null
  return { resume: stats.resume ?? null, more: stats.more ?? null, canApprove }
}

function requirements(stats: DatasetStats): Requirement[] {
  const dropped = Object.values(stats.dropped_by_reason).reduce((a, b) => a + b, 0)
  return [
    {
      label: `At least ${stats.min_pairs} pairs kept`,
      have: stats.kept,
      need: stats.min_pairs,
      ok: stats.kept >= stats.min_pairs,
      fix:
        dropped > 0
          ? `In the review table, restore some of the ${dropped} dropped pairs or add your own.`
          : 'In the review table, add your own pairs, or add documents and regenerate.',
    },
    {
      label: `At least ${stats.min_eval} ${stats.min_eval === 1 ? 'pair' : 'pairs'} held out for evaluation`,
      have: stats.eval,
      need: stats.min_eval,
      ok: stats.eval >= stats.min_eval,
      fix: 'In the review table, move a few pairs to eval.',
    },
    ...(stats.kept > stats.max_pairs
      ? [
          {
            label: `No more than ${stats.max_pairs.toLocaleString()} pairs`,
            have: stats.kept,
            need: stats.max_pairs,
            ok: false,
            fix: 'Drop some pairs in the review table.',
          },
        ]
      : []),
  ]
}

function Checklist({ id, items }: { id: string; items: Requirement[] }) {
  const missing = items.filter((r) => !r.ok).length
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="flex flex-col gap-3 rounded-lg border bg-muted/30 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={`${id}-title`} className="text-card-title">
          {missing === 0 ? 'Ready to approve' : 'Before you can approve'}
        </h3>
        <span className="text-metric text-xs text-muted-foreground">
          {items.length - missing}/{items.length} done
        </span>
      </div>
      <ul className="flex flex-col divide-y">
        {items.map((r) => {
          const pct = Math.min(100, (r.have / r.need) * 100)
          return (
            <li key={r.label} className="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
              <span
                aria-hidden
                className={cn(
                  'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full',
                  r.ok ? 'bg-success-muted text-success-muted-foreground' : 'bg-warning-muted text-warning-muted-foreground',
                )}
              >
                {r.ok ? <Check className="size-3" /> : <CircleAlert className="size-3" />}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <p className="text-sm font-medium">
                    <span className="sr-only">{r.ok ? 'Done: ' : 'Not done: '}</span>
                    {r.label}
                  </p>
                  <span className="text-metric text-xs text-muted-foreground">
                    {r.have.toLocaleString()} / {r.need.toLocaleString()}
                  </span>
                </div>
                {!r.ok && (
                  <>
                    {r.have < r.need && (
                      <div aria-hidden className="h-1 overflow-hidden rounded-full bg-border/70">
                        <div className="h-full rounded-full bg-warning" style={{ width: `${pct}%` }} />
                      </div>
                    )}
                    <p className="text-caption text-muted-foreground">{r.fix}</p>
                  </>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

function OptionCard({
  icon: Icon,
  title,
  recommended,
  children,
  action,
}: {
  icon: typeof ListPlus
  title: string
  recommended?: boolean
  children: ReactNode
  action: ReactNode
}) {
  return (
    <li className={cn('flex flex-col gap-3 rounded-lg border bg-card p-4', recommended && 'border-primary/40')}>
      <div className="flex items-center gap-2">
        <Icon className="size-4 text-muted-foreground" aria-hidden />
        <h4 className="text-sm font-semibold">{title}</h4>
        {recommended && <Badge variant="secondary">Recommended</Badge>}
      </div>
      <p className="flex-1 text-caption text-muted-foreground">{children}</p>
      <div>{action}</div>
    </li>
  )
}

function MoreDescription({ more }: { more: NonNullable<DatasetStats['more']> }) {
  return (
    <>
      Another pass over <span className="text-metric">{more.sections}</span> document{' '}
      {more.sections === 1 ? 'section' : 'sections'}, asking for up to <span className="text-metric">{more.pairs_to_generate}</span> new
      pairs (some get filtered by the quality check). New questions avoid the ones you already have, and your pairs and edits are kept.
    </>
  )
}

function SmallDatasetChoice({ projectId, stats }: { projectId: string; stats: DatasetStats }) {
  const options = smallDatasetOptions(stats)
  const resume = useResumeRun(projectId)
  const more = useGenerateMore(projectId)
  const approve = useApproveDataset(projectId)
  if (!options) return null
  const runId = options.resume?.run_id
  const busy = resume.isPending || more.isPending || approve.isPending
  return (
    <section aria-labelledby="small-dataset-title" className="flex flex-col gap-3 border-t pt-5">
      <div className="flex flex-col gap-1">
        <h3 id="small-dataset-title" className="text-card-title">
          Your dataset has {stats.kept} of the recommended {stats.min_pairs} pairs
        </h3>
        <p className="text-caption text-muted-foreground">
          {options.resume ? 'Generation was stopped early. ' : ''}Choose how to continue, or add pairs yourself in the review table.
        </p>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {options.resume && (
          <OptionCard
            icon={ListPlus}
            title="Complete generation"
            recommended
            action={
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  resume.mutate(runId ?? '', {
                    onSuccess: () => toast.success('Generation resumed'),
                    onError: (err) => toast.error(err.message),
                  })
                }
              >
                {resume.isPending ? 'Starting…' : 'Complete generation'}
              </Button>
            }
          >
            Generate pairs for the <span className="text-metric">{options.resume.remaining_chunks}</span> of{' '}
            <span className="text-metric">{options.resume.total_chunks}</span> document sections that were skipped. The pairs you have
            and your edits are kept; the train/eval split is redone at the end.
          </OptionCard>
        )}
        {options.more && (
          <OptionCard
            icon={ListPlus}
            title="Generate more pairs"
            recommended
            action={
              <Button
                size="sm"
                disabled={busy}
                onClick={() =>
                  more.mutate(undefined, {
                    onSuccess: () => toast.success('Generating more pairs'),
                    onError: (err) => toast.error(err.message),
                  })
                }
              >
                {more.isPending ? 'Starting…' : 'Generate more pairs'}
              </Button>
            }
          >
            <MoreDescription more={options.more} />
          </OptionCard>
        )}
        {options.canApprove && (
          <OptionCard
            icon={PackageCheck}
            title={`Continue with ${stats.kept} pairs`}
            recommended={!options.resume && !options.more}
            action={
              <Button
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() =>
                  approve.mutate(
                    { allowSmall: true },
                    { onSuccess: () => toast.success('Dataset approved'), onError: (err) => toast.error(err.message) },
                  )
                }
              >
                {approve.isPending ? 'Approving…' : `Approve ${stats.kept} pairs`}
              </Button>
            }
          >
            Train on what you have now. Good for a quick first try, but the model learns your style less reliably with fewer than{' '}
            {stats.min_pairs} pairs.
          </OptionCard>
        )}
      </ul>
    </section>
  )
}

export function ReviewPanel({ project }: { project: Project }) {
  const stats = useDatasetStats(project.id)
  const more = useGenerateMore(project.id)
  const exportDataset = useExportDataset(project.id)
  const approve = useApproveDataset(project.id)
  const restyle = useRestyle(project.id)
  const [confirmRestyle, setConfirmRestyle] = useState(false)
  const [setupOpen, setSetupOpen] = useState(false)
  const version = project.dataset_version
  const reqs = stats.data ? requirements(stats.data) : []
  const blocked = reqs.some((r) => !r.ok)
  // below the recommended size but with a way forward: the choice replaces the checklist and the Approve button
  const choosing = !version && !!stats.data && smallDatasetOptions(stats.data) !== null

  const nativeExport = NATIVE_EXPORT[project.style?.dataset_format ?? 'qa_chat']

  function onExport(shape: ExportShape = 'training') {
    exportDataset.mutate(shape, {
      onSuccess: ({ url }) => window.open(url, '_blank', 'noopener,noreferrer'),
      onError: (err) => toast.error(err.message),
    })
  }

  return (
    <Card>
      <PanelHeader
        icon={ClipboardCheck}
        title={
          <span className="flex flex-wrap items-center gap-2">
            Review your dataset
            {version && (
              <Badge variant="success">
                <BadgeCheck aria-hidden /> Approved v{version.version}
              </Badge>
            )}
          </span>
        }
        description="Look through the pairs, drop or fix any that are off, then approve the dataset when you're happy."
      />
      <CardContent className="flex flex-col gap-6">
        {stats.isPending ? (
          <div aria-busy="true" aria-label="Loading dataset stats" className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : stats.isError ? (
          <ErrorState message={stats.error.message} onRetry={() => stats.refetch()} />
        ) : (
          <StatsView stats={stats.data} />
        )}

        {!version && !choosing && reqs.length > 0 && <Checklist id="approve-checklist" items={reqs} />}
        {!version && stats.data && <SmallDatasetChoice projectId={project.id} stats={stats.data} />}

        {version && (
          <Callout tone="success" role="status">
            Approved v{version.version}: {version.train_count} train, {version.eval_count} eval. Next, set up training.
          </Callout>
        )}

        {approve.error && (
          <Callout tone="destructive" role="alert">
            {approve.error.message}
          </Callout>
        )}

        <div className="flex flex-col-reverse gap-4 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to={`/projects/${project.id}/dataset`}>
                <Table2 aria-hidden /> Open review table
              </Link>
            </Button>
            {nativeExport ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" disabled={exportDataset.isPending}>
                    <Download aria-hidden /> {exportDataset.isPending ? 'Preparing…' : 'Export JSONL'} <ChevronDown aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem onSelect={() => onExport('training')}>As trained (chat messages)</DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => onExport('native')}>{nativeExport}</DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <Button variant="outline" size="sm" disabled={exportDataset.isPending} onClick={() => onExport()}>
                <Download aria-hidden /> {exportDataset.isPending ? 'Preparing…' : 'Export JSONL'}
              </Button>
            )}
            {!choosing && stats.data?.more && (
              <Button
                variant="outline"
                size="sm"
                disabled={more.isPending}
                title={`Up to ${stats.data.more.pairs_to_generate} new pairs toward your target of ${stats.data.more.target_pairs}`}
                onClick={() =>
                  more.mutate(undefined, {
                    onSuccess: () => toast.success('Generating more pairs'),
                    onError: (err) => toast.error(err.message),
                  })
                }
              >
                <ListPlus aria-hidden /> {more.isPending ? 'Starting…' : 'Generate more pairs'}
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => setConfirmRestyle(true)}>
              <Wand2 aria-hidden /> Change style &amp; regenerate
            </Button>
          </div>
          {choosing ? null : version ? (
            <Button size="lg" onClick={() => setSetupOpen(true)}>
              <Rocket aria-hidden /> Set up training
            </Button>
          ) : (
            <Button
              size="lg"
              disabled={approve.isPending || blocked}
              aria-describedby={blocked ? 'approve-checklist' : undefined}
              onClick={() => approve.mutate({}, { onSuccess: () => toast.success('Dataset approved') })}
            >
              {approve.isPending ? 'Approving…' : 'Approve & continue'}
            </Button>
          )}
        </div>
      </CardContent>

      {version && <TrainSetupDialog projectId={project.id} open={setupOpen} onOpenChange={setSetupOpen} />}

      <AlertDialog open={confirmRestyle} onOpenChange={setConfirmRestyle}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Change style and regenerate?</AlertDialogTitle>
            <AlertDialogDescription>
              This discards the generated pairs and takes you back to the style step.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep dataset</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              disabled={restyle.isPending}
              onClick={(e) => {
                e.preventDefault()
                restyle.mutate(undefined, {
                  onSuccess: () => setConfirmRestyle(false),
                  onError: (err) => toast.error(err.message),
                })
              }}
            >
              {restyle.isPending ? 'Working…' : 'Discard and change style'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}
