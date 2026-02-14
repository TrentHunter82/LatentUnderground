import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useNotifications } from '../hooks/useNotifications'

const TOTAL_STEPS = 4

export default function OnboardingModal({ open, onClose }) {
  const [step, setStep] = useState(0)
  const modalRef = useRef(null)
  const navigate = useNavigate()
  const { permission, requestPermission } = useNotifications()
  const [notifRequested, setNotifRequested] = useState(false)

  const handleClose = useCallback(() => {
    localStorage.setItem('lu_onboarding_complete', 'true')
    onClose()
  }, [onClose])

  const handleCreateProject = useCallback(() => {
    localStorage.setItem('lu_onboarding_complete', 'true')
    onClose()
    navigate('/projects/new')
  }, [onClose, navigate])

  useEffect(() => {
    if (!open || !modalRef.current) return
    const focusable = modalRef.current.querySelectorAll('button')
    focusable[0]?.focus()
  }, [open, step])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      handleClose()
      return
    }
    if (e.key === 'Tab') {
      const modal = modalRef.current
      if (!modal) return
      const focusable = modal.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
  }, [handleClose])

  const handleNext = () => {
    if (step < TOTAL_STEPS - 1) {
      setStep(step + 1)
    } else {
      handleCreateProject()
    }
  }

  const handleBack = () => {
    if (step > 0) setStep(step - 1)
  }

  const handleRequestNotifications = async () => {
    setNotifRequested(true)
    await requestPermission()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={handleClose}>
      <div className="absolute inset-0 bg-black/70" />
      <div
        ref={modalRef}
        className="relative retro-panel border border-retro-border rounded shadow-2xl max-w-lg w-full mx-4 p-6 glow-green"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-title"
      >
        <button
          onClick={handleClose}
          className="absolute top-4 right-4 text-xs text-zinc-500 hover:text-zinc-300 transition-colors font-mono bg-transparent border-0 cursor-pointer"
          aria-label="Skip onboarding"
        >
          SKIP
        </button>

        <div className="flex flex-col items-center text-center space-y-5 mt-2">
          {step === 0 && <StepWelcome />}
          {step === 1 && <StepConfigure />}
          {step === 2 && <StepMonitor />}
          {step === 3 && (
            <StepNotifications
              permission={permission}
              notifRequested={notifRequested}
              onRequest={handleRequestNotifications}
            />
          )}

          {/* Step indicators */}
          <div className="flex items-center justify-center gap-2 py-3">
            {Array.from({ length: TOTAL_STEPS }).map((_, idx) => (
              <button
                key={idx}
                onClick={() => setStep(idx)}
                className={`w-2 h-2 rounded-full transition-colors border-0 cursor-pointer p-0 ${
                  idx === step ? 'bg-crt-green' : 'bg-zinc-600 hover:bg-zinc-500'
                }`}
                aria-label={`Go to step ${idx + 1}${idx === step ? ' (current)' : ''}`}
              />
            ))}
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between w-full pt-1">
            <button
              onClick={handleBack}
              disabled={step === 0}
              className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors font-mono bg-transparent border-0 cursor-pointer"
            >
              BACK
            </button>
            <button onClick={handleNext} className="btn-neon px-6 py-2 text-sm font-mono">
              {step === TOTAL_STEPS - 1 ? 'CREATE FIRST PROJECT' : 'NEXT'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function StepWelcome() {
  return (
    <>
      <div className="flex items-center justify-center">
        <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
        </svg>
      </div>
      <div className="space-y-3">
        <h2 id="onboarding-title" className="text-lg font-semibold text-zinc-100 font-mono m-0">
          Welcome to Latent Underground
        </h2>
        <p className="text-sm text-zinc-400 leading-relaxed m-0">
          A swarm orchestration control center for managing AI agent teams. Launch coordinated multi-agent workflows, monitor real-time execution, and analyze performance metrics.
        </p>
      </div>
      <div className="w-full text-left space-y-2 px-2">
        <Feature icon="terminal" label="Real-time terminal output per agent" />
        <Feature icon="grid" label="Dashboard with live agent status and metrics" />
        <Feature icon="history" label="Swarm run history with performance analytics" />
        <Feature icon="key" label="Keyboard shortcuts for power users" />
      </div>
    </>
  )
}

function StepConfigure() {
  return (
    <>
      <div className="flex items-center justify-center">
        <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </div>
      <div className="space-y-3">
        <h2 id="onboarding-title" className="text-lg font-semibold text-zinc-100 font-mono m-0">
          Create & Configure
        </h2>
        <p className="text-sm text-zinc-400 leading-relaxed m-0">
          Set up a project by defining your objective, choosing agent count, and configuring execution phases. Use templates for quick setup or customize every parameter.
        </p>
      </div>
      <div className="w-full text-left space-y-2 px-2">
        <Feature icon="template" label="Start from prebuilt templates or create your own" />
        <Feature icon="agents" label="Configure 1-4 specialized agents per project" />
        <Feature icon="folder" label="Point to any project folder on your machine" />
        <Shortcut keys="Ctrl+N" label="Quick-create a new project anytime" />
      </div>
    </>
  )
}

function StepMonitor() {
  return (
    <>
      <div className="flex items-center justify-center">
        <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      </div>
      <div className="space-y-3">
        <h2 id="onboarding-title" className="text-lg font-semibold text-zinc-100 font-mono m-0">
          Launch & Monitor
        </h2>
        <p className="text-sm text-zinc-400 leading-relaxed m-0">
          Watch agents work in real-time. Each agent gets its own terminal tab with live output. Stop individual agents, send input, and export logs for review.
        </p>
      </div>
      <div className="w-full text-left space-y-2 px-2">
        <Feature icon="tabs" label="Per-agent terminal tabs with LED status indicators" />
        <Feature icon="stop" label="Stop individual agents or the entire swarm" />
        <Feature icon="export" label="Export terminal output and project data" />
        <Shortcut keys="Ctrl+L" label="Clear terminal output instantly" />
      </div>
    </>
  )
}

function StepNotifications({ permission, notifRequested, onRequest }) {
  const granted = permission === 'granted'
  const denied = permission === 'denied'

  return (
    <>
      <div className="flex items-center justify-center">
        <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
      </div>
      <div className="space-y-3">
        <h2 id="onboarding-title" className="text-lg font-semibold text-zinc-100 font-mono m-0">
          Stay Informed
        </h2>
        <p className="text-sm text-zinc-400 leading-relaxed m-0">
          Get browser notifications when agents crash or swarms complete. Notifications only fire when the tab is in the background, so they won't interrupt your work.
        </p>
      </div>

      <div className="w-full px-2">
        {granted ? (
          <div className="flex items-center gap-2 p-3 rounded bg-crt-green/10 border border-crt-green/20">
            <svg className="w-4 h-4 text-crt-green shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-sm text-crt-green font-mono">Notifications enabled</span>
          </div>
        ) : denied ? (
          <div className="flex items-center gap-2 p-3 rounded bg-signal-red/10 border border-signal-red/20">
            <span className="text-sm text-zinc-400 font-mono">
              Notifications blocked by browser. You can enable them in your browser settings.
            </span>
          </div>
        ) : (
          <button
            onClick={onRequest}
            disabled={notifRequested}
            className="w-full p-3 rounded bg-retro-grid hover:bg-retro-border border border-retro-border text-zinc-200 text-sm font-mono cursor-pointer transition-colors disabled:opacity-50"
          >
            {notifRequested ? 'Requesting...' : 'Enable Browser Notifications'}
          </button>
        )}
      </div>

      <p className="text-xs text-zinc-600 m-0">
        You can change this anytime in Settings.
      </p>
    </>
  )
}

function Feature({ icon, label }) {
  const icons = {
    terminal: <path strokeLinecap="round" strokeLinejoin="round" d="M8 9l3 3-3 3m5 0h3" />,
    grid: <path strokeLinecap="round" strokeLinejoin="round" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />,
    history: <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />,
    key: <path strokeLinecap="round" strokeLinejoin="round" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />,
    template: <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />,
    agents: <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />,
    folder: <path strokeLinecap="round" strokeLinejoin="round" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />,
    tabs: <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />,
    stop: <path strokeLinecap="round" strokeLinejoin="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />,
    export: <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />,
  }

  return (
    <div className="flex items-center gap-2.5 py-1">
      <svg className="w-4 h-4 text-crt-green/70 shrink-0" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
        {icons[icon]}
      </svg>
      <span className="text-xs text-zinc-400 font-mono">{label}</span>
    </div>
  )
}

function Shortcut({ keys, label }) {
  return (
    <div className="flex items-center gap-2.5 py-1">
      <kbd className="text-[10px] font-mono bg-retro-grid border border-retro-border rounded px-1.5 py-0.5 text-crt-green shrink-0 min-w-[3.5rem] text-center">
        {keys}
      </kbd>
      <span className="text-xs text-zinc-400 font-mono">{label}</span>
    </div>
  )
}
