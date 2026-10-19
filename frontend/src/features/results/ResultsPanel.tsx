import { Cloud, FlaskConical, PartyPopper, RotateCw } from 'lucide-react'
import { Link } from 'react-router'

import { Callout } from '@/components/Callout'
import { ErrorState } from '@/components/ErrorState'
import { Section } from '@/components/Section'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { DownloadList } from '@/features/results/DownloadList'
import { EvalComparison, SamplesList } from '@/features/results/EvalComparison'
import { metricNumber } from '@/features/results/eval-utils'
import { OllamaInstructions } from '@/features/results/OllamaInstructions'
import type { Project } from '@/features/projects/api'
import { useEvaluation } from '@/features/training/api'
import { PanelHeader } from '@/features/training/PanelHeader'

/** Results sections sit under the panel's h2, so they are h3s separated by rules. */
const SECTION_PROPS = { as: 'h3', className: 'border-t pt-6' } as const

export function ResultsPanel({ project }: { project: Project }) {
  const job = project.active_job
  const evalQuery = useEvaluation(project.id)
  const evaluation = evalQuery.data !== undefined ? evalQuery.data : project.evaluation
  const rougeBase = metricNumber(job?.metrics, 'rouge_l_base')
  const rougeTuned = metricNumber(job?.metrics, 'rouge_l_tuned')
  const driveRaw = job?.exports?.['drive_path']
  const hfRaw = job?.exports?.['hf_repo']
  const drivePath = typeof driveRaw === 'string' ? driveRaw : null
  const hfRepo = typeof hfRaw === 'string' ? hfRaw : null
  const isLlama = job?.is_llama === true
  const isKaggle = job?.backend === 'kaggle'
  const license = job?.base_model_license ?? project.base_model_license

  return (
    <Card>
      <PanelHeader
        icon={PartyPopper}
        tone="success"
        large
        eyebrow="Training complete"
        title="Your model is ready"
        description="See how it compares with the original, download your files, or chat with it."
        actions={
          <>
            <Button asChild size="lg">
              <Link to={`/projects/${project.id}/playground`}>
                <FlaskConical aria-hidden /> Open playground
              </Link>
            </Button>
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span tabIndex={0} className="rounded-md">
                    <Button variant="outline" size="lg" disabled aria-label="Train again (coming soon)">
                      <RotateCw aria-hidden /> Train again
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>Coming soon</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </>
        }
      />
      <CardContent className="flex flex-col gap-6">
        <Callout tone="info" title="Style, not facts">
          Fine-tuning teaches your model how to answer. For facts from your documents, chat with it in the playground, which looks them up with search.
        </Callout>
        <Section {...SECTION_PROPS} title="Original vs tuned">
          {evalQuery.isError && evaluation === undefined ? (
            <ErrorState title="Couldn't load the evaluation" message={evalQuery.error.message} onRetry={() => evalQuery.refetch()} />
          ) : (
            <EvalComparison evaluation={evaluation} />
          )}
          {rougeBase !== null && rougeTuned !== null && (
            <p className="text-caption text-muted-foreground">
              ROUGE-L (word overlap with the reference answers): original {rougeBase.toFixed(3)} → tuned {rougeTuned.toFixed(3)}.
            </p>
          )}
        </Section>

        {evaluation?.state === 'done' && (
          <Section {...SECTION_PROPS} title="Side-by-side answers" description="Held-out questions your model never saw while training.">
            <SamplesList evaluation={evaluation} />
          </Section>
        )}

        <Section {...SECTION_PROPS} title="Downloads">
          <DownloadList projectId={project.id} />
          {(drivePath || hfRepo) && (
            <p className="flex items-start gap-2 text-caption text-muted-foreground">
              <Cloud className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                The full GGUF and merged model went to
                {drivePath && (
                  <>
                    {' '}
                    your Google Drive at <code className="font-mono break-all text-foreground">{drivePath}</code>
                  </>
                )}
                {drivePath && hfRepo && ' and'}
                {hfRepo && (
                  <>
                    {' '}
                    your Hugging Face repo <code className="font-mono break-all text-foreground">{hfRepo}</code>
                  </>
                )}
                .
              </span>
            </p>
          )}
          {!drivePath && !hfRepo && !isKaggle && (
            <p className="text-caption text-muted-foreground">
              The full GGUF and merged weights are saved to your own Google Drive from the notebook, if you mounted Drive.
            </p>
          )}
          <p className="text-caption text-muted-foreground">Files are kept for 14 days after training ends.</p>
        </Section>

        <Section {...SECTION_PROPS} title="Run it with Ollama">
          <OllamaInstructions kaggle={isKaggle} baseModel={job?.base_model_id} />
        </Section>

        <Section {...SECTION_PROPS} title="License">
          <p className="text-sm text-muted-foreground">
            Your model is based on <strong className="font-medium text-foreground">{job?.base_model_id ?? project.base_model_id ?? 'the base model'}</strong>
            {license ? ` (${license})` : ''}. Follow that license when you share or use it.
          </p>
          {isLlama && (
            <Callout tone="info" title="Built with Llama.">
              The Llama license asks you to show this notice whenever you share the model.
            </Callout>
          )}
        </Section>
      </CardContent>
    </Card>
  )
}
