import { useState, useEffect } from 'react'

export default function ProjectSettings({ projectId, initialConfig, onSave }) {
  const [agentCount, setAgentCount] = useState(4)
  const [maxPhases, setMaxPhases] = useState(24)
  const [customPrompts, setCustomPrompts] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (initialConfig) {
      setAgentCount(initialConfig.agent_count ?? 4)
      setMaxPhases(initialConfig.max_phases ?? 24)
      setCustomPrompts(initialConfig.custom_prompts ?? '')
    }
  }, [initialConfig])

  const handleSave = async (e) => {
    e.preventDefault()
    if (!onSave) return
    setSaving(true)
    setSaved(false)
    try {
      await onSave(projectId, { agent_count: agentCount, max_phases: maxPhases, custom_prompts: customPrompts || undefined })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Project Settings</h3>
      <form onSubmit={handleSave} className="space-y-4">
        <div>
          <label htmlFor="agentCount" className="block text-sm text-zinc-400 mb-1 font-mono">Agent Count</label>
          <input
            id="agentCount"
            type="number"
            min={1}
            max={10}
            value={agentCount}
            onChange={(e) => setAgentCount(Number(e.target.value))}
            className="retro-input w-full px-3 py-2 rounded text-sm"
          />
        </div>
        <div>
          <label htmlFor="maxPhases" className="block text-sm text-zinc-400 mb-1 font-mono">Max Phases</label>
          <input
            id="maxPhases"
            type="number"
            min={1}
            max={20}
            value={maxPhases}
            onChange={(e) => setMaxPhases(Number(e.target.value))}
            className="retro-input w-full px-3 py-2 rounded text-sm"
          />
        </div>
        <div>
          <label htmlFor="customPrompts" className="block text-sm text-zinc-400 mb-1 font-mono">Custom Prompts</label>
          <textarea
            id="customPrompts"
            value={customPrompts}
            onChange={(e) => setCustomPrompts(e.target.value)}
            rows={3}
            placeholder="Optional: custom instructions for agents..."
            className="retro-input w-full px-3 py-2 rounded text-sm resize-y"
          />
        </div>
        <button
          type="submit"
          disabled={saving}
          className="btn-neon px-4 py-2 rounded text-sm disabled:opacity-50"
        >
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Settings'}
        </button>
      </form>
    </div>
  )
}
