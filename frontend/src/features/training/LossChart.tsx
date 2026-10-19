import { TrendingDown } from 'lucide-react'
import { useEffect, useId, useRef, useState, type PointerEvent } from 'react'

import type { Metric } from '@/features/training/api'

const DEFAULT_W = 640
const H = 232
const PAD = { top: 16, right: 16, bottom: 32, left: 46 }
const Y_TICKS = 4

type Point = { step: number; loss: number }

function usable(points: Metric[]): Point[] {
  return points.flatMap((p) => (p.loss !== null && Number.isFinite(p.loss) ? [{ step: p.step, loss: p.loss }] : []))
}

/** Track the rendered width so axis labels keep a readable size on phones (falls back to a fixed width without ResizeObserver). */
function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(DEFAULT_W)
  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry?.contentRect.width ?? 0)
      if (w > 0) setWidth(w)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])
  return { ref, width }
}

const compact = (n: number) => (n >= 10_000 ? `${Math.round(n / 1000)}k` : n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k` : String(Math.round(n)))

/** Accessible inline-SVG line chart of training loss (no chart library, so no extra bundle). Hover or touch shows exact values. */
export function LossChart({ points, maxSteps }: { points: Metric[]; maxSteps?: number }) {
  const data = usable(points)
  const { ref, width: W } = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const gradId = useId()

  if (data.length === 0) {
    return (
      <div role="status" className="flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-10 text-center">
        <span className="flex size-10 items-center justify-center rounded-full bg-muted text-muted-foreground">
          <TrendingDown className="size-5" aria-hidden />
        </span>
        <p className="max-w-xs text-caption text-muted-foreground">The loss curve appears once training reports its first steps.</p>
      </div>
    )
  }

  const minLoss = Math.min(...data.map((d) => d.loss))
  const maxLoss = Math.max(...data.map((d) => d.loss))
  const span = maxLoss - minLoss || 1
  const lo = minLoss - span * 0.06
  const hi = maxLoss + span * 0.06
  const maxStep = Math.max(maxSteps ?? 0, ...data.map((d) => d.step), 1)
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const x = (step: number) => PAD.left + (step / maxStep) * plotW
  const y = (loss: number) => PAD.top + (1 - (loss - lo) / (hi - lo)) * plotH
  const line = data.map((d) => `${x(d.step).toFixed(1)},${y(d.loss).toFixed(1)}`).join(' ')
  const first = data[0]!
  const last = data[data.length - 1]!
  const area = `${x(first.step).toFixed(1)},${PAD.top + plotH} ${line} ${x(last.step).toFixed(1)},${PAD.top + plotH}`
  const yTicks = Array.from({ length: Y_TICKS }, (_, i) => lo + ((hi - lo) * i) / (Y_TICKS - 1))
  const xTicks = [0, 0.25, 0.5, 0.75, 1].map((t) => Math.round(t * maxStep))
  const label = `Training loss over ${data.length} ${data.length === 1 ? 'point' : 'points'}: latest ${last.loss.toFixed(3)} at step ${last.step}, lowest ${minLoss.toFixed(3)}.`
  const active = hover !== null ? data[hover]! : null

  function onMove(e: PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    let best = 0
    let dist = Infinity
    data.forEach((d, i) => {
      const dx = Math.abs(x(d.step) - px)
      if (dx < dist) {
        dist = dx
        best = i
      }
    })
    setHover(best)
  }

  return (
    <figure className="flex flex-col gap-2">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <figcaption className="text-caption text-muted-foreground">Loss going down means the model is learning.</figcaption>
        <span className="text-metric text-xs text-muted-foreground">
          Latest: {last.loss.toFixed(3)} at step {last.step}
        </span>
      </div>
      <div ref={ref} className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          width={W}
          height={H}
          role="img"
          aria-label={label}
          className="block h-auto w-full touch-pan-y"
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
        >
          <title>{label}</title>
          <defs>
            <linearGradient id={gradId} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" className="[stop-color:var(--chart-1)]" stopOpacity={0.28} />
              <stop offset="100%" className="[stop-color:var(--chart-1)]" stopOpacity={0} />
            </linearGradient>
          </defs>
          {yTicks.map((v) => (
            <g key={v}>
              <line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} className="stroke-border" strokeDasharray="2 4" opacity={0.7} />
              <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" fontSize="10" className="fill-muted-foreground font-mono tabular-nums">
                {v.toFixed(2)}
              </text>
            </g>
          ))}
          <line x1={PAD.left} x2={W - PAD.right} y1={PAD.top + plotH} y2={PAD.top + plotH} className="stroke-border" />
          {xTicks.map((s, i) => (
            <text
              key={s}
              x={x(s)}
              y={H - 10}
              textAnchor={i === 0 ? 'start' : i === xTicks.length - 1 ? 'end' : 'middle'}
              fontSize="10"
              className="fill-muted-foreground font-mono tabular-nums"
            >
              {i === 0 ? 'step 0' : compact(s)}
            </text>
          ))}
          <polygon points={area} fill={`url(#${gradId})`} />
          <polyline
            data-testid="loss-line"
            points={line}
            fill="none"
            strokeWidth={1.75}
            strokeLinejoin="round"
            strokeLinecap="round"
            className="stroke-chart-1"
          />
          <circle cx={x(last.step)} cy={y(last.loss)} r={7} className="fill-chart-1" opacity={0.18} />
          <circle cx={x(last.step)} cy={y(last.loss)} r={3.5} className="fill-chart-1 stroke-card" strokeWidth={1.5} />
          {active && (
            <g aria-hidden>
              <line x1={x(active.step)} x2={x(active.step)} y1={PAD.top} y2={PAD.top + plotH} className="stroke-muted-foreground/50" />
              <circle cx={x(active.step)} cy={y(active.loss)} r={4.5} className="fill-chart-1 stroke-card" strokeWidth={2} />
            </g>
          )}
        </svg>
        {active && (
          <div
            aria-hidden
            className="pointer-events-none absolute top-1 rounded-md border bg-popover px-2 py-1 text-caption whitespace-nowrap text-popover-foreground shadow-md font-mono text-xs tabular-nums"
            style={{
              left: Math.min(Math.max(x(active.step), 70), W - 70),
              transform: 'translateX(-50%)',
            }}
          >
            Step {active.step.toLocaleString()} · loss <span className="font-semibold">{active.loss.toFixed(3)}</span>
          </div>
        )}
      </div>
    </figure>
  )
}
