import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchStats, fetchScans } from '../api'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [lastScan, setLastScan] = useState(null)

  useEffect(() => {
    fetchStats().then(setStats).catch(() => setStats(null))
    fetchScans().then((d) => {
      const items = d.items || []
      const completed = items.filter((s) => s.status === 'completed').sort((a, b) => b.id - a.id)
      setLastScan(completed[0] ?? items[0] ?? null)
    }).catch(() => {})
  }, [])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Security posture overview</h2>
          <p className="subtle">Track scan health and compliance drift at a glance.</p>
        </div>
        <Link to="/scans" className="muted-link">Scan history</Link>
      </div>

      <div className="panel-grid">
        <StatCard label="Total scans" value={stats?.total_scans} />
        <StatCard label="Open criticals" value={stats?.open_critical_findings} color="var(--danger)" />
        <StatCard label="Active findings" value={stats?.active_findings} color="var(--success)" />
      </div>

      {lastScan && (
        <div className="panel card-elevated fade-in">
          <h3 style={{ margin: '0 0 0.6rem' }}>Latest scan snapshot</h3>
          <div className="section-grid">
            <Info label="Scan ID" value={`#${lastScan.id}`} />
            <Info label="Status" value={lastScan.status} />
            <Info label="PR number" value={lastScan.pr_number ?? '-'} />
            <Info label="Created" value={lastScan.created_at} />
          </div>
          {lastScan.resolution_summary && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
              <span className="chip chip-danger">New: {lastScan.resolution_summary.new_findings}</span>
              <span className="chip chip-success">Resolved: {lastScan.resolution_summary.resolved_findings}</span>
              <span className="chip">Unchanged: {lastScan.resolution_summary.unchanged_findings}</span>
            </div>
          )}
          <Link to={`/scans/${lastScan.id}`} style={{ color: 'var(--accent)', display: 'inline-block', marginTop: 10 }}>View details</Link>
        </div>
      )}
    </div>
  )
}

function Info({ label, value }) {
  return (
    <div style={{ background: '#0d1527', border: '1px solid var(--border)', borderRadius: 10, padding: '0.55rem 0.65rem' }}>
      <div style={{ color: 'var(--text-subtle)', fontSize: '0.75rem', marginBottom: 2 }}>{label}</div>
      <div style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{value}</div>
    </div>
  )
}

function StatCard({ label, value, color }) {
  return (
    <div className="panel stat-card">
      <div className="stat-value" style={{ color: color || 'var(--text-primary)' }}>{value ?? '-'}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}
