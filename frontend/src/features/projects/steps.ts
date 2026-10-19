import type { StepState } from '@/components/StepRail'
import type { ProjectStatus } from '@/features/projects/api'

export const STEPS = ['Upload', 'Style', 'Preview', 'Dataset', 'Train', 'Results'] as const

/**
 * Index of the current step per status (STEPS.length = everything done).
 * `null` means the status is not tied to a step (failed).
 */
export const stepIndexByStatus: Record<ProjectStatus, number | null> = {
  draft: 0,
  uploaded: 0,
  parsing: 0,
  awaiting_style: 1,
  previewing: 2,
  generating: 3,
  in_review: 3,
  awaiting_run: 4,
  training: 4,
  paused: 4,
  evaluating: 4,
  ready: 5,
  failed: null,
}

/** What each step is about, shown under its label in the stepper rail. */
export const STEP_HINTS: Record<(typeof STEPS)[number], string> = {
  Upload: 'Add your documents',
  Style: 'Describe the answers',
  Preview: 'Check a few samples',
  Dataset: 'Generate and review',
  Train: 'Fine-tune on a free GPU',
  Results: 'Download and try it',
}

export function stepStates(status: ProjectStatus): StepState[] {
  const idx = stepIndexByStatus[status]
  return STEPS.map((_, i) => (idx === null ? 'todo' : i < idx ? 'done' : i === idx ? 'active' : 'todo'))
}

/** 0-100 for progress bars. */
export function stepPercent(status: ProjectStatus): number {
  const idx = stepIndexByStatus[status]
  return idx === null ? 0 : Math.round((idx / STEPS.length) * 100)
}

/** One plain-language line per status: what is happening or what to do next. Used by cards and the workspace header. */
export const statusHint: Record<ProjectStatus, string> = {
  draft: 'Add the documents your model should learn from.',
  uploaded: 'Documents added. Process them to continue.',
  parsing: 'Reading your documents. This takes a few minutes.',
  awaiting_style: 'Describe how your model should answer.',
  previewing: 'Writing a few sample pairs to check your style.',
  generating: 'Writing your training dataset from your documents.',
  in_review: 'Review the dataset, then approve it to train.',
  awaiting_run: 'Training is set up and about to start.',
  training: 'Your model is training.',
  paused: 'Progress is saved. Resume when you are ready.',
  evaluating: 'Checking how well your model learned.',
  ready: 'Your model is ready to download and try.',
  failed: 'Something went wrong. You can try again.',
}

/** Short label of the step a status belongs to (null for failed). */
export function stepLabel(status: ProjectStatus): string | null {
  const idx = stepIndexByStatus[status]
  return idx === null ? null : (STEPS[idx] ?? null)
}
