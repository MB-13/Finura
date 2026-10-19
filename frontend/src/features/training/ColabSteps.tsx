import { ExternalLink } from 'lucide-react'
import type { ReactNode } from 'react'

import { Button } from '@/components/ui/button'
import { StepItem } from '@/components/StepRail'

/** The four things to do in Colab, in order. Step 1 is the token block rendered by the caller. */
export function ColabSteps({ notebookUrl, tokenSlot }: { notebookUrl: string | null; tokenSlot: ReactNode }) {
  return (
    <ol className="flex flex-col" aria-label="Steps to run the notebook">
      <Step n={1} title="Copy your job token">
        {tokenSlot}
      </Step>
      <Step n={2} title="Open the notebook in Colab">
        {notebookUrl ? (
          <Button asChild className="self-start">
            <a href={notebookUrl} target="_blank" rel="noopener noreferrer">
              <ExternalLink aria-hidden /> Open in Colab
            </a>
          </Button>
        ) : (
          <p className="text-sm text-muted-foreground">The notebook link is not available right now. Refresh the page to try again.</p>
        )}
        <p className="text-caption text-muted-foreground">Sign in with your own Google account. The notebook runs in your account, not ours.</p>
      </Step>
      <Step n={3} title="Pick a free GPU">
        <p className="text-sm text-muted-foreground">
          In Colab choose <strong className="font-medium text-foreground">Runtime → Change runtime type → T4 GPU</strong>.
        </p>
      </Step>
      <Step n={4} title="Run all cells and keep the tab open" last>
        <p className="text-sm text-muted-foreground">
          Choose <strong className="font-medium text-foreground">Runtime → Run all</strong>, paste the token when asked, and leave the tab open until training is done.
        </p>
      </Step>
    </ol>
  )
}

function Step({ n, title, last = false, children }: { n: number; title: string; last?: boolean; children: ReactNode }) {
  return (
    <StepItem state="todo" n={n} last={last}>
      <div className="flex flex-col gap-2.5">
        <h3 className="text-card-title">
          <span className="sr-only">Step {n}: </span>
          {title}
        </h3>
        {children}
      </div>
    </StepItem>
  )
}
