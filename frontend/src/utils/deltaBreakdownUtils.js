export const COLOR_PIT = 'var(--color-danger)'
export const COLOR_TYRE = 'var(--color-warning)'
export const COLOR_TRAFFIC = '#818cf8'
export const COLOR_NET = 'var(--color-accent)'

export function rowMeta(backendLabel) {
  const L = String(backendLabel || '').toLowerCase()
  if (L.includes('pit'))
    return { display: 'Pit timing', fill: COLOR_PIT, key: 'pit' }
  if (L.includes('pace') || L.includes('tyre'))
    return { display: 'Tyre / pace', fill: COLOR_TYRE, key: 'tyre' }
  if (L.includes('traffic'))
    return { display: 'Traffic / rejoin', fill: COLOR_TRAFFIC, key: 'traffic' }
  return { display: backendLabel || 'Effect', fill: 'var(--color-text-secondary)', key: 'other' }
}

const ROW_ORDER = ['pit', 'tyre', 'traffic', 'other']

export function orderedComponents(comps) {
  return [...comps].sort((a, b) => {
    const ka = rowMeta(a.label).key
    const kb = rowMeta(b.label).key
    const ia = ROW_ORDER.indexOf(ka) >= 0 ? ROW_ORDER.indexOf(ka) : 99
    const ib = ROW_ORDER.indexOf(kb) >= 0 ? ROW_ORDER.indexOf(kb) : 99
    return ia - ib
  })
}

export function formatGainSeconds(v) {
  if (v > 0) return `+${v.toFixed(1)}s`
  if (v < 0) return `${v.toFixed(1)}s`
  return '0.0s'
}

export function breakdownForDriver(code, viz) {
  if (!viz) return null
  const k = String(code).toUpperCase()
  return viz[k] || viz[code] || null
}

/** Max |seconds| so cumulative stack from 0 and net tick fit on a symmetric ± domain. */
export function stackMaxAbs(components, total) {
  const comps = orderedComponents(components || [])
  let s = 0
  let lo = 0
  let hi = 0
  for (const c of comps) {
    s += c.value
    lo = Math.min(lo, s)
    hi = Math.max(hi, s)
  }
  const fromRun = Math.max(Math.abs(lo), Math.abs(hi))
  const fromTotal = Math.abs(total ?? 0)
  return Math.max(fromRun, fromTotal, 1e-6)
}

/**
 * Cumulative stacked segments on [-maxAbs, +maxAbs]; x maps to 0–100% (0s at 50%).
 * @returns {{ segments: Array<{left:number,width:number,label:string,value:number,display:string,fill:string}>, netLeft: number, maxAbs: number, cumEnd: number }}
 */
export function layoutStackedSegments(components, total, maxAbs) {
  const comps = orderedComponents(components || [])
  const m = Math.max(maxAbs, 1e-6)
  const scale = (t) => ((t + m) / (2 * m)) * 100
  let cum = 0
  const segments = []
  for (const c of comps) {
    const a = cum
    const b = cum + c.value
    cum = b
    const p0 = scale(a)
    const p1 = scale(b)
    const left = Math.min(p0, p1)
    const width = Math.max(Math.abs(p1 - p0), 0.2)
    const meta = rowMeta(c.label)
    segments.push({
      left,
      width,
      label: c.label,
      value: c.value,
      display: meta.display,
      fill: meta.fill,
    })
  }
  const netLeft = scale(total ?? 0)
  return { segments, netLeft, maxAbs: m, cumEnd: cum }
}
