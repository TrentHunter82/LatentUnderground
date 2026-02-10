import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { createProject, launchSwarm, getTemplates, createTemplate } from '../lib/api'
import { DEFAULT_TEMPLATE_PRESETS } from '../lib/constants'
import { useToast } from './Toast'
import FolderBrowser from './FolderBrowser'
import TemplateManager from './TemplateManager'

const complexityOptions = ['Simple', 'Medium', 'Complex']

const defaultForm = {
  name: '',
  goal: '',
  project_type: 'Web Application (frontend + backend)',
  tech_stack: '',
  complexity: 'Medium',
  requirements: '',
  folder_path: '',
}

export default function NewProject({ onProjectChange }) {
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [templates, setTemplates] = useState([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [templateConfig, setTemplateConfig] = useState(null)
  const [form, setForm] = useState({ ...defaultForm })
  const [showBrowser, setShowBrowser] = useState(false)
  const [showManager, setShowManager] = useState(false)

  const toast = useToast()

  const refreshTemplates = () => {
    getTemplates().then(setTemplates).catch((err) => console.warn('Failed to load templates:', err.message))
  }

  useEffect(() => { refreshTemplates() }, [])

  const loadDefaultPresets = async () => {
    try {
      for (const preset of DEFAULT_TEMPLATE_PRESETS) {
        await createTemplate(preset)
      }
      refreshTemplates()
      toast('Default templates loaded', 'success')
    } catch (err) {
      toast(`Failed to load presets: ${err.message}`, 'error', 4000, {
        label: 'Retry',
        onClick: loadDefaultPresets,
      })
    }
  }

  const handleTemplateChange = (e) => {
    const id = e.target.value
    setSelectedTemplateId(id)

    if (!id) {
      setForm({ ...defaultForm })
      setTemplateConfig(null)
      return
    }

    const tmpl = templates.find((t) => String(t.id) === id)
    if (!tmpl) return

    const cfg = tmpl.config || {}
    setTemplateConfig(cfg)

    // Populate form fields from template config where applicable
    setForm((f) => ({
      ...f,
      project_type: cfg.project_type || f.project_type,
      tech_stack: cfg.tech_stack || f.tech_stack,
      complexity: cfg.complexity || f.complexity,
      requirements: cfg.requirements || f.requirements,
    }))
  }

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const project = await createProject(form)
      onProjectChange?.()
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setError(err.message)
      toast(err.message, 'error', 4000, { label: 'Retry', onClick: () => handleSubmit(e) })
    } finally {
      setLoading(false)
    }
  }

  const handleLaunchNew = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const project = await createProject(form)
      await launchSwarm({
        project_id: project.id,
        resume: false,
        no_confirm: true,
        agent_count: templateConfig?.agent_count ?? 4,
        max_phases: templateConfig?.max_phases ?? 24,
      })
      onProjectChange?.()
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setError(err.message)
      toast(err.message, 'error', 4000, { label: 'Retry', onClick: () => handleLaunchNew(e) })
    } finally {
      setLoading(false)
    }
  }

  const inputClass = 'retro-input w-full rounded px-3 py-2 text-sm transition-colors'
  const labelClass = 'block text-xs font-medium text-zinc-400 mb-1.5 font-mono uppercase tracking-wider'

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-4 py-4 sm:p-6">
        <h1 className="text-xl font-semibold text-zinc-100 mb-1 font-mono">New Swarm Project</h1>
        <p className="text-sm text-zinc-500 mb-6">Configure and launch a new Claude swarm session.</p>

        {error && (
          <div className="mb-4 px-4 py-2 rounded bg-signal-red/10 border border-signal-red/30 text-signal-red text-sm font-mono">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className={`${labelClass} mb-0`}>Start from Template</label>
              <button
                type="button"
                onClick={() => setShowManager((v) => !v)}
                className="text-[10px] text-zinc-500 hover:text-crt-green bg-transparent border-0 cursor-pointer font-mono transition-colors"
              >
                {showManager ? 'Hide Manager' : 'Manage Templates'}
              </button>
            </div>
            {templates.length > 0 && (
              <>
                <select
                  value={selectedTemplateId}
                  onChange={handleTemplateChange}
                  className={`${inputClass} cursor-pointer`}
                >
                  <option value="">Custom (no template)</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}{t.description ? ` — ${t.description}` : ''}
                    </option>
                  ))}
                </select>
                {templateConfig && (
                  <p className="text-xs text-zinc-600 mt-1 font-mono">
                    {templateConfig.agent_count && `${templateConfig.agent_count} agents`}
                    {templateConfig.agent_count && templateConfig.max_phases && ' · '}
                    {templateConfig.max_phases && `${templateConfig.max_phases} phases`}
                  </p>
                )}
              </>
            )}
            {templates.length === 0 && !showManager && (
              <div className="flex items-center gap-3">
                <p className="text-xs text-zinc-600 font-mono m-0">No templates yet.</p>
                <button
                  type="button"
                  onClick={loadDefaultPresets}
                  className="text-xs text-crt-green hover:text-crt-cyan bg-transparent border-0 cursor-pointer font-mono transition-colors"
                >
                  Load defaults
                </button>
              </div>
            )}
          </div>

          {showManager && (
            <TemplateManager onTemplatesChange={setTemplates} />
          )}

          <div>
            <label className={labelClass}>Project Name</label>
            <input
              className={inputClass}
              placeholder="My Awesome App"
              value={form.name}
              onChange={set('name')}
              required
            />
          </div>

          <div>
            <label className={labelClass}>Goal</label>
            <textarea
              className={`${inputClass} min-h-20 resize-y`}
              placeholder="What should this project accomplish?"
              value={form.goal}
              onChange={set('goal')}
              rows={3}
              required
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={labelClass}>Project Type</label>
              <input
                className={inputClass}
                placeholder="Web Application"
                value={form.project_type}
                onChange={set('project_type')}
              />
            </div>
            <div>
              <label className={labelClass}>Tech Stack</label>
              <input
                className={inputClass}
                placeholder="React + FastAPI + SQLite"
                value={form.tech_stack}
                onChange={set('tech_stack')}
              />
            </div>
          </div>

          <div>
            <label className={labelClass}>Complexity</label>
            <div className="flex flex-wrap gap-2">
              {complexityOptions.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, complexity: opt }))}
                  className={`px-3 sm:px-4 py-2 rounded text-sm font-medium transition-colors cursor-pointer font-mono ${
                    form.complexity === opt
                      ? 'btn-neon'
                      : 'bg-retro-grid text-zinc-400 hover:bg-retro-border border border-retro-border'
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className={labelClass}>Requirements</label>
            <textarea
              className={`${inputClass} min-h-20 resize-y`}
              placeholder="Specific requirements, constraints, or notes..."
              value={form.requirements}
              onChange={set('requirements')}
              rows={3}
            />
          </div>

          <div>
            <label className={labelClass}>Project Folder Path</label>
            <div className="flex gap-2">
              <input
                className={`${inputClass} flex-1`}
                placeholder="C:/Projects/my-app"
                value={form.folder_path}
                onChange={set('folder_path')}
                required
              />
              <button
                type="button"
                onClick={() => setShowBrowser(true)}
                className="px-3 py-2 rounded bg-retro-grid hover:bg-retro-border text-zinc-400 hover:text-crt-green text-sm font-mono border border-retro-border cursor-pointer transition-colors shrink-0"
                title="Browse for folder"
                aria-label="Browse for folder"
              >
                Browse
              </button>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="px-4 sm:px-5 py-2.5 rounded bg-retro-grid hover:bg-retro-border text-zinc-200 text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer border border-retro-border font-mono"
            >
              {loading ? 'Creating...' : 'Create Project'}
            </button>
            <button
              type="button"
              onClick={handleLaunchNew}
              disabled={loading}
              className="btn-neon px-4 sm:px-5 py-2.5 rounded text-sm disabled:opacity-50"
            >
              {loading ? 'Launching...' : 'Create & Launch'}
            </button>
          </div>
        </form>
      </div>

      <FolderBrowser
        open={showBrowser}
        onSelect={(path) => setForm((f) => ({ ...f, folder_path: path }))}
        onClose={() => setShowBrowser(false)}
      />
    </div>
  )
}
