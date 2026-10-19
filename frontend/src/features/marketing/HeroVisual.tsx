import { AppFrame } from '@/components/AppFrame'
import { StatRow } from '@/components/StatRow'
import { StatusBadge } from '@/components/StatusBadge'
import { ProjectStepper } from '@/features/projects/ProjectStepper'
import { REVIEW_PAIRS } from '@/features/marketing/vignette-data'
import { Decor, PairLine } from '@/features/marketing/vignettes'

/** Decorative product window: real stepper + review composition with fixture data. Inert and hidden from assistive tech. */
export function HeroVisual() {
  return (
    <Decor className="mx-auto w-full max-w-5xl">
      <AppFrame title="doctune.app / projects / support-assistant" fade className="h-[26rem] sm:h-[30rem]">
        <div className="grid lg:grid-cols-[14rem_1fr]">
          <div className="hidden border-r bg-muted/20 p-5 lg:block">
            <ProjectStepper status="in_review" className="lg:static" />
          </div>
          <div className="flex min-w-0 flex-col gap-5 p-4 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="truncate text-card-title">Support assistant</div>
                <div className="text-caption text-muted-foreground">3 documents · friendly, short answers</div>
              </div>
              <StatusBadge status="in_review" />
            </div>
            <StatRow
              items={[
                { label: 'Pairs', value: '940' },
                { label: 'Approved', value: '846' },
                { label: 'To review', value: '94' },
                { label: 'Avg score', value: '4.3' },
              ]}
            />
            <div className="flex flex-col divide-y border-t pt-4">
              {REVIEW_PAIRS.map((p) => (
                <PairLine key={p.q} {...p} />
              ))}
            </div>
          </div>
        </div>
      </AppFrame>
    </Decor>
  )
}
