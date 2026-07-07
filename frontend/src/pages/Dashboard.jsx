import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  GitPullRequest,
  Radar,
  ScanSearch,
  Shield,
  ShieldAlert,
  TrendingUp,
} from 'lucide-react'
import { fetchStats, fetchScans, fetchRepos, fetchScan } from '../api'
import SeverityBadge from '../components/SeverityBadge'
import {
  ComplianceBars,
  ScanActivityChart,
  SecurityScoreRing,
  SeverityDonut,
} from '../components/DashboardCharts'

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

function computeSecurityScore(severityCounts) {
  const weights = { CRITICAL: 18, HIGH: 10, MEDIUM: 4, LOW: 1 }
  let penalty = 0
  for (const [sev, count] of Object.entries(severityCounts)) {
    penalty += (weights[sev] || 1) * count
  }
  return Math.max(0, Math.min(100, 100 - penalty))
}

function formatDate(raw) {
  if (!raw) return '—'
  try {
    return new Date(raw).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return String(raw)
  }
}

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [scans, setScans] = useState([])
  const [repos, setRepos] = useState([])
  const [latestDetail, setLatestDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [statsData, scansData, reposData] = await Promise.all([
          fetchStats(),
          fetchScans(),
          fetchRepos(),
        ])
        if (cancelled) return
        setStats(statsData)
        const items = scansData.items || []
        setScans(items)
        setRepos(reposData.items || [])

        const completed = items
          .filter((s) => s.status === 'completed')
          .sort((a, b) => b.id - a.id)
        const latest = completed[0] ?? items[0]
        if (latest?.id) {
          const detail = await fetchScan(latest.id)
          if (!cancelled) setLatestDetail(detail)
        }
      } catch {
        if (!cancelled) {
          setStats(null)
          setScans([])
          setRepos([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const severityCounts = useMemo(() => {
    const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 }
    for (const f of latestDetail?.findings || []) {
      const sev = (f.severity || 'LOW').toUpperCase()
      if (counts[sev] != null) counts[sev] += 1
    }
    return counts
  }, [latestDetail])

  const securityScore = useMemo(() => computeSecurityScore(severityCounts), [severityCounts])

  const topFindings = useMemo(() => {
    const rank = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 }
    return (latestDetail?.findings || [])
      .slice()
      .sort((a, b) => (rank[a.severity] ?? 9) - (rank[b.severity] ?? 9))
      .slice(0, 5)
  }, [latestDetail])

  const lastScan = useMemo(() => {
    const completed = scans.filter((s) => s.status === 'completed').sort((a, b) => b.id - a.id)
    return completed[0] ?? scans[0] ?? null
  }, [scans])

  const repoName = useMemo(() => {
    if (!lastScan) return null
    const repo = repos.find((r) => r.id === lastScan.repository_id)
    return repo?.name ?? `repo #${lastScan.repository_id}`
  }, [lastScan, repos])

  const completedScans = scans.filter((s) => s.status === 'completed').length
  const failedScans = scans.filter((s) => s.status === 'failed').length

  return (
    <div className="page dashboard-page">
      <section className="dash-hero panel card-elevated">
        <div className="dash-hero-content">
          <div className="dash-hero-badge">
            <Radar size={14} />
            Live security posture
          </div>
          <h2 className="dash-hero-title">Security Command Center</h2>
          <p className="dash-hero-sub">
            Monitor IaC risk across pull requests, track severity trends, and jump into findings in one place.
          </p>
          <div className="dash-hero-actions">
            <Link to="/scans" className="btn">
              <ScanSearch size={15} />
              View all scans
            </Link>
            <Link to="/run" className="btn btn-ghost">
              <GitPullRequest size={15} />
              PR scan guide
            </Link>
          </div>
        </div>
        <div className="dash-hero-score">
          <SecurityScoreRing score={securityScore} size={132} />
          <p className="dash-score-caption">
            Based on latest scan severity mix
          </p>
        </div>
      </section>

      <div className="dash-kpi-grid">
        <KpiCard
          icon={Shield}
          label="Total scans"
          value={stats?.total_scans}
          hint={`${completedScans} completed`}
          accent="cyan"
        />
        <KpiCard
          icon={ShieldAlert}
          label="Open criticals"
          value={stats?.open_critical_findings}
          hint="Unresolved CRITICAL"
          accent="red"
        />
        <KpiCard
          icon={AlertTriangle}
          label="Active findings"
          value={stats?.active_findings}
          hint="Latest completed scan"
          accent="amber"
        />
        <KpiCard
          icon={Activity}
          label="Repositories"
          value={repos.length}
          hint={`${failedScans} failed scans`}
          accent="green"
        />
      </div>

      <div className="dash-charts-row">
        <div className="panel dash-chart-panel card-elevated">
          <div className="dash-panel-head">
            <div>
              <h3>Severity breakdown</h3>
              <p className="subtle">Distribution from the most recent scan</p>
            </div>
            {lastScan && (
              <Link to={`/scans/${lastScan.id}`} className="dash-link">
                Scan #{lastScan.id} <ArrowRight size={14} />
              </Link>
            )}
          </div>
          <div className="dash-donut-layout">
            <SeverityDonut data={severityCounts} size={210} />
            <ul className="dash-legend">
              {SEVERITY_ORDER.map((sev) => (
                <li key={sev}>
                  <span className={`dash-legend-dot sev-${sev.toLowerCase()}`} />
                  <span>{sev}</span>
                  <strong>{severityCounts[sev] ?? 0}</strong>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="panel dash-chart-panel card-elevated">
          <div className="dash-panel-head">
            <div>
              <h3>Compliance posture</h3>
              <p className="subtle">Framework control failures across all findings</p>
            </div>
          </div>
          <ComplianceBars data={stats?.compliance_posture} />
        </div>
      </div>

      <div className="panel dash-chart-panel card-elevated dash-activity-panel">
        <div className="dash-panel-head">
          <div>
            <h3>Scan activity</h3>
            <p className="subtle">New vs resolved findings per recent scan</p>
          </div>
          <div className="dash-activity-legend">
            <span><i className="dot dot-new" /> New</span>
            <span><i className="dot dot-resolved" /> Resolved</span>
          </div>
        </div>
        <ScanActivityChart scans={scans} />
      </div>

      <div className="dash-bottom-row">
        {lastScan && (
          <div className="panel dash-snapshot card-elevated">
            <div className="dash-panel-head">
              <div>
                <h3>Latest scan snapshot</h3>
                <p className="subtle">{repoName} · PR #{lastScan.pr_number ?? '—'}</p>
              </div>
              <span className={`chip ${lastScan.status === 'completed' ? 'chip-success' : lastScan.status === 'failed' ? 'chip-danger' : 'chip-warning'}`}>
                {lastScan.status}
              </span>
            </div>
            <div className="dash-snapshot-grid">
              <SnapshotTile label="Scan ID" value={`#${lastScan.id}`} />
              <SnapshotTile label="Created" value={formatDate(lastScan.created_at)} />
              <SnapshotTile label="New findings" value={lastScan.resolution_summary?.new_findings ?? '—'} tone="danger" />
              <SnapshotTile label="Resolved" value={lastScan.resolution_summary?.resolved_findings ?? '—'} tone="success" />
            </div>
            <div className="dash-snapshot-actions">
              <Link to={`/scans/${lastScan.id}`} className="btn">
                View findings
              </Link>
              {lastScan.status === 'completed' && (
                <Link to={`/scans/${lastScan.id}/graph`} className="btn btn-ghost">
                  <TrendingUp size={14} />
                  Topology graph
                </Link>
              )}
            </div>
          </div>
        )}

        <div className="panel dash-findings-panel card-elevated">
          <div className="dash-panel-head">
            <div>
              <h3>Top findings</h3>
              <p className="subtle">Highest severity items from latest scan</p>
            </div>
          </div>
          {topFindings.length === 0 ? (
            <p className="chart-empty">Run a PR scan to populate findings.</p>
          ) : (
            <ul className="dash-findings-list">
              {topFindings.map((f) => (
                <li key={f.id}>
                  <div className="dash-finding-main">
                    <SeverityBadge severity={f.severity} />
                    <span className="dash-finding-type">{f.finding_type}</span>
                  </div>
                  {f.source_file && (
                    <span className="dash-finding-file">
                      {f.source_file}
                      {f.source_line ? `:${f.source_line}` : ''}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {lastScan && (
            <Link to={`/scans/${lastScan.id}`} className="dash-link dash-link-block">
              See all findings <ArrowRight size={14} />
            </Link>
          )}
        </div>
      </div>

      {loading && <p className="dash-loading subtle">Refreshing dashboard…</p>}
    </div>
  )
}

function KpiCard({ icon: Icon, label, value, hint, accent }) {
  return (
    <div className={`panel dash-kpi dash-kpi-${accent}`}>
      <div className="dash-kpi-icon">
        <Icon size={20} />
      </div>
      <div className="dash-kpi-body">
        <div className="dash-kpi-value">{value ?? '—'}</div>
        <div className="dash-kpi-label">{label}</div>
        {hint && <div className="dash-kpi-hint">{hint}</div>}
      </div>
    </div>
  )
}

function SnapshotTile({ label, value, tone }) {
  return (
    <div className={`dash-snapshot-tile ${tone ? `tone-${tone}` : ''}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
