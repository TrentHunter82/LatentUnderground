// Shared agent and status constants - single source of truth
// Used by: AgentGrid, LogViewer, ActivityFeed

export const AGENT_NAMES = ['Claude-1', 'Claude-2', 'Claude-3', 'Claude-4', 'supervisor']

export const AGENT_ROLES = {
  'Claude-1': 'Backend/Core',
  'Claude-2': 'Frontend/UI',
  'Claude-3': 'Integration/Test',
  'Claude-4': 'Polish/Review',
}

export const AGENT_BORDER_COLORS = {
  'Claude-1': 'border-crt-cyan',
  'Claude-2': 'border-crt-magenta',
  'Claude-3': 'border-crt-green',
  'Claude-4': 'border-crt-amber',
}

export const AGENT_NEON_COLORS = {
  'Claude-1': 'neon-cyan',
  'Claude-2': 'neon-magenta',
  'Claude-3': 'neon-green',
  'Claude-4': 'neon-amber',
  'supervisor': 'text-zinc-400',
}

export const AGENT_LOG_COLORS = {
  'Claude-1': { label: 'neon-cyan', bg: 'bg-crt-cyan/5' },
  'Claude-2': { label: 'neon-magenta', bg: 'bg-crt-magenta/5' },
  'Claude-3': { label: 'neon-green', bg: 'bg-crt-green/5' },
  'Claude-4': { label: 'neon-amber', bg: 'bg-crt-amber/5' },
  'supervisor': { label: 'text-zinc-400', bg: 'bg-zinc-500/5' },
}
