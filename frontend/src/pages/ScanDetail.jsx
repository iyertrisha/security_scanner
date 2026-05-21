import { useEffect, useMemo, useState, Fragment } from 'react'
import { useParams, Link } from 'react-router-dom'
import { fetchScan, fetchOverrides, postOverride, proposeFix, fetchScanFixes, postGithubFixComment } from '../api'
import SeverityBadge from '../components/SeverityBadge'
import { 
  Target, 
  Shield, 
  Wrench, 
  CheckCircle, 
  AlertCircle, 
  XCircle,
  FileCode,
  ChevronDown,
  Copy,
  ExternalLink,
  Loader2
} from 'lucide-react'

export default function ScanDetail() {
  const { scanId } = useParams()
  const [scan, setScan] = useState(null)
  const [tab, setTab] = useState('all')
  const [sortCol, setSortCol] = useState('severity')
  const [sortAsc, setSortAsc] = useState(false)
  const [overrides, setOverrides] = useState([])
  const [overrideForm, setOverrideForm] = useState({ finding_type: '', resource_pattern: '*', justification: '' })

  const [fixBusy, setFixBusy] = useState({})
  const [fixCache, setFixCache] = useState({})
  const [fixList, setFixList] = useState([])
  const [expandedDiffs, setExpandedDiffs] = useState({})
  const [ghPostModal, setGhPostModal] = useState(null) // { proposalId, token, busy, error }

  useEffect(() => {
    fetchScan(scanId).then(setScan).catch(() => setScan(null))
    fetchScanFixes(scanId).then((d) => setFixList(d.items || [])).catch(() => setFixList([]))
    fetchOverrides().then((d) => setOverrides(d.items || [])).catch(() => {})
  }, [scanId])

  const refreshFixes = () => {
    fetchScanFixes(scanId).then((d) => setFixList(d.items || [])).catch(() => {})
  }

  const runSuggestFix = async (findingId) => {
    setFixBusy((b) => ({ ...b, [findingId]: true }))
    try {
      const r = await proposeFix(scanId, findingId)
      setFixCache((c) => ({ ...c, [findingId]: r }))
      refreshFixes()
    } catch (err) {
      setFixCache((c) => ({ ...c, [findingId]: { error: err.message || String(err) } }))
    } finally {
      setFixBusy((b) => ({ ...b, [findingId]: false }))
    }
  }

  const openGhPostModal = (proposalId) => {
    setGhPostModal({ proposalId, token: '', busy: false, error: '' })
  }

  const closeGhPostModal = () => {
    if (ghPostModal?.busy) return
    setGhPostModal(null)
  }

  const submitGhPost = async () => {
    if (!ghPostModal?.proposalId) return
    setGhPostModal((m) => ({ ...m, busy: true, error: '' }))
    try {
      const trimmed = (ghPostModal.token || '').trim()
      await postGithubFixComment(ghPostModal.proposalId, trimmed)
      refreshFixes()
      setGhPostModal(null)
    } catch (err) {
      setGhPostModal((m) => ({
        ...m,
        busy: false,
        error: err.message || String(err),
      }))
    }
  }

  const toggleDiff = (findingId) => {
    setExpandedDiffs((prev) => ({ ...prev, [findingId]: !prev[findingId] }))
  }

  const copyDiff = async (text) => {
    try {
      await navigator.clipboard.writeText(text)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const findings = useMemo(() => scan?.findings || [], [scan])

  const filtered = useMemo(() => {
    let list = findings
    if (tab === 'new') list = list.filter((f) => f.is_new)
    else if (tab === 'unchanged') list = list.filter((f) => !f.is_new)
    const sevRank = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 }
    list = [...list].sort((a, b) => {
      if (sortCol === 'severity') return (sevRank[b.severity] || 0) - (sevRank[a.severity] || 0)
      if (sortCol === 'type') return (a.finding_type || '').localeCompare(b.finding_type || '')
      if (sortCol === 'blast') return (b.blast_radius_count || 0) - (a.blast_radius_count || 0)
      return 0
    })
    if (sortAsc) list.reverse()
    return list
  }, [findings, tab, sortCol, sortAsc])

  const toggleSort = (col) => {
    if (sortCol === col) setSortAsc(!sortAsc)
    else { setSortCol(col); setSortAsc(false) }
  }

  const submitOverride = async () => {
    if (!overrideForm.finding_type) return
    try {
      await postOverride(overrideForm)
      const refreshed = await fetchOverrides()
      setOverrides(refreshed.items || [])
      setOverrideForm({ finding_type: '', resource_pattern: '*', justification: '' })
    } catch { /* ignore */ }
  }

  if (!scan) return <p style={{ color: '#94a3b8' }}>Loading scan #{scanId}...</p>

  return (
    <div className="page">
      <div className="panel card-elevated">
        <div className="page-header">
          <div>
            <h2 className="page-title">Scan #{scan.id}</h2>
            <p className="subtle">Status: {scan.status} · PR {scan.pr_number ?? '-'} · Commit {scan.commit_sha ?? '-'} · {scan.created_at}</p>
          </div>
          <Link to={`/scans/${scanId}/graph`} className="btn btn-ghost" style={{ textDecoration: 'none' }}>
            View topology graph
          </Link>
        </div>
        {fixList.length > 0 && (
          <p className="subtle" style={{ marginTop: 8 }}>
            Autofix proposals stored: {fixList.length}
          </p>
        )}
      </div>

      <div className="panel fade-in">
        <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
          {['all', 'new', 'unchanged'].map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`btn ${tab === t ? '' : 'btn-ghost'}`}>
              {t[0].toUpperCase() + t.slice(1)} ({t === 'all' ? findings.length : t === 'new' ? findings.filter((f) => f.is_new).length : findings.filter((f) => !f.is_new).length})
            </button>
          ))}
        </div>

        <div className="table-wrap">
          <table>
          <thead>
            <tr>
              <Th label="Finding type" col="type" sortCol={sortCol} sortAsc={sortAsc} onClick={toggleSort} />
              <Th label="Severity" col="severity" sortCol={sortCol} sortAsc={sortAsc} onClick={toggleSort} />
              <th>Location</th>
              <Th label="Blast radius" col="blast" sortCol={sortCol} sortAsc={sortAsc} onClick={toggleSort} />
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((f) => (
              <Fragment key={f.id}>
                <tr>
                <td>{f.finding_type}</td>
                <td><SeverityBadge severity={f.severity} /></td>
                <td>
                  {f.source_file != null && f.source_line != null ? (
                    f.github_url ? (
                      <a href={f.github_url} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)', fontSize: '0.85rem' }}>
                        {f.source_file}:{f.source_line}
                      </a>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>{f.source_file}:{f.source_line}</span>
                    )
                  ) : (
                    <span style={{ color: 'var(--text-subtle)', fontSize: '0.8rem' }}>-</span>
                  )}
                </td>
                <td>{f.blast_radius_count ?? 0}</td>
                <td>
                  {f.is_new ? <span className="chip chip-success">New</span> : <span className="chip">Unchanged</span>}
                  {f.overridden ? <span className="chip chip-warning" style={{ marginLeft: 6 }}>Overridden</span> : null}
                </td>
                <td>
                  <div className="action-buttons">
                    <Link
                      to={`/scans/${scanId}/graph`}
                      state={{
                        highlight: [
                          f.resource_id,
                          ...(Array.isArray(f.blast_radius_resources) ? f.blast_radius_resources : []),
                        ].filter(Boolean),
                        focusNode: f.resource_id || null,
                      }}
                      className="btn btn-ghost"
                    >
                      <Target />
                      Highlight blast
                    </Link>
                    <button 
                      type="button" 
                      onClick={() => setOverrideForm((p) => ({ ...p, finding_type: f.finding_type }))} 
                      className="btn btn-ghost"
                    >
                      <Shield />
                      Override
                    </button>
                    <button 
                      type="button" 
                      disabled={!!fixBusy[f.id]} 
                      onClick={() => runSuggestFix(f.id)} 
                      className="btn btn-warning"
                    >
                      {fixBusy[f.id] ? <Loader2 className="spinner" /> : <Wrench />}
                      {fixBusy[f.id] ? 'Processing...' : 'Suggest fix'}
                    </button>
                  </div>
                </td>
              </tr>
              {fixCache[f.id] && (
                <tr>
                  <td colSpan={6} style={{ padding: '0.75rem', verticalAlign: 'top' }}>
                    <div className="fix-preview-card">
                      {fixCache[f.id].error ? (
                        <div className="fix-error">
                          <XCircle />
                          <span>{fixCache[f.id].error}</span>
                        </div>
                      ) : (
                        <>
                          <div className="fix-preview-header">
                            <div className="fix-preview-status">
                              <div className={`status-badge ${fixCache[f.id].status === 'validated' ? 'validated' : fixCache[f.id].status === 'pending' ? 'pending' : 'error'}`}>
                                {fixCache[f.id].status === 'validated' ? (
                                  <>
                                    <CheckCircle />
                                    <span>Validated</span>
                                  </>
                                ) : fixCache[f.id].status === 'pending' ? (
                                  <>
                                    <AlertCircle />
                                    <span>Pending</span>
                                  </>
                                ) : (
                                  <>
                                    <XCircle />
                                    <span>Error</span>
                                  </>
                                )}
                              </div>
                              {fixCache[f.id].regression_detail && (
                                <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                                  {fixCache[f.id].regression_detail}
                                </span>
                              )}
                            </div>
                          </div>

                          {fixCache[f.id].validation_errors?.length > 0 && (
                            <div className="validation-errors">
                              <AlertCircle />
                              <span>{fixCache[f.id].validation_errors.join('; ')}</span>
                            </div>
                          )}

                          {fixCache[f.id].unified_diff_preview && (
                            <div className="diff-section">
                              <div 
                                className="diff-header" 
                                onClick={() => toggleDiff(f.id)}
                              >
                                <div className="diff-header-label">
                                  <FileCode />
                                  <span>Diff Preview</span>
                                  <span style={{ color: 'var(--text-subtle)', fontSize: '0.75rem' }}>
                                    ({fixCache[f.id].unified_diff_preview.split('\n').length} lines)
                                  </span>
                                </div>
                                <div className={`diff-toggle ${expandedDiffs[f.id] === false ? 'collapsed' : ''}`}>
                                  <ChevronDown />
                                </div>
                              </div>
                              {expandedDiffs[f.id] !== false && (
                                <pre className="diff-container">
                                  {fixCache[f.id].unified_diff_preview.split('\n').map((line, idx) => {
                                    if (line.startsWith('+') && !line.startsWith('+++')) {
                                      return <span key={idx} className="diff-line-add">{line}{'\n'}</span>
                                    } else if (line.startsWith('-') && !line.startsWith('---')) {
                                      return <span key={idx} className="diff-line-remove">{line}{'\n'}</span>
                                    } else {
                                      return <span key={idx} className="diff-line-context">{line}{'\n'}</span>
                                    }
                                  })}
                                </pre>
                              )}
                            </div>
                          )}

                          <div className="button-group">
                            {fixCache[f.id].unified_diff_preview && (
                              <button 
                                type="button" 
                                onClick={() => copyDiff(fixCache[f.id].unified_diff_preview)} 
                                className="btn btn-ghost"
                              >
                                <Copy />
                                Copy diff
                              </button>
                            )}
                            {fixCache[f.id].proposal_id && scan?.pr_number != null && (
                              <button 
                                type="button" 
                                onClick={() => openGhPostModal(fixCache[f.id].proposal_id)} 
                                className="btn"
                              >
                                <ExternalLink />
                                Post to GitHub PR
                              </button>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
            {filtered.length === 0 && <tr><td colSpan={6} style={{ textAlign: 'center', color: '#64748b' }}>No findings.</td></tr>}
          </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h3 style={{ margin: '0 0 0.75rem' }}>Overrides</h3>
        <div className="section-grid">
          <div>
            <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-muted)' }}>New override request</h4>
            <input placeholder="Finding type" value={overrideForm.finding_type} onChange={(e) => setOverrideForm((p) => ({ ...p, finding_type: e.target.value }))} />
            <input placeholder="Resource pattern" value={overrideForm.resource_pattern} onChange={(e) => setOverrideForm((p) => ({ ...p, resource_pattern: e.target.value }))} />
            <textarea placeholder="Justification" value={overrideForm.justification} onChange={(e) => setOverrideForm((p) => ({ ...p, justification: e.target.value }))} rows={2} />
            <button onClick={submitOverride} type="button" className="btn">Submit override</button>
          </div>
          <div>
            <h4 style={{ margin: '0 0 0.5rem', fontSize: '0.95rem', color: 'var(--text-muted)' }}>Active overrides</h4>
            {overrides.length === 0 ? (
              <p className="subtle">No active overrides.</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: '0.9rem' }}>{overrides.map((o) => <li key={o.id}>{o.finding_type} :: {o.resource_pattern}</li>)}</ul>
            )}
          </div>
        </div>
      </div>

      {ghPostModal && (
        <div className="modal-backdrop" onClick={closeGhPostModal} role="presentation">
          <div
            className="panel modal-card"
            role="dialog"
            aria-modal="true"
            aria-labelledby="gh-post-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="gh-post-title" style={{ marginTop: 0 }}>Post autofix to GitHub PR</h3>
            <p className="subtle" style={{ marginTop: 0 }}>
              Optional: paste a GitHub PAT to post as your account. Leave blank to use the server{' '}
              <code>GITHUB_TOKEN</code> from <code>.env</code>.
            </p>
            <label className="auth-label" htmlFor="gh-pat-input">GitHub PAT (optional)</label>
            <input
              id="gh-pat-input"
              type="password"
              autoComplete="off"
              placeholder="ghp_… or github_pat_…"
              value={ghPostModal.token}
              disabled={ghPostModal.busy}
              onChange={(e) => setGhPostModal((m) => ({ ...m, token: e.target.value, error: '' }))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !ghPostModal.busy) submitGhPost()
                if (e.key === 'Escape' && !ghPostModal.busy) closeGhPostModal()
              }}
            />
            {ghPostModal.error && (
              <div className="fix-error" style={{ marginTop: '0.75rem' }}>
                {ghPostModal.error}
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem', justifyContent: 'flex-end' }}>
              <button type="button" className="btn btn-ghost" disabled={ghPostModal.busy} onClick={closeGhPostModal}>
                Cancel
              </button>
              <button type="button" className="btn" disabled={ghPostModal.busy} onClick={submitGhPost}>
                {ghPostModal.busy ? 'Posting…' : 'Post comment'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function Th({ label, col, sortCol, sortAsc, onClick }) {
  const active = sortCol === col
  return (
    <th style={{ cursor: 'pointer', userSelect: 'none' }} onClick={() => onClick(col)}>
      {label} {active ? (sortAsc ? '▲' : '▼') : ''}
    </th>
  )
}
