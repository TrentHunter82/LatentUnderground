import { useQuery } from '@tanstack/react-query'
import {
  getSwarmStatus,
  getSwarmHistory,
  getSwarmAgents,
  getSwarmOutput,
  getAgentEvents,
  getLogs,
  searchLogs,
  getBusMessages,
  getBusInbox,
  getBusChannelMessages,
} from '../lib/api'

// Query key factories
export const swarmKeys = {
  all: ['swarm'],
  status: (projectId) => [...swarmKeys.all, 'status', projectId],
  history: (projectId) => [...swarmKeys.all, 'history', projectId],
  agents: (projectId) => [...swarmKeys.all, 'agents', projectId],
  output: (projectId, filters) => [...swarmKeys.all, 'output', projectId, filters],
  events: (projectId, filters) => [...swarmKeys.all, 'events', projectId, filters],
  logs: (projectId) => [...swarmKeys.all, 'logs', projectId],
  logSearch: (projectId, filters) => [...swarmKeys.all, 'logSearch', projectId, filters],
}

export function useSwarmStatus(projectId, options = {}) {
  return useQuery({
    queryKey: swarmKeys.status(projectId),
    queryFn: () => getSwarmStatus(projectId),
    enabled: !!projectId,
    staleTime: 5_000,
    ...options,
  })
}

export function useSwarmHistory(projectId, options = {}) {
  return useQuery({
    queryKey: swarmKeys.history(projectId),
    queryFn: () => getSwarmHistory(projectId),
    enabled: !!projectId,
    staleTime: 30_000,
    ...options,
  })
}

export function useSwarmAgents(projectId, options = {}) {
  return useQuery({
    queryKey: swarmKeys.agents(projectId),
    queryFn: () => getSwarmAgents(projectId),
    enabled: !!projectId,
    staleTime: 5_000,
    ...options,
  })
}

export function useSwarmOutput(projectId, { offset = 0, agent = null } = {}, options = {}) {
  return useQuery({
    queryKey: swarmKeys.output(projectId, { offset, agent }),
    queryFn: () => getSwarmOutput(projectId, offset, agent),
    enabled: !!projectId,
    staleTime: 3_000,
    ...options,
  })
}

export function useAgentEvents(projectId, filters = {}, options = {}) {
  return useQuery({
    queryKey: swarmKeys.events(projectId, filters),
    queryFn: () => getAgentEvents(projectId, filters),
    enabled: !!projectId,
    staleTime: 10_000,
    ...options,
  })
}

export function useLogs(projectId, lines = 200, options = {}) {
  return useQuery({
    queryKey: swarmKeys.logs(projectId),
    queryFn: () => getLogs(projectId, lines),
    enabled: !!projectId,
    staleTime: 30_000,
    ...options,
  })
}

export function useLogSearch(projectId, filters = {}, options = {}) {
  return useQuery({
    queryKey: swarmKeys.logSearch(projectId, filters),
    queryFn: () => searchLogs(projectId, filters),
    enabled: !!projectId && !!(filters.from_date || filters.to_date),
    staleTime: 30_000,
    ...options,
  })
}

// Message Bus query keys
export const busKeys = {
  all: (projectId) => ['bus', projectId],
  messages: (projectId, filters) => [...busKeys.all(projectId), 'messages', filters],
  inbox: (projectId, agent) => [...busKeys.all(projectId), 'inbox', agent],
  channel: (projectId, channel) => [...busKeys.all(projectId), 'channel', channel],
}

export function useBusMessages(projectId, filters = {}, options = {}) {
  return useQuery({
    queryKey: busKeys.messages(projectId, filters),
    queryFn: () => getBusMessages(projectId, filters),
    enabled: !!projectId,
    staleTime: 5_000,
    refetchInterval: 10_000,
    ...options,
  })
}

export function useBusInbox(projectId, agent, options = {}) {
  return useQuery({
    queryKey: busKeys.inbox(projectId, agent),
    queryFn: () => getBusInbox(projectId, agent),
    enabled: !!projectId && !!agent,
    staleTime: 5_000,
    refetchInterval: 10_000,
    ...options,
  })
}

export function useBusChannel(projectId, channel, filters = {}, options = {}) {
  return useQuery({
    queryKey: busKeys.channel(projectId, channel),
    queryFn: () => getBusChannelMessages(projectId, channel, filters),
    enabled: !!projectId && !!channel,
    staleTime: 5_000,
    refetchInterval: 10_000,
    ...options,
  })
}
