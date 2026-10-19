import type { Metric } from '@/features/training/api'

const WINDOW = 12

/**
 * Seconds left, from the step rate over the most recent metric points.
 * Returns null until two points with distinct times exist.
 */
export function estimateEtaSeconds(points: Metric[], currentStep: number, maxSteps: number): number | null {
  if (maxSteps <= 0 || currentStep >= maxSteps) return null
  const recent = points.slice(-WINDOW)
  if (recent.length < 2) return null
  const first = recent[0]!
  const last = recent[recent.length - 1]!
  const dt = (new Date(last.at).getTime() - new Date(first.at).getTime()) / 1000
  const dSteps = last.step - first.step
  if (!(dt > 0) || dSteps <= 0) return null
  return Math.round((maxSteps - currentStep) / (dSteps / dt))
}

/** Whole-number percent of steps done (0-100). */
export function trainingPercent(current: number, max: number): number {
  return max > 0 ? Math.min(100, Math.floor((current / max) * 100)) : 0
}
