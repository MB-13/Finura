import { useQuery } from '@tanstack/react-query'

import { qk } from '@/lib/query-keys'
import type { StoredNotice } from '@/lib/sse'

/** Latest warning notice pushed over SSE (cache-only; nothing is fetched). */
export function useLatestNotice(projectId: string): StoredNotice | undefined {
  const { data } = useQuery<StoredNotice | null>({
    queryKey: qk.notice(projectId),
    queryFn: () => null,
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  })
  return data ?? undefined
}
