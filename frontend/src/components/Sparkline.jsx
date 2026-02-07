export default function Sparkline({ data = [], width = 80, height = 24, color = '#80C8B0' }) {
  if (!data.length) {
    return (
      <svg width={width} height={height} role="img" aria-label="Sparkline: no data">
        <line x1={0} y1={height / 2} x2={width} y2={height / 2} stroke={color} strokeWidth={1} opacity={0.3} />
      </svg>
    )
  }

  if (data.length === 1) {
    return (
      <svg width={width} height={height} role="img" aria-label="Sparkline: 1 point">
        <circle cx={width / 2} cy={height / 2} r={2} fill={color} />
      </svg>
    )
  }

  const max = Math.max(...data)
  const min = Math.min(...data)
  const range = max - min || 1
  const padding = 2

  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * width
      const y = padding + ((max - v) / range) * (height - padding * 2)
      return `${x},${y}`
    })
    .join(' ')

  return (
    <svg width={width} height={height} role="img" aria-label={`Sparkline: ${data.length} points`}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
