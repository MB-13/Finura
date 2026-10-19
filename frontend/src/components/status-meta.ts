import type { ProjectStatus } from '@/features/projects/api'

export type Tone = 'neutral' | 'running' | 'paused' | 'ready' | 'failed'

export const statusMeta: Record<ProjectStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Draft', tone: 'neutral' },
  uploaded: { label: 'Documents uploaded', tone: 'neutral' },
  parsing: { label: 'Reading documents', tone: 'running' },
  awaiting_style: { label: 'Needs style', tone: 'neutral' },
  previewing: { label: 'Generating preview', tone: 'running' },
  generating: { label: 'Generating dataset', tone: 'running' },
  in_review: { label: 'In review', tone: 'neutral' },
  awaiting_run: { label: 'Ready to train', tone: 'neutral' },
  training: { label: 'Training', tone: 'running' },
  paused: { label: 'Paused', tone: 'paused' },
  evaluating: { label: 'Evaluating', tone: 'running' },
  ready: { label: 'Ready', tone: 'ready' },
  failed: { label: 'Failed', tone: 'failed' },
}
