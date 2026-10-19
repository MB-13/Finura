import { useQuery } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type Meta = components['schemas']['MetaOut']

export function useMeta() {
  return useQuery({
    queryKey: qk.meta(),
    queryFn: async () => unwrap(await api.GET('/meta')),
    staleTime: 10 * 60_000,
  })
}
