import { useEffect, useState, useMemo } from 'react'
import { useParams, useLocation, Link } from 'react-router-dom'
import { fetchGraph, fetchScan } from '../api'
import GraphView from '../components/GraphView'

export default function ScanGraph() {
  const { scanId } = useParams()
  const location = useLocation()
  const [graphData, setGraphData] = useState(null)
  const [scan, setScan] = useState(null)
  const [error, setError] = useState(null)
  const [highlighted, setHighlighted] = useState(location.state?.highlight || [])
  const [focusNode] = useState(location.state?.focusNode || null)

  useEffect(() => {
    fetchGraph(scanId)
      .then((d) => {
        const head = d?.head ?? d?.base
        setGraphData(head && typeof head === 'object' ? head : null)
        if (!head) setError('No graph data in response.')
      })
      .catch((err) => setError(err.message))

    fetchScan(scanId)
      .then(setScan)
      .catch(() => setScan(null))
  }, [scanId])

  const dangerousNodes = useMemo(() => {
    if (!scan?.findings) return []
    const dangerous = new Set()
    for (const finding of scan.findings) {
      if (finding.severity === 'CRITICAL' || finding.severity === 'HIGH') {
        if (finding.resource_id) dangerous.add(finding.resource_id)
        if (finding.blast_radius_resources) {
          for (const r of finding.blast_radius_resources) {
            if (typeof r === 'string') dangerous.add(r)
            else if (r?.id) dangerous.add(r.id)
          }
        }
      }
    }
    return Array.from(dangerous)
  }, [scan])

  const sourceByNode = useMemo(() => {
    const m = new Map()
    const findings = scan?.findings || []

    function alternateKeys(rid) {
      const s = String(rid)
      const keys = new Set([s])
      const prefixed = /^kubernetes_[a-z0-9]+_(.+)$/i.exec(s)
      if (prefixed?.[1]) keys.add(prefixed[1])
      return keys
    }

    function upsert(rid, payload) {
      for (const key of alternateKeys(rid)) {
        const prev = m.get(key)
        if (!prev) {
          m.set(key, { ...payload })
          continue
        }
        if (!prev.githubUrl && payload.githubUrl) {
          m.set(key, { ...prev, ...payload })
        }
      }
    }

    for (const f of findings) {
      const rid = f?.details?.resource_id || f?.resource_id
      if (!rid) continue
      const sourceFile = f?.source_file ?? f?.details?.source_file
      const sourceLine = f?.source_line ?? f?.details?.source_line
      const githubUrl = f?.github_url || null
      if (sourceFile != null && sourceLine != null) {
        upsert(String(rid), {
          sourceFile: String(sourceFile),
          sourceLine: Number(sourceLine),
          githubUrl,
        })
      }
    }
    return m
  }, [scan])

  const dangerousCount = dangerousNodes.length

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h2 className="page-title">Network topology</h2>
          <p className="subtle">Scan #{scanId}</p>
        </div>
        <Link to={`/scans/${scanId}`} style={{ color: 'var(--accent)' }}>Back to findings</Link>
      </div>

      <div className="panel">
        <div className="section-grid">
          <div>
            <p className="subtle">Nodes and risk snapshot</p>
            {graphData?.metadata && (
              <p style={{ margin: '4px 0 0' }}>
                Nodes: <strong>{graphData.metadata.node_count ?? 0}</strong> | Edges: <strong>{graphData.metadata.edge_count ?? 0}</strong>
              </p>
            )}
            {Number(graphData?.metadata?.edge_count ?? 0) === 0 && (
              <p className="subtle">Sparse graph detected: no inferred relationships in current data.</p>
            )}
          </div>
          <div>
            {dangerousCount > 0 && (
              <p style={{ margin: 0, color: '#fca5a5' }}>
                {dangerousCount} dangerous node{dangerousCount !== 1 ? 's' : ''} with CRITICAL/HIGH findings
              </p>
            )}
            {highlighted.length > 0 && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
                <span style={{ fontSize: '0.85rem', color: '#f87171' }}>Highlighting {highlighted.length} finding node(s)</span>
                <button onClick={() => setHighlighted([])} className="btn btn-ghost" style={{ fontSize: '0.8rem', padding: '2px 8px' }}>Clear</button>
              </div>
            )}
            <p className="subtle" style={{ marginTop: 8 }}>
              Click a node to open the details panel (top bar shows source links when NetGuard mapped this resource to a file).
              Drag/zoom inside the canvas as usual.
            </p>
          </div>
        </div>
      </div>

      {error && <p style={{ color: '#f87171' }}>{error}</p>}
      {graphData && (
        <div className="panel fade-in" style={{ padding: 0, overflow: 'visible' }}>
          <GraphView
            graphData={graphData}
            highlightedNodes={highlighted}
            dangerousNodes={dangerousNodes}
            sourceByNode={sourceByNode}
            findingsHref={`/scans/${scanId}`}
            initialSelectedNode={focusNode}
            fullPage
          />
        </div>
      )}
      {!graphData && !error && <p style={{ color: '#64748b' }}>Loading graph...</p>}
    </div>
  )
}
