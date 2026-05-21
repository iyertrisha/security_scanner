import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { fetchScans, fetchRepos } from '../api'

export default function ScanHistory() {
  const [scans, setScans] = useState([])
  const [repoById, setRepoById] = useState(() => new Map())

  useEffect(() => {
    Promise.all([fetchScans(), fetchRepos()])
      .then(([scansData, reposData]) => {
        setScans(scansData.items || [])
        const items = reposData.items || []
        const m = new Map()
        for (const r of items) {
          m.set(r.id, r.name)
        }
        setRepoById(m)
      })
      .catch(() => {
        setScans([])
        setRepoById(new Map())
      })
  }, [])

  const rows = useMemo(
    () =>
      scans.map((s) => ({
        ...s,
        repoName: repoById.get(s.repository_id) ?? '-',
        shortSha: s.commit_sha ? String(s.commit_sha).slice(0, 7) : '-',
      })),
    [scans, repoById],
  )

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Scan history</h2>
          <p className="subtle">Browse all pull-request scans and jump into findings fast.</p>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 10 }}>
        {rows.map((s) => (
          <div
            key={s.id}
            className="panel"
            style={{ transition: 'transform 0.2s ease' }}
          >
            <div className="page-header">
              <div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                  <strong>Scan #{s.id}</strong>
                  <span className={`chip ${s.status === 'completed' ? 'chip-success' : s.status === 'failed' ? 'chip-danger' : 'chip-warning'}`}>
                    {s.status}
                  </span>
                  <span className="chip">PR {s.pr_number ?? '-'}</span>
                </div>
                <p className="subtle" style={{ marginTop: 6 }}>
                  {s.repoName} · commit <code style={{ color: 'var(--text-muted)' }}>{s.shortSha}</code> · {s.created_at}
                </p>
              </div>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Link to={`/scans/${s.id}`} className="btn btn-ghost" style={{ textDecoration: 'none' }}>Findings</Link>
                {s.status === 'completed' && (
                  <Link to={`/scans/${s.id}/graph`} className="btn" style={{ textDecoration: 'none' }}>Graph</Link>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
              <span className="chip chip-danger">New: {s.resolution_summary?.new_findings ?? '-'}</span>
              <span className="chip chip-success">Resolved: {s.resolution_summary?.resolved_findings ?? '-'}</span>
              <span className="chip">Unchanged: {s.resolution_summary?.unchanged_findings ?? '-'}</span>
            </div>
          </div>
        ))}
      </div>

      {scans.length === 0 && (
        <div className="panel" style={{ textAlign: 'center', color: 'var(--text-subtle)' }}>
          No scans yet. Open or update a PR that changes <code>.tf</code>, <code>.yaml</code>, or <code>.yml</code> files.
          <div style={{ marginTop: 10 }}>
            <Link to="/run" style={{ color: 'var(--accent)' }}>Open PR scan guide</Link>
          </div>
        </div>
      )}

      <div className="panel table-wrap">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Repository</th>
              <th>Status</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 8).map((s) => (
              <tr key={`compact-${s.id}`}>
                <td>#{s.id}</td>
                <td>{s.repoName}</td>
                <td>{s.status}</td>
                <td>{s.created_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
