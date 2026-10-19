import { SlidersHorizontal } from 'lucide-react'
import { Popover } from 'radix-ui'

import { Label } from '@/components/ui/label'

type Props = {
  temperature: number
  onTemperature: (v: number) => void
  maxTokens: number
  onMaxTokens: (v: number) => void
}

/** Temperature and answer length live in a popover on the composer toolbar, out of the way of the conversation. */
export function ChatSettings({ temperature, onTemperature, maxTokens, onMaxTokens }: Props) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          aria-label="Chat settings"
          className="flex h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring/50 data-[state=open]:bg-accent data-[state=open]:text-foreground"
        >
          <SlidersHorizontal className="size-3.5" aria-hidden />
          <span className="hidden sm:inline">Settings</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="start"
          sideOffset={8}
          collisionPadding={12}
          aria-label="Chat settings"
          className="z-50 flex w-72 max-w-[calc(100vw-1.5rem)] flex-col gap-4 rounded-xl border bg-popover p-4 text-popover-foreground shadow-lg outline-none"
        >
          <div className="flex flex-col gap-1.5">
            <div className="flex items-baseline justify-between gap-2">
              <Label htmlFor="temperature">Temperature</Label>
              <span className="font-mono text-[0.75rem] text-muted-foreground tabular-nums">{temperature.toFixed(1)}</span>
            </div>
            <input
              id="temperature"
              type="range"
              min={0}
              max={1.5}
              step={0.1}
              value={temperature}
              onChange={(e) => onTemperature(Number(e.target.value))}
              className="h-5 w-full accent-primary"
            />
            <span className="text-caption text-muted-foreground">Lower is more focused, higher is more creative.</span>
          </div>
          <div className="flex flex-col gap-1.5 border-t pt-4">
            <div className="flex items-baseline justify-between gap-2">
              <Label htmlFor="max-tokens">Max answer length</Label>
              <span className="font-mono text-[0.75rem] text-muted-foreground tabular-nums">{maxTokens}</span>
            </div>
            <input
              id="max-tokens"
              type="range"
              min={16}
              max={512}
              step={16}
              value={maxTokens}
              onChange={(e) => onMaxTokens(Number(e.target.value))}
              className="h-5 w-full accent-primary"
            />
            <span className="text-caption text-muted-foreground">Longer answers take longer on a shared CPU.</span>
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
