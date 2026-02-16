import { useState, useEffect, useRef, useCallback } from 'react'
import { useProjectQuota } from '../hooks/useProjectQuery'

const RULE_TYPES = [
  { value: 'regex_match', label: 'Require Pattern', needsPattern: true },
  { value: 'regex_reject', label: 'Forbid Pattern', needsPattern: true },
  { value: 'min_lines', label: 'Min Output Lines', needsThreshold: true },
  { value: 'max_errors', label: 'Max Error Count', needsThreshold: true },
]

const MAX_GUARDRAIL_RULES = 20
const PATTERN_MAX_LENGTH = 200

function emptyRule() {
  return { type: 'regex_match', pattern: '', threshold: 0, action: 'warn' }
}

function QuotaSlider({ id, label, value, onChange, min, max, step = 1, unit = '', disabled = false, usage = null, usageMax = null }) {
  const pct = usageMax && usageMax > 0 ? Math.min((usage / usageMax) * 100, 100) : 0
  const isWarning = pct >= 80
  const isCritical = pct >= 100

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-xs text-zinc-400 font-mono">{label}</label>
        <span className="text-xs text-zinc-300 font-mono">
          {value === null || value === undefined ? 'Unlimited' : `${value}${unit}`}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value ?? max}
        onChange={(e) => {
          const v = Number(e.target.value)
          onChange(v === max ? null : v)
        }}
        disabled={disabled}
        className="w-full h-1.5 bg-retro-grid rounded-full appearance-none cursor-pointer accent-crt-green [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-crt-green [&::-webkit-slider-thumb]:appearance-none"
        aria-label={`${label}: ${value ?? 'Unlimited'}`}
      />
      {usage != null && usageMax != null && usageMax > 0 && (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1 bg-retro-grid rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                isCritical ? 'bg-signal-red' : isWarning ? 'bg-signal-amber' : 'bg-crt-green'
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <span className={`text-[10px] font-mono ${isCritical ? 'text-signal-red' : isWarning ? 'text-signal-amber' : 'text-zinc-500'}`}>
            {usage}/{usageMax}
          </span>
        </div>
      )}
    </div>
  )
}

function GuardrailRuleRow({ rule, index, onChange, onRemove }) {
  const typeInfo = RULE_TYPES.find(t => t.value === rule.type) || RULE_TYPES[0]

  return (
    <div className="flex flex-col gap-1.5 p-2 rounded bg-retro-bg/50 border border-retro-border" data-testid={`guardrail-rule-${index}`}>
      <div className="flex items-center gap-2">
        <select
          value={rule.type}
          onChange={(e) => onChange(index, { ...rule, type: e.target.value })}
          className="retro-input px-2 py-1 rounded text-xs flex-1"
          aria-label={`Rule ${index + 1} type`}
        >
          {RULE_TYPES.map(t => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
        <select
          value={rule.action}
          onChange={(e) => onChange(index, { ...rule, action: e.target.value })}
          className={`retro-input px-2 py-1 rounded text-xs w-20 ${
            rule.action === 'halt' ? 'text-signal-red' : 'text-signal-amber'
          }`}
          aria-label={`Rule ${index + 1} action`}
        >
          <option value="warn">Warn</option>
          <option value="halt">Halt</option>
        </select>
        <button
          type="button"
          onClick={() => onRemove(index)}
          className="p-1 rounded text-zinc-600 hover:text-signal-red hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors shrink-0"
          aria-label={`Remove rule ${index + 1}`}
          title="Remove rule"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M3 3l8 8M11 3l-8 8" />
          </svg>
        </button>
      </div>
      {typeInfo.needsPattern && (
        <input
          type="text"
          value={rule.pattern || ''}
          onChange={(e) => onChange(index, { ...rule, pattern: e.target.value })}
          placeholder="Regex pattern (e.g. BUILD SUCCESS)"
          maxLength={PATTERN_MAX_LENGTH}
          className="retro-input px-2 py-1 rounded text-xs w-full"
          aria-label={`Rule ${index + 1} pattern`}
        />
      )}
      {typeInfo.needsThreshold && (
        <input
          type="number"
          value={rule.threshold ?? 0}
          onChange={(e) => onChange(index, { ...rule, threshold: Math.max(0, Number(e.target.value) || 0) })}
          min={0}
          className="retro-input px-2 py-1 rounded text-xs w-24"
          aria-label={`Rule ${index + 1} threshold`}
        />
      )}
    </div>
  )
}

export default function ProjectSettings({ projectId, initialConfig, onSave }) {
  const [agentCount, setAgentCount] = useState(4)
  const [maxPhases, setMaxPhases] = useState(24)
  const [customPrompts, setCustomPrompts] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [fieldErrors, setFieldErrors] = useState({})

  // Quota state
  const [maxAgentsConcurrent, setMaxAgentsConcurrent] = useState(null)
  const [maxDurationHours, setMaxDurationHours] = useState(null)
  const [maxRestartsPerAgent, setMaxRestartsPerAgent] = useState(null)
  const [quotaUsage, setQuotaUsage] = useState(null)

  // Circuit breaker config
  const [cbMaxFailures, setCbMaxFailures] = useState(3)
  const [cbWindowSeconds, setCbWindowSeconds] = useState(300)
  const [cbRecoverySeconds, setCbRecoverySeconds] = useState(60)

  // Guardrail rules
  const [guardrailRules, setGuardrailRules] = useState([])

  // Track the "saved" state for dirty detection
  const savedConfig = useRef({ agent_count: 4, max_phases: 999, custom_prompts: '', max_agents_concurrent: null, max_duration_hours: null, max_restarts_per_agent: null, circuit_breaker_max_failures: 3, circuit_breaker_window_seconds: 300, circuit_breaker_recovery_seconds: 60, guardrails: [] })

  useEffect(() => {
    if (initialConfig) {
      const ac = initialConfig.agent_count ?? 4
      const mp = initialConfig.max_phases ?? 999
      const cp = initialConfig.custom_prompts ?? ''
      const mac = initialConfig.max_agents_concurrent ?? null
      const mdh = initialConfig.max_duration_hours ?? null
      const mra = initialConfig.max_restarts_per_agent ?? null
      setAgentCount(ac)
      setMaxPhases(mp)
      setCustomPrompts(cp)
      setMaxAgentsConcurrent(mac)
      setMaxDurationHours(mdh)
      setMaxRestartsPerAgent(mra)
      setCbMaxFailures(initialConfig.circuit_breaker_max_failures ?? 3)
      setCbWindowSeconds(initialConfig.circuit_breaker_window_seconds ?? 300)
      setCbRecoverySeconds(initialConfig.circuit_breaker_recovery_seconds ?? 60)
      const gr = Array.isArray(initialConfig.guardrails) ? initialConfig.guardrails : []
      setGuardrailRules(gr.map(r => ({ type: r.type, pattern: r.pattern || '', threshold: r.threshold ?? 0, action: r.action || 'warn' })))
      savedConfig.current = { agent_count: ac, max_phases: mp, custom_prompts: cp, max_agents_concurrent: mac, max_duration_hours: mdh, max_restarts_per_agent: mra, circuit_breaker_max_failures: initialConfig.circuit_breaker_max_failures ?? 3, circuit_breaker_window_seconds: initialConfig.circuit_breaker_window_seconds ?? 300, circuit_breaker_recovery_seconds: initialConfig.circuit_breaker_recovery_seconds ?? 60, guardrails: gr }
    }
  }, [initialConfig])

  // Fetch quota usage via TanStack Query
  const { data: quotaData } = useProjectQuota(projectId, { enabled: !!projectId })
  useEffect(() => {
    if (quotaData) setQuotaUsage(quotaData)
  }, [quotaData])

  const isDirty = useCallback(() => {
    const savedGr = savedConfig.current.guardrails || []
    const grChanged = JSON.stringify(guardrailRules) !== JSON.stringify(savedGr.map(r => ({ type: r.type, pattern: r.pattern || '', threshold: r.threshold ?? 0, action: r.action || 'warn' })))
    return (
      agentCount !== savedConfig.current.agent_count ||
      maxPhases !== savedConfig.current.max_phases ||
      (customPrompts || '') !== (savedConfig.current.custom_prompts || '') ||
      maxAgentsConcurrent !== savedConfig.current.max_agents_concurrent ||
      maxDurationHours !== savedConfig.current.max_duration_hours ||
      maxRestartsPerAgent !== savedConfig.current.max_restarts_per_agent ||
      cbMaxFailures !== savedConfig.current.circuit_breaker_max_failures ||
      cbWindowSeconds !== savedConfig.current.circuit_breaker_window_seconds ||
      cbRecoverySeconds !== savedConfig.current.circuit_breaker_recovery_seconds ||
      grChanged
    )
  }, [agentCount, maxPhases, customPrompts, maxAgentsConcurrent, maxDurationHours, maxRestartsPerAgent, cbMaxFailures, cbWindowSeconds, cbRecoverySeconds, guardrailRules])

  // Warn on browser navigation/close when dirty
  useEffect(() => {
    const handler = (e) => {
      if (isDirty()) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isDirty])

  const handleAddRule = () => {
    if (guardrailRules.length >= MAX_GUARDRAIL_RULES) return
    setGuardrailRules(prev => [...prev, emptyRule()])
  }

  const handleUpdateRule = (index, updated) => {
    setGuardrailRules(prev => prev.map((r, i) => i === index ? updated : r))
  }

  const handleRemoveRule = (index) => {
    setGuardrailRules(prev => prev.filter((_, i) => i !== index))
  }

  const handleSave = async (e) => {
    e.preventDefault()
    if (!onSave) return
    setSaving(true)
    setSaved(false)
    try {
      // Build guardrail rules for API - strip empty pattern/threshold based on type
      const cleanedRules = guardrailRules.map(r => {
        const typeInfo = RULE_TYPES.find(t => t.value === r.type)
        const rule = { type: r.type, action: r.action }
        if (typeInfo?.needsPattern) rule.pattern = r.pattern || ''
        if (typeInfo?.needsThreshold) rule.threshold = r.threshold ?? 0
        return rule
      })

      const config = {
        agent_count: agentCount,
        max_phases: maxPhases,
        custom_prompts: customPrompts || undefined,
        max_agents_concurrent: maxAgentsConcurrent,
        max_duration_hours: maxDurationHours,
        max_restarts_per_agent: maxRestartsPerAgent,
        circuit_breaker_max_failures: cbMaxFailures,
        circuit_breaker_window_seconds: cbWindowSeconds,
        circuit_breaker_recovery_seconds: cbRecoverySeconds,
        guardrails: cleanedRules.length > 0 ? cleanedRules : null,
      }
      await onSave(projectId, config)
      savedConfig.current = { agent_count: agentCount, max_phases: maxPhases, custom_prompts: customPrompts || '', max_agents_concurrent: maxAgentsConcurrent, max_duration_hours: maxDurationHours, max_restarts_per_agent: maxRestartsPerAgent, circuit_breaker_max_failures: cbMaxFailures, circuit_breaker_window_seconds: cbWindowSeconds, circuit_breaker_recovery_seconds: cbRecoverySeconds, guardrails: cleanedRules }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  const dirty = isDirty()

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
            onChange={(e) => {
              const raw = Number(e.target.value) || 1
              const clamped = Math.min(10, Math.max(1, raw))
              setAgentCount(clamped)
              setFieldErrors(prev => ({
                ...prev,
                agentCount: raw !== clamped ? `Value clamped to ${clamped} (must be 1\u201310)` : null
              }))
            }}
            aria-describedby="agentCount-hint agentCount-error"
            aria-required="true"
            className="retro-input w-full px-3 py-2 rounded text-sm"
          />
          <span id="agentCount-hint" className="text-[10px] text-zinc-600 font-mono mt-0.5 block">Must be between 1 and 10</span>
          {fieldErrors.agentCount && (
            <span id="agentCount-error" role="alert" className="text-[10px] text-signal-red font-mono mt-0.5 block">
              {fieldErrors.agentCount}
            </span>
          )}
        </div>
        <div>
          <label htmlFor="maxPhases" className="block text-sm text-zinc-400 mb-1 font-mono">Max Phases</label>
          <input
            id="maxPhases"
            type="number"
            min={1}
            max={999}
            value={maxPhases}
            onChange={(e) => {
              const raw = Number(e.target.value) || 1
              const clamped = Math.min(999, Math.max(1, raw))
              setMaxPhases(clamped)
              setFieldErrors(prev => ({
                ...prev,
                maxPhases: raw !== clamped ? `Value clamped to ${clamped} (must be 1\u2013999)` : null
              }))
            }}
            aria-describedby="maxPhases-hint maxPhases-error"
            aria-required="true"
            className="retro-input w-full px-3 py-2 rounded text-sm"
          />
          <span id="maxPhases-hint" className="text-[10px] text-zinc-600 font-mono mt-0.5 block">Must be between 1 and 999</span>
          {fieldErrors.maxPhases && (
            <span id="maxPhases-error" role="alert" className="text-[10px] text-signal-red font-mono mt-0.5 block">
              {fieldErrors.maxPhases}
            </span>
          )}
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
            aria-describedby="customPrompts-hint"
          />
          <span id="customPrompts-hint" className="text-[10px] text-zinc-600 font-mono mt-0.5 block">Optional: extra instructions sent to all agents</span>
        </div>
        {/* Resource Quotas */}
        <div className="pt-3 border-t border-retro-border">
          <h4 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono mb-3 m-0">Resource Quotas</h4>
          <div className="space-y-3">
            <QuotaSlider
              id="maxAgentsConcurrent"
              label="Max Concurrent Agents"
              value={maxAgentsConcurrent}
              onChange={setMaxAgentsConcurrent}
              min={1}
              max={20}
              usage={quotaUsage?.agent_count}
              usageMax={maxAgentsConcurrent}
            />
            <QuotaSlider
              id="maxDurationHours"
              label="Max Duration"
              value={maxDurationHours}
              onChange={setMaxDurationHours}
              min={1}
              max={48}
              step={0.5}
              unit="h"
              usage={quotaUsage?.elapsed_hours}
              usageMax={maxDurationHours}
            />
            <QuotaSlider
              id="maxRestartsPerAgent"
              label="Max Restarts/Agent"
              value={maxRestartsPerAgent}
              onChange={setMaxRestartsPerAgent}
              min={0}
              max={10}
              usage={quotaUsage?.max_restart_count}
              usageMax={maxRestartsPerAgent}
            />
            <p className="text-[10px] text-zinc-600 font-mono m-0">
              Set to max to allow unlimited. Quotas prevent runaway agents.
            </p>
          </div>
        </div>

        {/* Circuit Breaker Config */}
        <div className="pt-3 border-t border-retro-border">
          <h4 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono mb-3 m-0">Circuit Breaker</h4>
          <div className="space-y-3">
            <QuotaSlider
              id="cbMaxFailures"
              label="Max Failures Before Open"
              value={cbMaxFailures}
              onChange={(v) => setCbMaxFailures(v ?? 3)}
              min={1}
              max={10}
            />
            <QuotaSlider
              id="cbWindowSeconds"
              label="Failure Window"
              value={cbWindowSeconds}
              onChange={(v) => setCbWindowSeconds(v ?? 300)}
              min={60}
              max={3600}
              step={60}
              unit="s"
            />
            <QuotaSlider
              id="cbRecoverySeconds"
              label="Recovery Time"
              value={cbRecoverySeconds}
              onChange={(v) => setCbRecoverySeconds(v ?? 60)}
              min={30}
              max={600}
              step={30}
              unit="s"
            />
            <p className="text-[10px] text-zinc-600 font-mono m-0">
              Circuit breaker prevents crash loops by blocking agent restarts after repeated failures.
            </p>
          </div>
        </div>

        {/* Output Guardrails */}
        <div className="pt-3 border-t border-retro-border">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono m-0">Output Guardrails</h4>
            {guardrailRules.length < MAX_GUARDRAIL_RULES && (
              <button
                type="button"
                onClick={handleAddRule}
                className="text-[10px] text-crt-green hover:text-crt-cyan bg-transparent border-0 cursor-pointer font-mono transition-colors"
              >
                + Add Rule
              </button>
            )}
          </div>
          {guardrailRules.length === 0 ? (
            <div className="text-[10px] text-zinc-600 font-mono py-2 text-center">
              No guardrail rules configured. Add rules to validate agent output on completion.
            </div>
          ) : (
            <div className="space-y-2">
              {guardrailRules.map((rule, i) => (
                <GuardrailRuleRow
                  key={i}
                  rule={rule}
                  index={i}
                  onChange={handleUpdateRule}
                  onRemove={handleRemoveRule}
                />
              ))}
            </div>
          )}
          <p className="text-[10px] text-zinc-600 font-mono m-0 mt-2">
            Rules run when all agents exit. Halt stops the swarm; Warn logs and continues. Max {MAX_GUARDRAIL_RULES} rules, patterns up to {PATTERN_MAX_LENGTH} chars.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            aria-busy={saving}
            className="btn-neon px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Settings'}
          </button>
          <span aria-live="polite" className="text-[10px] font-mono">
            {dirty && !saving && !saved && (
              <span className="text-signal-yellow" role="status">Unsaved changes</span>
            )}
            {saved && (
              <span className="text-crt-green" role="status">Settings saved</span>
            )}
          </span>
        </div>
      </form>
    </div>
  )
}
