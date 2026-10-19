import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap } from '@/lib/api/client'
import type { components } from '@/lib/api/schema'
import { qk } from '@/lib/query-keys'

export type Project = components['schemas']['ProjectOut']
export type ProjectSummary = components['schemas']['ProjectSummary']
export type ProjectStatus = components['schemas']['ProjectStatus']
export type ProjectPatch = components['schemas']['ProjectPatch']

export function useProjects() {
  return useInfiniteQuery({
    queryKey: qk.projects(),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) =>
      unwrap(await api.GET('/projects', { params: { query: { limit: 50, cursor: pageParam } } })),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
}

export function useProject(id: string) {
  return useQuery({
    queryKey: qk.project(id),
    queryFn: async () => unwrap(await api.GET('/projects/{project_id}', { params: { path: { project_id: id } } })),
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) => unwrap(await api.POST('/projects', { body: { name } })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(project.id), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

export function useRenameProject(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(await api.PATCH('/projects/{project_id}', { params: { path: { project_id: id } }, body: { name } })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(id), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (id: string) => {
      const result = await api.DELETE('/projects/{project_id}', { params: { path: { project_id: id } } })
      unwrap(result)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.projects() }),
  })
}

export function useProcessProject(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/projects/{project_id}/process', { params: { path: { project_id: id } } })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(id), project)
      void queryClient.invalidateQueries({ queryKey: qk.documents(id) })
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}

export function useRetryProject(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => unwrap(await api.POST('/projects/{project_id}/retry', { params: { path: { project_id: id } } })),
    onSuccess: (project) => {
      queryClient.setQueryData(qk.project(id), project)
      void queryClient.invalidateQueries({ queryKey: qk.projects() })
    },
  })
}
