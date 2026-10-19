import { CheckCircle2, XCircle } from 'lucide-react'

import { Callout } from '@/components/Callout'
import { blockingMessage, FITS_COPY, MODE_LABEL, warningMessage } from '@/features/training/model-copy'
import type { ModelCheck } from '@/features/training/api'

export function ModelCheckResult({
  result,
  licenseAck,
  onLicenseAck,
}: {
  result: ModelCheck
  licenseAck: boolean
  onLicenseAck: (v: boolean) => void
}) {
  const blocked = result.blocking.length > 0
  return (
    <div className="flex flex-col gap-3" aria-live="polite">
      <div className="flex flex-col gap-1.5 border-b pb-3 text-sm">
        <div className="flex items-center gap-2 font-medium">
          {blocked ? (
            <XCircle className="size-4 shrink-0 text-destructive" aria-hidden />
          ) : (
            <CheckCircle2 className="size-4 shrink-0 text-success" aria-hidden />
          )}
          <span className="min-w-0 font-mono text-[0.8125rem] break-all">{result.hf_id}</span>
        </div>
        {!blocked && (
          <p className="pl-6 text-caption text-muted-foreground">
            {result.params_b != null && `${result.params_b} B parameters · `}
            {result.license ?? 'License unknown'} · {MODE_LABEL[result.train_mode]} · {FITS_COPY[result.fits_t4]}
          </p>
        )}
      </div>

      {result.blocking.length > 0 && (
        <Callout tone="destructive" role="alert">
          <ul className="flex flex-col gap-1">
            {result.blocking.map((code) => (
              <li key={code}>{blockingMessage(code)}</li>
            ))}
          </ul>
        </Callout>
      )}

      {result.warnings.length > 0 && (
        <Callout tone="warning">
          <ul className="flex flex-col gap-1">
            {result.warnings.map((code) => (
              <li key={code}>{warningMessage(code)}</li>
            ))}
          </ul>
        </Callout>
      )}

      {result.is_llama && (
        <Callout tone="info">
          This is a Llama model. Its license asks you to show <strong>Built with Llama</strong> whenever you share or publish the result.
        </Callout>
      )}

      {!blocked && !result.license_ok && (
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-warning/40 bg-warning-muted p-4 text-sm has-focus-visible:ring-[3px] has-focus-visible:ring-ring/50">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-primary"
            checked={licenseAck}
            onChange={(e) => onLicenseAck(e.target.checked)}
          />
          <span className="text-foreground/90">
            I have read this model&apos;s license{result.license ? ` (${result.license})` : ''} and I&apos;m allowed to use it this way.
          </span>
        </label>
      )}
    </div>
  )
}
