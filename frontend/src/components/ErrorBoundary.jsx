import { Component } from 'react'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-retro-dark flex items-center justify-center p-8" role="alert" aria-live="assertive">
          <div className="max-w-md w-full retro-panel border border-retro-border rounded p-6 text-center glow-magenta">
            <h1 className="text-xl font-semibold text-signal-red mb-2 font-mono">Something went wrong</h1>
            <p className="text-zinc-400 text-sm mb-4">
              {this.state.error?.message || 'An unexpected error occurred.'}
            </p>
            <button
              onClick={this.handleRetry}
              className="btn-neon px-4 py-2 rounded text-sm"
            >
              Try Again
            </button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
