import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  createProject,
  updateProject,
  deleteProject,
  launchSwarm,
  stopSwarm,
  sendDirective,
  updateAgentPrompt,
  updateProjectConfig,
  archiveProject,
  unarchiveProject,
  stopSwarmAgent,
  restartAgent,
  sendSwarmInput,
  createTemplate,
  sendBusMessage,
} from '../lib/api'
import { projectKeys, templateKeys } from './useProjectQuery'
import { swarmKeys, busKeys } from './useSwarmQuery'

export function useCreateProject(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useUpdateProject(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }) => updateProject(id, data),
    onSuccess: (_, { id }) => {
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(id) })
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useDeleteProject(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: deleteProject,
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: projectKeys.detail(id) })
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useUpdateProjectConfig(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, config }) => updateProjectConfig(projectId, config),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) })
    },
    ...options,
  })
}

export function useLaunchSwarm(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: launchSwarm,
    onSuccess: (_, variables) => {
      const projectId = variables.project_id
      queryClient.invalidateQueries({ queryKey: swarmKeys.status(projectId) })
      queryClient.invalidateQueries({ queryKey: swarmKeys.agents(projectId) })
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) })
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useStopSwarm(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: stopSwarm,
    onSuccess: (_, variables) => {
      const projectId = variables.project_id
      queryClient.invalidateQueries({ queryKey: swarmKeys.status(projectId) })
      queryClient.invalidateQueries({ queryKey: swarmKeys.agents(projectId) })
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) })
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useSendDirective(options = {}) {
  return useMutation({
    mutationFn: ({ projectId, agentName, text, priority }) =>
      sendDirective(projectId, agentName, text, priority),
    ...options,
  })
}

export function useUpdateAgentPrompt(options = {}) {
  return useMutation({
    mutationFn: ({ projectId, agentName, content }) =>
      updateAgentPrompt(projectId, agentName, content),
    ...options,
  })
}

export function useArchiveProject(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: archiveProject,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(id) })
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useUnarchiveProject(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: unarchiveProject,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: projectKeys.detail(id) })
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
    },
    ...options,
  })
}

export function useStopSwarmAgent(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, agentName }) => stopSwarmAgent(projectId, agentName),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: swarmKeys.agents(projectId) })
    },
    ...options,
  })
}

export function useRestartAgent(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, agentName }) => restartAgent(projectId, agentName),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: swarmKeys.agents(projectId) })
    },
    ...options,
  })
}

export function useSendSwarmInput(options = {}) {
  return useMutation({
    mutationFn: ({ projectId, text, agent }) => sendSwarmInput(projectId, text, agent),
    ...options,
  })
}

export function useCreateTemplate(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: templateKeys.list() })
    },
    ...options,
  })
}

export function useSendBusMessage(options = {}) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ projectId, data }) => sendBusMessage(projectId, data),
    onSuccess: (_, { projectId }) => {
      queryClient.invalidateQueries({ queryKey: busKeys.messages(projectId, {}) })
    },
    ...options,
  })
}
