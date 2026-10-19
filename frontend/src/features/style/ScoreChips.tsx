import { formatScore } from '@/lib/format'

type Props = { correctness: number | null; style: number | null; reason?: string | null }

const dotFor = (score: number) => (score >= 4 ? 'bg-success' : score >= 3 ? 'bg-warning' : 'bg-destructive')

function Score({ label, score, ariaLabel }: { label: string; score: number; ariaLabel: string }) {
  return (
    <span aria-label={ariaLabel} className="inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span aria-hidden className={`size-1.5 rounded-full ${dotFor(score)}`} />
      <span className="text-muted-foreground">{label}</span>
      <span className="text-metric text-foreground">{formatScore(score)}/5</span>
    </span>
  )
}

/** Judge scores as a dot + label + mono number (the number is always shown, so colour is never the only signal). */
export function ScoreChips({ correctness, style, reason }: Props) {
  if (correctness === null && style === null) return <span className="text-caption text-muted-foreground">Not scored</span>
  return (
    <span className="inline-flex flex-col gap-0.5" title={reason ?? undefined}>
      {correctness !== null && <Score label="Accuracy" score={correctness} ariaLabel={`Accuracy score ${formatScore(correctness)}`} />}
      {style !== null && <Score label="Style" score={style} ariaLabel={`Style score ${formatScore(style)}`} />}
    </span>
  )
}
