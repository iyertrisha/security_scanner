import { useLayoutEffect, useRef } from 'react'
import * as d3 from 'd3'

const SEVERITY_COLORS = {
  CRITICAL: '#f87171',
  HIGH: '#fb923c',
  MEDIUM: '#fbbf24',
  LOW: '#38bdf8',
}

export function SeverityDonut({ data, size = 200 }) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (!ref.current) return
    const el = ref.current
    el.innerHTML = ''

    const entries = Object.entries(data || {}).filter(([, v]) => v > 0)
    const total = entries.reduce((s, [, v]) => s + v, 0)
    if (total === 0) {
      el.innerHTML = '<p class="chart-empty">No findings yet</p>'
      return
    }

    const radius = size / 2
    const inner = radius * 0.58
    const svg = d3
      .select(el)
      .append('svg')
      .attr('width', size)
      .attr('height', size)
      .attr('viewBox', `0 0 ${size} ${size}`)

    const g = svg.append('g').attr('transform', `translate(${radius},${radius})`)
    const pie = d3.pie().value((d) => d[1]).sort(null)
    const arc = d3.arc().innerRadius(inner).outerRadius(radius - 6).cornerRadius(4)

    g.selectAll('path')
      .data(pie(entries))
      .join('path')
      .attr('fill', (d) => SEVERITY_COLORS[d.data[0]] || '#64748b')
      .attr('d', arc)
      .attr('opacity', 0.92)

    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '-0.15em')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '1.65rem')
      .attr('font-weight', 700)
      .text(total)

    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '1.1em')
      .attr('fill', '#94a3b8')
      .attr('font-size', '0.7rem')
      .text('findings')
  }, [data, size])

  return <div className="chart-wrap" ref={ref} />
}

export function ComplianceBars({ data }) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (!ref.current) return
    const el = ref.current
    el.innerHTML = ''

    const items = Object.entries(data || {})
      .map(([key, val]) => ({ key, failing: val?.failing ?? 0, passing: val?.passing ?? 0 }))
      .filter((d) => d.failing > 0 || d.passing > 0)
      .sort((a, b) => b.failing - a.failing)

    if (!items.length) {
      el.innerHTML = '<p class="chart-empty">No compliance data yet</p>'
      return
    }

    const width = el.clientWidth || 360
    const rowH = 28
    const height = items.length * rowH + 16
    const labelW = 108
    const barW = width - labelW - 48

    const svg = d3.select(el).append('svg').attr('width', width).attr('height', height)
    const max = d3.max(items, (d) => d.failing + d.passing) || 1

    items.forEach((item, i) => {
      const y = 8 + i * rowH
      const total = item.failing + item.passing
      const failW = (item.failing / max) * barW
      const passW = (item.passing / max) * barW

      svg
        .append('text')
        .attr('x', 0)
        .attr('y', y + 16)
        .attr('fill', '#94a3b8')
        .attr('font-size', '0.68rem')
        .attr('font-weight', 600)
        .text(item.key.replace(/_/g, ' '))

      const barG = svg.append('g').attr('transform', `translate(${labelW},${y + 4})`)
      if (item.failing > 0) {
        barG
          .append('rect')
          .attr('width', failW)
          .attr('height', 14)
          .attr('rx', 4)
          .attr('fill', '#f87171')
      }
      if (item.passing > 0) {
        barG
          .append('rect')
          .attr('x', failW + 2)
          .attr('width', passW)
          .attr('height', 14)
          .attr('rx', 4)
          .attr('fill', '#4ade80')
          .attr('opacity', 0.75)
      }

      svg
        .append('text')
        .attr('x', labelW + barW + 8)
        .attr('y', y + 16)
        .attr('fill', '#e2e8f0')
        .attr('font-size', '0.72rem')
        .attr('font-weight', 600)
        .text(total)
    })
  }, [data])

  return <div className="chart-wrap chart-wrap-wide" ref={ref} />
}

export function ScanActivityChart({ scans }) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (!ref.current) return
    const el = ref.current
    el.innerHTML = ''

    const items = (scans || [])
      .slice()
      .sort((a, b) => a.id - b.id)
      .slice(-8)
      .map((s) => ({
        label: `#${s.id}`,
        new: s.resolution_summary?.new_findings ?? 0,
        resolved: s.resolution_summary?.resolved_findings ?? 0,
      }))

    if (!items.length) {
      el.innerHTML = '<p class="chart-empty">No scan history yet</p>'
      return
    }

    const width = el.clientWidth || 520
    const height = 180
    const margin = { top: 16, right: 12, bottom: 28, left: 36 }
    const innerW = width - margin.left - margin.right
    const innerH = height - margin.top - margin.bottom

    const svg = d3
      .select(el)
      .append('svg')
      .attr('width', width)
      .attr('height', height)

    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

    const x = d3
      .scaleBand()
      .domain(items.map((d) => d.label))
      .range([0, innerW])
      .padding(0.28)

    const maxY = d3.max(items, (d) => d.new + d.resolved) || 1
    const y = d3.scaleLinear().domain([0, maxY]).nice().range([innerH, 0])

    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).tickSize(0))
      .call((sel) => sel.select('.domain').remove())
      .call((sel) => sel.selectAll('text').attr('fill', '#64748b').attr('font-size', '0.68rem'))

    g.append('g')
      .call(d3.axisLeft(y).ticks(4).tickSize(-innerW))
      .call((sel) => sel.select('.domain').remove())
      .call((sel) => sel.selectAll('text').attr('fill', '#64748b').attr('font-size', '0.68rem'))
      .call((sel) => sel.selectAll('.tick line').attr('stroke', '#1e293b'))

    const barW = x.bandwidth() / 2 - 2

    items.forEach((d) => {
      const x0 = x(d.label)
      g.append('rect')
        .attr('x', x0)
        .attr('y', y(d.new))
        .attr('width', barW)
        .attr('height', innerH - y(d.new))
        .attr('rx', 3)
        .attr('fill', '#f87171')
        .attr('opacity', 0.85)

      g.append('rect')
        .attr('x', x0 + barW + 4)
        .attr('y', y(d.resolved))
        .attr('width', barW)
        .attr('height', innerH - y(d.resolved))
        .attr('rx', 3)
        .attr('fill', '#4ade80')
        .attr('opacity', 0.85)
    })
  }, [scans])

  return <div className="chart-wrap chart-wrap-wide" ref={ref} />
}

export function SecurityScoreRing({ score, size = 120 }) {
  const ref = useRef(null)

  useLayoutEffect(() => {
    if (!ref.current) return
    const el = ref.current
    el.innerHTML = ''

    const radius = size / 2
    const stroke = 10
    const normalized = Math.max(0, Math.min(100, score ?? 0))
    const circumference = 2 * Math.PI * (radius - stroke)
    const offset = circumference - (normalized / 100) * circumference

    const color =
      normalized >= 80 ? '#4ade80' : normalized >= 60 ? '#fbbf24' : normalized >= 40 ? '#fb923c' : '#f87171'

    const svg = d3
      .select(el)
      .append('svg')
      .attr('width', size)
      .attr('height', size)
      .attr('viewBox', `0 0 ${size} ${size}`)

    const g = svg.append('g').attr('transform', `translate(${radius},${radius})`)

    g.append('circle')
      .attr('r', radius - stroke)
      .attr('fill', 'none')
      .attr('stroke', '#1e293b')
      .attr('stroke-width', stroke)

    g.append('circle')
      .attr('r', radius - stroke)
      .attr('fill', 'none')
      .attr('stroke', color)
      .attr('stroke-width', stroke)
      .attr('stroke-linecap', 'round')
      .attr('stroke-dasharray', circumference)
      .attr('stroke-dashoffset', offset)
      .attr('transform', 'rotate(-90)')

    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.1em')
      .attr('fill', '#e2e8f0')
      .attr('font-size', '1.5rem')
      .attr('font-weight', 800)
      .text(Math.round(normalized))

    g.append('text')
      .attr('text-anchor', 'middle')
      .attr('dy', '1.4em')
      .attr('fill', '#64748b')
      .attr('font-size', '0.62rem')
      .text('SCORE')
  }, [score, size])

  return <div className="chart-wrap chart-score-ring" ref={ref} />
}
