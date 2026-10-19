import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

import { AppFrame } from '@/components/AppFrame'
import { ChatVignette, Decor, DropzoneVignette, ReviewVignette, StyleVignette, TrainVignette } from '@/features/marketing/vignettes'
import { cn } from '@/lib/utils'

const steps: {
  title: string
  text: string
  frame: string
  visual: ReactNode
}[] = [
  {
    title: 'Upload documents',
    text: 'PDFs and docs you want your model to learn from. DocTune reads them and splits them into sections.',
    frame: 'Upload',
    visual: <DropzoneVignette />,
  },
  {
    title: 'Describe the style',
    text: 'Tone, length and format, plus a few example answers. This is what the model learns to copy.',
    frame: 'Style',
    visual: <StyleVignette />,
  },
  {
    title: 'Review the dataset',
    text: 'DocTune writes training examples and scores them. You edit, delete or add, then approve.',
    frame: 'Dataset',
    visual: <ReviewVignette />,
  },
  {
    title: 'Train for free',
    text: 'Run on your own free Kaggle or Google Colab GPU. Pauses are normal and progress is saved.',
    frame: 'Train',
    visual: <TrainVignette />,
  },
  {
    title: 'Chat and download',
    text: 'Try it in the playground with answers that cite your files, then take the model with you.',
    frame: 'Playground',
    visual: <ChatVignette />,
  },
]

const AUTO_MS = 6500

/** Expanding step list with a matching product vignette: visual on the right at lg+, inline under the step on mobile. */
export function StepShowcase() {
  const [active, setActive] = useState(0)
  const [paused, setPaused] = useState(false)
  const [userPicked, setUserPicked] = useState(false)
  const [canAuto, setCanAuto] = useState(false)
  const base = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  // Auto-advance only on large screens and never with reduced motion; stops for good once the user picks a step.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const wide = window.matchMedia('(min-width: 1024px)')
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setCanAuto(wide.matches && !calm.matches)
    update()
    wide.addEventListener('change', update)
    calm.addEventListener('change', update)
    return () => {
      wide.removeEventListener('change', update)
      calm.removeEventListener('change', update)
    }
  }, [])

  useEffect(() => {
    if (!canAuto || paused || userPicked) return
    const t = window.setTimeout(() => setActive((a) => (a + 1) % steps.length), AUTO_MS)
    return () => window.clearTimeout(t)
  }, [active, canAuto, paused, userPicked])

  const pick = useCallback((i: number) => {
    setActive(i)
    setUserPicked(true)
  }, [])

  function onKey(e: KeyboardEvent, i: number) {
    const move = e.key === 'ArrowDown' ? 1 : e.key === 'ArrowUp' ? -1 : 0
    if (!move) return
    e.preventDefault()
    const n = (i + move + steps.length) % steps.length
    refs.current[n]?.focus()
  }

  return (
    <div
      className="grid gap-8 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] lg:gap-12"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      <ol className="flex flex-col">
        {steps.map((s, i) => {
          const open = i === active
          return (
            <li key={s.title} className="border-t first:border-t-0 lg:first:border-t-0">
              <h3>
                <button
                  ref={(el) => {
                    refs.current[i] = el
                  }}
                  type="button"
                  aria-expanded={open}
                  aria-controls={`${base}-p${i}`}
                  onClick={() => pick(i)}
                  onKeyDown={(e) => onKey(e, i)}
                  className={cn(
                    'group flex w-full items-center gap-4 rounded-md py-4 text-left transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none',
                    open ? 'text-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  <span className={cn('text-metric text-xs', open ? 'text-primary' : 'text-muted-foreground')}>{String(i + 1).padStart(2, '0')}</span>
                  <span className="text-section-title">{s.title}</span>
                </button>
              </h3>
              <div id={`${base}-p${i}`} hidden={!open} className="flex flex-col gap-5 pb-5 pl-9">
                <p className="max-w-md text-body text-muted-foreground">{s.text}</p>
                <Decor className="lg:hidden">
                  <AppFrame title={s.frame} className="shadow-md" bodyClassName="p-4">
                    {s.visual}
                  </AppFrame>
                </Decor>
              </div>
            </li>
          )
        })}
      </ol>
      <Decor className="hidden lg:block">
        <AppFrame title={steps[active]!.frame} bodyClassName="min-h-[26rem] p-6">
          <div key={active} className="animate-in fade-in duration-300 motion-reduce:animate-none">
            {steps[active]!.visual}
          </div>
        </AppFrame>
      </Decor>
    </div>
  )
}
