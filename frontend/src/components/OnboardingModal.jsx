import { useState, useEffect, useRef, useCallback } from 'react'

const steps = [
  {
    title: 'Welcome to Latent Underground',
    description:
      'A swarm orchestration control center for managing AI agent teams. Launch coordinated multi-agent workflows, monitor real-time execution, and analyze performance metrics from a unified command interface.',
    icon: (
      <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    title: 'Create Your First Project',
    description:
      'Define your mission objective and configure swarm parameters. Set the number of AI agents, choose max execution phases, and customize agent behavior. Each project tracks its own swarm runs and maintains independent configuration.',
    icon: (
      <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
  {
    title: 'Launch & Monitor',
    description:
      'Initiate swarm execution and observe agent coordination in real-time. Watch terminal output streams, track agent signals and task progress, and analyze completion metrics. Review historical runs and performance analytics to optimize future missions.',
    icon: (
      <svg className="w-12 h-12 text-crt-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
      </svg>
    ),
  },
]

export default function OnboardingModal({ open, onClose }) {
  const [step, setStep] = useState(0)
  const modalRef = useRef(null)

  const handleClose = useCallback(() => {
    localStorage.setItem('lu_onboarding_complete', 'true')
    onClose()
  }, [onClose])

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
    if (step < steps.length - 1) {
      setStep(step + 1)
    } else {
      handleClose()
    }
  }

  const handleBack = () => {
    if (step > 0) setStep(step - 1)
  }

  if (!open) return null

  const current = steps[step]

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

        <div className="flex flex-col items-center text-center space-y-6 mt-2">
          <div className="flex items-center justify-center">{current.icon}</div>

          <div className="space-y-3">
            <h2 id="onboarding-title" className="text-lg font-semibold text-zinc-100 font-mono m-0">
              {current.title}
            </h2>
            <p className="text-sm text-zinc-400 leading-relaxed m-0">{current.description}</p>
          </div>

          <div className="flex items-center justify-center gap-2 py-4">
            {steps.map((_, idx) => (
              <span
                key={idx}
                role="img"
                className={`w-2 h-2 rounded-full transition-colors ${
                  idx === step ? 'bg-crt-green' : 'bg-zinc-600'
                }`}
                aria-label={`Step ${idx + 1}${idx === step ? ' (current)' : ''}`}
              />
            ))}
          </div>

          <div className="flex items-center justify-between w-full pt-2">
            <button
              onClick={handleBack}
              disabled={step === 0}
              className="text-sm text-zinc-400 hover:text-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors font-mono bg-transparent border-0 cursor-pointer"
            >
              BACK
            </button>
            <button onClick={handleNext} className="btn-neon px-6 py-2 text-sm font-mono">
              {step === steps.length - 1 ? 'GET STARTED' : 'NEXT'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
