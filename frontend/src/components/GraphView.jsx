import { useLayoutEffect, useMemo, useRef, useState, useCallback, useEffect } from 'react'
import { Link } from 'react-router-dom'
import * as d3 from 'd3'

function normalizeIds(ids) {
  if (!Array.isArray(ids)) return []
  return ids
    .map((x) => {
      if (typeof x === 'string') return x
      if (x != null && typeof x === 'object' && 'id' in x) return String(x.id)
      return x == null ? '' : String(x)
    })
    .filter(Boolean)
}

function nodeColor(nodeType) {
  switch (String(nodeType || '').toLowerCase()) {
    case 'internet':
      return '#ef4444'
    case 'security_group':
      return '#f59e0b'
    case 'lb':
      return '#22d3ee'
    case 'ec2_instance':
      return '#3b82f6'
    case 'subnet':
      return '#a78bfa'
    case 'vpc':
      return '#10b981'
    default:
      return '#64748b'
  }
}

function buildAdjacencyMap(edges) {
  const adj = new Map()
  for (const edge of edges) {
    const source = String(edge.source?.id ?? edge.source ?? '')
    const target = String(edge.target?.id ?? edge.target ?? '')
    if (!adj.has(source)) adj.set(source, new Set())
    if (!adj.has(target)) adj.set(target, new Set())
    adj.get(source).add(target)
    adj.get(target).add(source)
  }
  return adj
}

function getBlastRadius(nodeId, adjacencyMap, depth) {
  const visited = new Set([nodeId])
  let frontier = [nodeId]
  for (let d = 0; d < depth && frontier.length > 0; d++) {
    const nextFrontier = []
    for (const n of frontier) {
      const neighbors = adjacencyMap.get(n) || new Set()
      for (const neighbor of neighbors) {
        if (!visited.has(neighbor)) {
          visited.add(neighbor)
          nextFrontier.push(neighbor)
        }
      }
    }
    frontier = nextFrontier
  }
  return visited
}

const LAYOUT_OPTIONS = [
  { id: 'force', label: 'Force-Directed' },
  { id: 'radial', label: 'Radial' },
  { id: 'hierarchical', label: 'Hierarchical' },
  { id: 'circular', label: 'Circular' },
]

export default function GraphView({
  graphData,
  highlightedNodes = [],
  fullPage = false,
  onNodeSelect,
  dangerousNodes = [],
  sourceByNode = new Map(),
  findingsHref = null,
  initialSelectedNode = null,
}) {
  const ref = useRef(null)
  const simulationRef = useRef(null)
  const highlightSet = useMemo(() => new Set(normalizeIds(highlightedNodes)), [highlightedNodes])
  const dangerousSet = useMemo(() => new Set(normalizeIds(dangerousNodes)), [dangerousNodes])
  const [selectedNode, setSelectedNode] = useState(null)
  const [blastRadius, setBlastRadius] = useState(1)
  const [blastNodes, setBlastNodes] = useState(new Set())
  const [layout, setLayout] = useState('force')
  const [nodeInfo, setNodeInfo] = useState(null)

  useEffect(() => {
    if (initialSelectedNode) setSelectedNode(String(initialSelectedNode))
  }, [initialSelectedNode])

  const adjacencyMap = useMemo(() => {
    if (!graphData) return new Map()
    return buildAdjacencyMap(graphData.edges || [])
  }, [graphData])

  const handleNodeClick = useCallback((nodeId) => {
    setSelectedNode(nodeId)
    if (onNodeSelect) onNodeSelect(nodeId)
  }, [onNodeSelect])

  useEffect(() => {
    if (selectedNode && adjacencyMap.size > 0) {
      const radius = getBlastRadius(selectedNode, adjacencyMap, blastRadius)
      setBlastNodes(radius)
      const connections = adjacencyMap.get(selectedNode) || new Set()
      const isDangerous = dangerousSet.has(selectedNode)
      const source = sourceByNode instanceof Map ? sourceByNode.get(selectedNode) : null
      setNodeInfo({
        id: selectedNode,
        directConnections: Array.from(connections),
        blastRadiusCount: radius.size - 1,
        isDangerous,
        sourceFile: source?.sourceFile || null,
        sourceLine: source?.sourceLine || null,
        githubUrl: source?.githubUrl || null,
        totalNodes: graphData?.nodes?.length || 0,
        totalEdges: graphData?.edges?.length || 0,
      })
    } else {
      setBlastNodes(new Set())
      setNodeInfo(null)
    }
  }, [selectedNode, blastRadius, adjacencyMap, dangerousSet, graphData, sourceByNode])

  useLayoutEffect(() => {
    if (!graphData || !ref.current) return undefined

    const width = fullPage ? 1200 : 720
    const height = fullPage ? 700 : 400
    const svg = d3.select(ref.current)
    svg.selectAll('*').remove()
    svg.attr('viewBox', `0 0 ${width} ${height}`).attr('width', '100%').attr('height', '100%')

    const rawNodes = graphData.nodes || []
    const rawEdges = graphData.edges || []
    if (rawNodes.length === 0) {
      svg.append('text').attr('x', 24).attr('y', 32).attr('fill', '#94a3b8').text('No nodes in this graph.')
      return undefined
    }

    const nodes = rawNodes.map((n) => ({ ...n }))
    const links = rawEdges.map((e) => ({ ...e }))
    const degreeByNode = new Map()
    for (const edge of links) {
      const source = String(edge.source ?? '')
      const target = String(edge.target ?? '')
      degreeByNode.set(source, (degreeByNode.get(source) || 0) + 1)
      degreeByNode.set(target, (degreeByNode.get(target) || 0) + 1)
    }

    if (layout === 'circular') {
      const angleStep = (2 * Math.PI) / nodes.length
      const radius = Math.min(width, height) / 2.5
      nodes.forEach((n, i) => {
        n.x = width / 2 + radius * Math.cos(i * angleStep)
        n.y = height / 2 + radius * Math.sin(i * angleStep)
        n.fx = n.x
        n.fy = n.y
      })
    } else if (layout === 'radial') {
      const sortedNodes = [...nodes].sort((a, b) => (degreeByNode.get(String(b.id)) || 0) - (degreeByNode.get(String(a.id)) || 0))
      const layers = []
      let remaining = sortedNodes.slice()
      while (remaining.length > 0) {
        const layerSize = Math.max(1, Math.ceil(remaining.length / 3))
        layers.push(remaining.slice(0, layerSize))
        remaining = remaining.slice(layerSize)
      }
      layers.forEach((layer, li) => {
        const radius = (li + 1) * (Math.min(width, height) / (layers.length + 1) / 2)
        const angleStep = (2 * Math.PI) / layer.length
        layer.forEach((n, i) => {
          n.x = width / 2 + radius * Math.cos(i * angleStep)
          n.y = height / 2 + radius * Math.sin(i * angleStep)
        })
      })
    } else if (layout === 'hierarchical') {
      const levels = new Map()
      const visited = new Set()
      const queue = []
      const roots = nodes.filter(n => {
        const id = String(n.id)
        return !links.some(l => String(l.target) === id || String(l.target?.id) === id)
      })
      if (roots.length === 0 && nodes.length > 0) roots.push(nodes[0])
      roots.forEach(r => { levels.set(String(r.id), 0); visited.add(String(r.id)); queue.push(r) })
      while (queue.length > 0) {
        const current = queue.shift()
        const currentLevel = levels.get(String(current.id))
        const neighbors = adjacencyMap.get(String(current.id)) || new Set()
        for (const neighborId of neighbors) {
          if (!visited.has(neighborId)) {
            visited.add(neighborId)
            levels.set(neighborId, currentLevel + 1)
            const neighborNode = nodes.find(n => String(n.id) === neighborId)
            if (neighborNode) queue.push(neighborNode)
          }
        }
      }
      const maxLevel = Math.max(...Array.from(levels.values()), 0)
      const levelGroups = Array.from({ length: maxLevel + 1 }, () => [])
      nodes.forEach(n => {
        const level = levels.get(String(n.id)) ?? 0
        levelGroups[level].push(n)
      })
      levelGroups.forEach((group, level) => {
        const y = 60 + level * ((height - 100) / Math.max(maxLevel, 1))
        const xStep = width / (group.length + 1)
        group.forEach((n, i) => {
          n.x = xStep * (i + 1)
          n.y = y
        })
      })
    }

    let simulation
    try {
      simulation = d3
        .forceSimulation(nodes)
        .force('link', d3.forceLink(links).id((d) => d.id).distance(fullPage ? 95 : 72))
        .force('charge', d3.forceManyBody().strength(fullPage ? -320 : -220))
        .force('center', d3.forceCenter(width / 2, height / 2))
        .force('collision', d3.forceCollide().radius(fullPage ? 20 : 15))

      if (layout === 'circular') {
        simulation.force('link', null).force('charge', null).force('center', null).force('collision', null)
      } else if (layout === 'hierarchical') {
        simulation.force('charge', d3.forceManyBody().strength(-50))
        simulation.force('y', d3.forceY().strength(0.1))
      }
      simulationRef.current = simulation
    } catch {
      svg.append('text').attr('x', 24).attr('y', 32).attr('fill', '#f87171').text('Could not build graph layout.')
      return undefined
    }

    const defs = svg.append('defs')
    defs
      .append('marker')
      .attr('id', 'edge-arrow')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', fullPage ? 18 : 13)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#475569')

    const graphLayer = svg.append('g')
    const link = graphLayer.append('g').selectAll('line').data(links).join('line')
      .attr('stroke', '#475569')
      .attr('stroke-width', 1.2)
      .attr('marker-end', links.length > 0 ? 'url(#edge-arrow)' : null)
      .attr('opacity', 0.8)
    link.append('title').text((d) => `${d.relationship || 'connects'}${d.port ? ` :${d.port}` : ''}`)

    const nodeGroup = graphLayer.append('g').selectAll('circle').data(nodes).join('circle')
      .attr('r', (d) => {
        const id = String(d.id)
        if (selectedNode === id) return fullPage ? 16 : 13
        if (dangerousSet.has(id)) return fullPage ? 14 : 11
        if (blastNodes.has(id)) return fullPage ? 13 : 10
        return fullPage ? 11 : 8
      })
      .attr('fill', (d) => {
        const id = String(d.id)
        if (selectedNode === id) return '#22d3ee'
        if (dangerousSet.has(id)) return '#dc2626'
        if (blastNodes.has(id)) return '#f59e0b'
        if (highlightSet.has(id)) return '#ef4444'
        return nodeColor(d.type)
      })
      .attr('stroke', (d) => {
        const id = String(d.id)
        if (selectedNode === id) return '#0ea5e9'
        if (dangerousSet.has(id)) return '#fca5a5'
        return '#0f172a'
      })
      .attr('stroke-width', (d) => {
        const id = String(d.id)
        if (selectedNode === id) return 3
        if (dangerousSet.has(id)) return 2.5
        return 1.5
      })
      .attr('opacity', (d) => (degreeByNode.get(String(d.id)) ? 1 : 0.45))
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        handleNodeClick(String(d.id))
      })

    nodeGroup.append('title').text((d) => {
      const id = String(d.id)
      const danger = dangerousSet.has(id) ? '\n⚠️ DANGEROUS NODE' : ''
      const src = sourceByNode instanceof Map ? sourceByNode.get(id) : null
      const srcHint =
        src?.sourceFile != null && src?.sourceLine != null
          ? `\nSource: ${src.sourceFile}:${src.sourceLine}${src.githubUrl ? ' (GitHub link in panel after click)' : ''}`
          : '\nTip: Click node — source links appear in the bar above the graph when available.'
      return `${d.id}\nType: ${d.type || 'unknown'}${danger}${srcHint}\nClick for blast radius & connections`
    })

    const label = graphLayer.append('g').selectAll('text').data(nodes).join('text')
      .text((d) => String(d.id || '').replace(/^aws_/, '').replace(/^kubernetes_/, ''))
      .attr('font-size', fullPage ? 11 : 8)
      .attr('fill', '#cbd5e1')
      .attr('pointer-events', 'none')

    svg.on('click', () => {
      setSelectedNode(null)
    })

    const drag = d3
      .drag()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.2).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        if (layout !== 'circular') {
          d.fx = null
          d.fy = null
        }
      })

    nodeGroup.call(drag)

    const zoom = d3
      .zoom()
      .scaleExtent([0.25, 3])
      .on('zoom', (event) => {
        graphLayer.attr('transform', event.transform)
      })
    svg.call(zoom)

    simulation.on('tick', () => {
      link.attr('x1', (d) => d.source.x).attr('y1', (d) => d.source.y).attr('x2', (d) => d.target.x).attr('y2', (d) => d.target.y)
      nodeGroup.attr('cx', (d) => d.x).attr('cy', (d) => d.y)
      label.attr('x', (d) => d.x + (fullPage ? 15 : 10)).attr('y', (d) => d.y + 4)
    })

    simulation.alpha(1).restart()
    return () => simulation.stop()
  }, [
    graphData,
    highlightSet,
    fullPage,
    layout,
    selectedNode,
    blastNodes,
    handleNodeClick,
    dangerousSet,
    adjacencyMap,
    sourceByNode,
  ])

  const controlsStyle = {
    display: 'flex',
    gap: '16px',
    alignItems: 'center',
    padding: '12px 16px',
    background: '#0f172a',
    borderBottom: '1px solid #1e293b',
    flexWrap: 'wrap',
  }

  const selectStyle = {
    padding: '6px 12px',
    background: '#1e293b',
    color: '#e2e8f0',
    border: '1px solid #334155',
    borderRadius: '6px',
    fontSize: '0.9rem',
    cursor: 'pointer',
  }

  const labelStyle = {
    color: '#94a3b8',
    fontSize: '0.85rem',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  }

  const infoPanelStyle = {
    position: 'absolute',
    top: '60px',
    right: '16px',
    background: '#1e293b',
    border: '1px solid #334155',
    borderRadius: '8px',
    padding: '12px 16px',
    maxWidth: '280px',
    zIndex: 10,
  }

  const legendStyle = {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '0.75rem',
    color: '#94a3b8',
  }

  const legendDotStyle = (color, border) => ({
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    background: color,
    border: border ? `2px solid ${border}` : 'none',
  })

  return (
    <div style={{ position: 'relative' }}>
      <div style={controlsStyle}>
        <span style={{ color: '#64748b', fontSize: '0.78rem', maxWidth: 260, lineHeight: 1.35 }}>
          Hover shows basics; click a node for blast radius and file links (GitHub opens when PR/commit metadata exists).
        </span>
        <label style={labelStyle}>
          Layout:
          <select value={layout} onChange={(e) => setLayout(e.target.value)} style={selectStyle}>
            {LAYOUT_OPTIONS.map(opt => (
              <option key={opt.id} value={opt.id}>{opt.label}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          Blast Radius:
          <select value={blastRadius} onChange={(e) => setBlastRadius(Number(e.target.value))} style={selectStyle}>
            {[1, 2, 3, 4, 5].map(n => (
              <option key={n} value={n}>{n} hop{n > 1 ? 's' : ''}</option>
            ))}
          </select>
        </label>
        {selectedNode && (
          <button
            type="button"
            onClick={() => setSelectedNode(null)}
            style={{ ...selectStyle, background: '#334155', cursor: 'pointer' }}
          >
            Clear Selection
          </button>
        )}
        {nodeInfo?.id === selectedNode && nodeInfo.githubUrl && (
          <a
            href={nodeInfo.githubUrl}
            target="_blank"
            rel="noreferrer"
            style={{
              ...selectStyle,
              background: '#0b3b63',
              color: '#e0f2fe',
              textDecoration: 'none',
              fontWeight: 600,
            }}
          >
            View source file →
          </a>
        )}
        {nodeInfo?.id === selectedNode && nodeInfo.sourceFile != null && nodeInfo.sourceLine != null && !nodeInfo.githubUrl && (
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard.writeText(`${nodeInfo.sourceFile}:${nodeInfo.sourceLine}`)
            }}
            style={{ ...selectStyle, background: '#1e293b', cursor: 'pointer' }}
          >
            Copy {nodeInfo.sourceFile}:{nodeInfo.sourceLine}
          </button>
        )}
        {selectedNode && nodeInfo?.id === selectedNode && !(nodeInfo.sourceFile != null && nodeInfo.sourceLine != null) && findingsHref && (
          <Link
            to={findingsHref}
            style={{
              ...selectStyle,
              background: '#312e81',
              color: '#e0e7ff',
              textDecoration: 'none',
            }}
          >
            Find code via findings table
          </Link>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <span style={legendStyle}><span style={legendDotStyle('#dc2626', '#fca5a5')} /> Dangerous</span>
          <span style={legendStyle}><span style={legendDotStyle('#22d3ee', '#0ea5e9')} /> Selected</span>
          <span style={legendStyle}><span style={legendDotStyle('#f59e0b')} /> Blast Radius</span>
        </div>
      </div>
      <div style={{ position: 'relative' }}>
        <svg ref={ref} style={{ width: '100%', height: fullPage ? 'calc(100vh - 180px)' : '400px', background: '#020617', borderRadius: '0 0 8px 8px', border: '1px solid #1e293b', borderTop: 'none' }} />
        {nodeInfo && nodeInfo.id === selectedNode && (
          <div style={infoPanelStyle}>
            <h4 style={{ margin: '0 0 8px', color: nodeInfo.isDangerous ? '#dc2626' : '#22d3ee', fontSize: '0.95rem' }}>
              {nodeInfo.isDangerous && '⚠️ '}{nodeInfo.id}
            </h4>
            {nodeInfo.isDangerous && (
              <p style={{ margin: '0 0 8px', padding: '4px 8px', background: '#7f1d1d', borderRadius: '4px', color: '#fca5a5', fontSize: '0.8rem' }}>
                This node has security findings
              </p>
            )}
            <p style={{ margin: '0 0 8px', color: '#94a3b8', fontSize: '0.85rem' }}>
              Blast radius ({blastRadius} hop{blastRadius > 1 ? 's' : ''}): <strong style={{ color: '#f59e0b' }}>{nodeInfo.blastRadiusCount}</strong> of {nodeInfo.totalNodes - 1} node{nodeInfo.totalNodes !== 2 ? 's' : ''}
            </p>
            <p style={{ margin: '0 0 8px', color: '#64748b', fontSize: '0.75rem' }}>
              Graph: {nodeInfo.totalNodes} nodes, {nodeInfo.totalEdges} edges
            </p>
            <div style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>
              {nodeInfo.sourceFile && nodeInfo.sourceLine != null && (
                <div style={{ marginBottom: 8 }}>
                  <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginBottom: 4 }}>
                    IaC source: {nodeInfo.sourceFile}:{nodeInfo.sourceLine}
                  </div>
                  {nodeInfo.githubUrl ? (
                    <a
                      href={nodeInfo.githubUrl}
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        display: 'inline-block',
                        padding: '4px 8px',
                        background: '#0b3b63',
                        color: '#e0f2fe',
                        border: '1px solid #334155',
                        borderRadius: 4,
                        fontSize: '0.78rem',
                        textDecoration: 'none',
                        fontWeight: 600,
                      }}
                    >
                      Open file on GitHub
                    </a>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        const text = `${nodeInfo.sourceFile}:${nodeInfo.sourceLine}`
                        void navigator.clipboard.writeText(text)
                      }}
                      style={{
                        padding: '4px 8px',
                        background: '#1e293b',
                        color: '#e2e8f0',
                        border: '1px solid #334155',
                        borderRadius: 4,
                        fontSize: '0.78rem',
                        cursor: 'pointer',
                      }}
                    >
                      Copy path for IDE search
                    </button>
                  )}
                </div>
              )}
              {!(nodeInfo.sourceFile && nodeInfo.sourceLine != null) && findingsHref && (
                <p style={{ margin: '0 0 10px', fontSize: '0.78rem', color: '#94a3b8' }}>
                  No file mapping for this graph node from scan findings.
                  {' '}
                  <Link to={findingsHref} style={{ color: '#38bdf8' }}>Open findings</Link>
                  {' '}to jump to GitHub/file links per finding.
                </p>
              )}
              <strong>Direct connections ({nodeInfo.directConnections.length}):</strong>
              {nodeInfo.directConnections.length === 0 ? (
                <p style={{ margin: '4px 0 0', color: '#64748b' }}>No direct connections</p>
              ) : (
                <ul style={{ margin: '4px 0 0', paddingLeft: '16px', maxHeight: '150px', overflowY: 'auto' }}>
                  {nodeInfo.directConnections.map(conn => (
                    <li key={conn} style={{ marginBottom: '2px' }}>
                      <span
                        style={{ color: dangerousSet.has(conn) ? '#dc2626' : '#0ea5e9', cursor: 'pointer' }}
                        onClick={() => handleNodeClick(conn)}
                      >
                        {dangerousSet.has(conn) && '⚠️ '}{conn.replace(/^aws_/, '').replace(/^kubernetes_/, '')}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
