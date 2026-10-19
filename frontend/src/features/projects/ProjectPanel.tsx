import { ReviewPanel } from '@/features/dataset/ReviewPanel'
import { ProcessingPanel } from '@/features/documents/ProcessingPanel'
import { UploadPanel } from '@/features/documents/UploadPanel'
import type { Project } from '@/features/projects/api'
import { FailedPanel } from '@/features/projects/panels/FailedPanel'
import { PausedPanel } from '@/features/projects/panels/PausedPanel'
import { GenerationPanel } from '@/features/generation/GenerationPanel'
import { ResultsPanel } from '@/features/results/ResultsPanel'
import { EvaluatingPanel } from '@/features/training/EvaluatingPanel'
import { RunNotebookPanel } from '@/features/training/RunNotebookPanel'
import { TrainingPanel } from '@/features/training/TrainingPanel'
import { AwaitingStylePanel } from '@/features/style/AwaitingStylePanel'
import { PreviewingPanel } from '@/features/style/PreviewingPanel'

function assertNever(value: never): never {
  throw new Error(`Unhandled project status: ${String(value)}`)
}

/** The panel shown for a project is decided only by `project.status`. */
export function ProjectPanel({ project }: { project: Project }) {
  const status = project.status
  switch (status) {
    case 'draft':
    case 'uploaded':
      return <UploadPanel project={project} />
    case 'parsing':
      return <ProcessingPanel project={project} />
    case 'awaiting_style':
      return <AwaitingStylePanel project={project} />
    case 'previewing':
      return <PreviewingPanel project={project} />
    case 'generating':
      return <GenerationPanel project={project} />
    case 'in_review':
      return <ReviewPanel project={project} />
    case 'awaiting_run':
      return <RunNotebookPanel project={project} />
    case 'training':
      return <TrainingPanel project={project} />
    case 'paused':
      return <PausedPanel project={project} />
    case 'evaluating':
      return <EvaluatingPanel project={project} />
    case 'ready':
      return <ResultsPanel project={project} />
    case 'failed':
      return <FailedPanel project={project} />
    default:
      return assertNever(status)
  }
}
