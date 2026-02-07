import { useNavigate } from 'react-router-dom'

export default function Home() {
  const navigate = useNavigate()

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center max-w-md">
        {/* Logo/Brand */}
        <div className="mb-6">
          <div className="w-16 h-16 rounded bg-crt-green/10 border border-crt-green/30 flex items-center justify-center mx-auto mb-4 glow-green">
            <div className="w-8 h-8 rounded bg-crt-green/20 flex items-center justify-center neon-green font-bold text-sm">
              LU
            </div>
          </div>
          <h1 className="text-2xl font-bold text-zinc-100 m-0 font-mono">Latent Underground</h1>
          <p className="text-sm text-zinc-500 mt-2 font-mono">
            Swarm orchestration control center. Create a project or select one from the sidebar.
          </p>
        </div>

        {/* Quick actions */}
        <div className="space-y-3">
          <button
            onClick={() => navigate('/projects/new')}
            className="btn-neon w-full py-3 px-4 rounded text-sm"
          >
            + New Swarm Project
          </button>
          <div className="text-xs text-zinc-600 font-mono">
            or select an existing project from the sidebar
          </div>
        </div>
      </div>
    </div>
  )
}
