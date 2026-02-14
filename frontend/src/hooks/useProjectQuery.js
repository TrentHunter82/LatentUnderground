import { useQuery } from '@tanstack/react-query'
import {
  getProject,
  getProjects,
  getProjectsWithArchived,
  getProjectStats,
  getProjectHealth,
  getProjectQuota,
  getProjectGuardrails,
  getTemplates,
} from '../lib/api'

// Query key factories for consistent cache management
export const projectKeys = {
  all: ['projects'],
  lists: () => [...projectKeys.all, 'list'],
  list: (filters) => [...projectKeys.lists(), filters],
  details: () => [...projectKeys.all, 'detail'],
  detail: (id) => [...projectKeys.details(), id],
  stats: (id) => [...projectKeys.detail(id), 'stats'],
  health: (id) => [...projectKeys.detail(id), 'health'],
  quota: (id) => [...projectKeys.detail(id), 'quota'],
  guardrails: (id) => [...projectKeys.detail(id), 'guardrails'],
}

export function useProjects({ showArchived = false } = {}) {
  return useQuery({
    queryKey: projectKeys.list({ showArchived }),
    queryFn: () => showArchived ? getProjectsWithArchived(true) : getProjects(),
    staleTime: 10_000,
  })
}

export function useProject(projectId, options = {}) {
  return useQuery({
    queryKey: projectKeys.detail(projectId),
    queryFn: () => getProject(projectId),
    enabled: !!projectId,
    staleTime: 5_000,
    ...options,
  })
}

export function useProjectStats(projectId, options = {}) {
  return useQuery({
    queryKey: projectKeys.stats(projectId),
    queryFn: () => getProjectStats(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
    ...options,
  })
}

export function useProjectHealth(projectId, options = {}) {
  return useQuery({
    queryKey: projectKeys.health(projectId),
    queryFn: () => getProjectHealth(projectId),
    enabled: !!projectId,
    staleTime: 10_000,
    ...options,
  })
}

export function useProjectQuota(projectId, options = {}) {
  return useQuery({
    queryKey: projectKeys.quota(projectId),
    queryFn: () => getProjectQuota(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
    ...options,
  })
}

export function useProjectGuardrails(projectId, options = {}) {
  return useQuery({
    queryKey: projectKeys.guardrails(projectId),
    queryFn: () => getProjectGuardrails(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
    ...options,
  })
}

// Template queries
export const templateKeys = {
  all: ['templates'],
  list: () => [...templateKeys.all, 'list'],
}

export function useTemplates(options = {}) {
  return useQuery({
    queryKey: templateKeys.list(),
    queryFn: getTemplates,
    staleTime: 30_000,
    ...options,
  })
}
