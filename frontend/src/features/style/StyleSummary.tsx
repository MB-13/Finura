import { useDatasetFormats, type StyleOut } from '@/features/style/api'

/** Read-only view of the saved style. */
export function StyleSummary({ style }: { style: StyleOut }) {
  const formats = useDatasetFormats()
  const datasetFormat = formats.data?.find((f) => f.key === style.dataset_format)?.name
  const facts: [string, string | number][] = [
    ...(datasetFormat ? [['Dataset', datasetFormat] as [string, string]] : []),
    ['Tone', style.tone],
    ['Length', style.length],
    ['Format', style.format],
    ['Language', style.language],
    ['Examples', style.examples.length],
  ]
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="whitespace-pre-wrap">{style.description}</p>
      <dl className="flex flex-wrap gap-2">
        {facts.map(([label, value]) => (
          <div key={label} className="flex gap-1 rounded-full bg-muted px-2.5 py-1 text-caption">
            <dt className="text-muted-foreground">{label}:</dt>
            <dd className="font-medium text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
