import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type Me = components['schemas']['MeOut']
export type MePatch = components['schemas']['MePatch']

export function useMe() {
  return useQuery({
    queryKey: qk.me(),
    queryFn: async () => unwrap(await api.GET('/me')),
  })
}

export function useUpdateMe() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: MePatch) => unwrap(await api.PATCH('/me', { body })),
    onSuccess: (me) => queryClient.setQueryData(qk.me(), me),
  })
}

export function useDeleteAccount() {
  return useMutation({
    mutationFn: async () => {
      const result = await api.DELETE('/me')
      unwrap(result)
    },
  })
}
