import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { signup, setStoredApiKey } from '../api'

export default function Signup() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [issued, setIssued] = useState(null) // { api_key, org_name, user_email }
  const [copied, setCopied] = useState(false)

  function update(field) {
    return (e) => setForm((cur) => ({ ...cur, [field]: e.target.value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    if (!form.name.trim()) return setError('Organization name is required.')
    if (!form.email.includes('@')) return setError('Please enter a valid email.')
    if (form.password.length < 8) return setError('Password must be at least 8 characters.')
    setSubmitting(true)
    try {
      const data = await signup(form)
      if (data?.api_key) setStoredApiKey(data.api_key)
      setIssued(data)
    } catch (err) {
      setError(err.message || 'Signup failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  async function copyKey() {
    if (!issued?.api_key) return
    try {
      await navigator.clipboard.writeText(issued.api_key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback: do nothing — user can select & copy manually.
    }
  }

  if (issued) {
    return (
      <div className="auth-shell">
        <div className="panel auth-card">
          <h2 style={{ marginTop: 0 }}>Welcome to NetGuard</h2>
          <p className="subtle" style={{ marginBottom: '1rem' }}>
            Your organization <strong>{issued.org_name}</strong> is ready.
          </p>
          <p style={{ color: '#fbbf24', fontWeight: 600, margin: '0 0 0.5rem' }}>
            Save this API key now — it will not be shown again.
          </p>
          <div
            style={{
              fontFamily: 'SF Mono, Monaco, Consolas, monospace',
              background: '#020617',
              border: '1px solid #1e3a5f',
              borderRadius: 8,
              padding: '0.75rem',
              wordBreak: 'break-all',
              fontSize: '0.85rem',
              color: '#22d3ee',
              margin: '0 0 0.75rem',
            }}
          >
            {issued.api_key}
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button type="button" className="btn" onClick={copyKey}>
              {copied ? 'Copied!' : 'Copy API key'}
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => navigate('/', { replace: true })}
            >
              Go to dashboard
            </button>
          </div>
          <p className="subtle" style={{ fontSize: '0.85rem', marginTop: '1rem' }}>
            This key will remain valid until you regenerate it from Settings. Treat it like a password.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="auth-shell">
      <form className="panel auth-card" onSubmit={handleSubmit}>
        <h2 style={{ marginTop: 0 }}>Create your NetGuard org</h2>
        <p className="subtle" style={{ marginBottom: '1rem' }}>
          Sign up to scan repositories and view org-scoped findings.
        </p>

        <label className="auth-label">Organization name</label>
        <input
          autoFocus
          value={form.name}
          onChange={update('name')}
          placeholder="Acme Corp"
          autoComplete="organization"
        />

        <label className="auth-label">Email</label>
        <input
          type="email"
          value={form.email}
          onChange={update('email')}
          placeholder="you@company.com"
          autoComplete="email"
        />

        <label className="auth-label">Password</label>
        <input
          type="password"
          value={form.password}
          onChange={update('password')}
          placeholder="At least 8 characters"
          autoComplete="new-password"
        />

        {error && (
          <div className="fix-error" style={{ marginTop: '0.5rem' }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          className="btn"
          disabled={submitting}
          style={{ width: '100%', marginTop: '0.75rem' }}
        >
          {submitting ? 'Creating org…' : 'Create account'}
        </button>

        <p className="subtle" style={{ marginTop: '0.75rem', fontSize: '0.85rem' }}>
          Already have an account? <Link to="/login" style={{ color: '#22d3ee' }}>Log in</Link>
        </p>
      </form>
    </div>
  )
}
