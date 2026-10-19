import type { ReactNode } from 'react'

import { Decor, DownloadTile, KaggleTile, PausedTile, PresetTile, ScoresTile, SourcesTile } from '@/features/marketing/vignettes'
import { cn } from '@/lib/utils'

type Tile = {
  title: string
  text: string
  visual: ReactNode
  className?: string
  wide?: boolean
}

const tiles: Tile[] = [
  {
    title: 'Review before you train',
    text: 'DocTune shows a small preview first and scores every example. Edit, delete or add; nothing trains until you approve.',
    visual: <ScoresTile />,
    className: 'sm:col-span-2',
  },
  {
    title: 'Pauses are normal',
    text: 'Free GPUs stop sometimes. Progress is saved, and you pick up where you left off.',
    visual: <PausedTile />,
  },
  {
    title: 'Free GPU, your account',
    text: 'Training runs on your own Kaggle or Google Colab account. DocTune never asks for your Google password.',
    visual: <KaggleTile />,
  },
  {
    title: 'Plain-language setup',
    text: 'Pick a preset instead of tuning settings. Advanced options stay tucked away.',
    visual: <PresetTile />,
  },
  {
    title: 'Chat with your documents',
    text: 'The playground searches your files, so answers can cite the source.',
    visual: <SourcesTile />,
  },
  {
    title: 'Take it with you',
    text: 'Download the adapter, a merged model or a GGUF file you can run on your own computer with Ollama.',
    visual: <DownloadTile />,
    className: 'sm:col-span-2 lg:col-span-3 lg:grid lg:grid-cols-2 lg:items-center lg:gap-10',
    wide: true,
  },
]

/** Mixed-size bento: each tile pairs a short explanation with a miniature of the real screen. */
export function FeatureBento() {
  return (
    <ul className="grid gap-px overflow-hidden rounded-2xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
      {tiles.map((t) => (
        <li key={t.title} className={cn('flex flex-col gap-6 bg-background p-6 sm:p-7', t.className)}>
          <div className="flex max-w-md flex-col gap-1.5">
            <h3 className="text-section-title">{t.title}</h3>
            <p className="text-body text-muted-foreground">{t.text}</p>
          </div>
          <Decor className={cn('mt-auto', t.wide && 'lg:mt-0')}>{t.visual}</Decor>
        </li>
      ))}
    </ul>
  )
}
