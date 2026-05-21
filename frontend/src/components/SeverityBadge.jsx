const colors = {
  CRITICAL: { bg: '#7f1d1d', text: '#fca5a5' },
  HIGH:     { bg: '#7c2d12', text: '#fdba74' },
  MEDIUM:   { bg: '#713f12', text: '#fde68a' },
  LOW:      { bg: '#1e3a5f', text: '#93c5fd' },
}

export default function SeverityBadge({ severity }) {
  const s = (severity || '').toUpperCase()
  const c = colors[s] || colors.LOW
  return (
    <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 999, background: c.bg, color: c.text, fontSize: '0.75rem', fontWeight: 600 }}>
      {s || 'UNKNOWN'}
    </span>
  )
}
