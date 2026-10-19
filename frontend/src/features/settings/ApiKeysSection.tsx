import { toast } from 'sonner'

import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { usePatchKey, useKeys, useProviders, type ProviderKey } from '@/features/settings/api'
import { ProviderKeyCard } from '@/features/settings/ProviderKeyCard'

export function ApiKeysSection() {
  const providers = useProviders()
  const keys = useKeys()
  const patch = usePatchKey()

  if (providers.isPending || keys.isPending) {
    return (
      <div aria-busy="true" aria-label="Loading API keys" className="flex flex-col gap-3">
        <Skeleton className="h-56 rounded-lg" />
        <Skeleton className="h-56 rounded-lg" />
      </div>
    )
  }
  if (providers.isError) return <ErrorState message={providers.error.message} onRetry={() => providers.refetch()} />
  if (keys.isError) return <ErrorState message={keys.error.message} onRetry={() => keys.refetch()} />

  // lower number = tried first
  const connected: ProviderKey[] = [...keys.data].sort((a, b) => a.priority - b.priority)
  const byProvider = new Map(keys.data.map((k) => [k.provider, k]))

  function move(provider: ProviderKey['provider'], direction: -1 | 1) {
    const from = connected.findIndex((k) => k.provider === provider)
    const to = from + direction
    if (from < 0 || to < 0 || to >= connected.length) return
    const order = [...connected]
    const [item] = order.splice(from, 1)
    order.splice(to, 0, item!)
    order.forEach((k, i) => {
      if (k.priority !== i) {
        patch.mutate({ provider: k.provider, body: { priority: i } }, { onError: (err) => toast.error(err.message) })
      }
    })
  }

  return (
    <div className="flex flex-col divide-y">
      {providers.data.map((info) => (
        <ProviderKeyCard
          key={info.provider}
          info={info}
          keyInfo={byProvider.get(info.provider)}
          index={connected.findIndex((k) => k.provider === info.provider)}
          total={connected.length}
          onMove={(d) => move(info.provider, d)}
        />
      ))}
    </div>
  )
}
