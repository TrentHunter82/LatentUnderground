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

export const KEYBOARD_SHORTCUTS = [
  { keys: 'Ctrl+K', description: 'Focus search', group: 'Navigation' },
  { keys: 'Escape', description: 'Close modal/dialog', group: 'Navigation' },
  { keys: 'Ctrl+N', description: 'New project', group: 'Actions' },
  { keys: 'Ctrl+?', description: 'Show keyboard shortcuts', group: 'Actions' },
  { keys: '←  →', description: 'Switch tabs', group: 'Views' },
  { keys: 'Home', description: 'First tab', group: 'Views' },
  { keys: 'End', description: 'Last tab', group: 'Views' },
]

export const DEFAULT_TEMPLATE_PRESETS = [
  {
    name: 'Quick Research',
    description: 'Fast research and analysis with minimal agent count',
    config: { agent_count: 2, max_phases: 3, model: 'sonnet' },
  },
  {
    name: 'Code Review',
    description: 'Thorough code review with testing and security analysis',
    config: { agent_count: 4, max_phases: 6, model: 'sonnet' },
  },
  {
    name: 'Feature Build',
    description: 'Full feature development with design, implementation, and testing',
    config: { agent_count: 4, max_phases: 12, model: 'opus' },
  },
  {
    name: 'Debugging',
    description: 'Focused debugging session with log analysis and fix verification',
    config: { agent_count: 3, max_phases: 8, model: 'sonnet' },
  },
]
