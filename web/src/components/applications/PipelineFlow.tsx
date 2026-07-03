import { useMemo, type ReactElement } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import type { Application } from '@/lib/schema'
import { pipelineMetrics } from './constants'

// Column node colors — theme tokens, plus a semantic red for rejections.
const C = {
  acc: 'var(--good)',
  iv: 'var(--stretch)',
  rej: '#ef4444',
  nr: 'var(--mute)',
  off: 'var(--strong)',
}

const LABEL_STYLE: React.CSSProperties = {
  fill: 'var(--fg)',
  stroke: 'var(--card)',
  strokeWidth: 3.5,
  strokeLinejoin: 'round',
  paintOrder: 'stroke',
  fontWeight: 600,
  fontSize: 12,
}

function node(x: number, y: number, w: number, h: number, fill: string, key: string) {
  if (h <= 0) return null
  return <rect key={key} x={x} y={y} width={w} height={h} rx={3} fill={fill} />
}

function band(
  x1: number,
  y1: number,
  h1: number,
  x2: number,
  y2: number,
  h2: number,
  fill: string,
  key: string,
) {
  if (h1 <= 0) return null
  const xm = (x1 + x2) / 2
  return (
    <path
      key={key}
      d={`M${x1} ${y1} C${xm} ${y1} ${xm} ${y2} ${x2} ${y2} L${x2} ${y2 + h2} C${xm} ${y2 + h2} ${xm} ${y1 + h1} ${x1} ${y1 + h1} Z`}
      fill={fill}
      opacity={0.2}
    />
  )
}

function label(x: number, y: number, anchor: 'start' | 'middle' | 'end', text: string, key: string) {
  return (
    <text key={key} x={x} y={y} textAnchor={anchor} dominantBaseline="middle" style={LABEL_STYLE}>
      {text}
    </text>
  )
}

/**
 * A dependency-free inline-SVG pipeline flow ("Sankey") showing how far each
 * application progressed: Applied -> {Interview, Rejected, No response} ->
 * {Offer, Rejected, In process}. Ported from render.py's `renderPipeline`.
 * Returns null when there is no submitted-pipeline data to draw.
 */
export function PipelineFlow({ apps }: { apps: Application[] }) {
  const reduce = useReducedMotion()
  const els = useMemo(() => {
    const p = pipelineMetrics(apps)
    if (p.submitted < 1) return null

    const W = 760
    const H = 300
    const top = 26
    const gap = 18
    const nw = 14
    const xA = 120
    const xM = 378
    const xR = 626
    const scale = (H - 2 * top - 2 * gap) / p.submitted

    const hIv = p.reachedIv * scale
    const hRb = p.rejBefore * scale
    const hNr = p.noResp * scale
    const aH = p.submitted * scale
    const hOff = p.offers * scale
    const hRa = p.rejAfter * scale
    const hIp = p.inProc * scale

    // Stacked y-offsets for the middle and right columns (present segments only).
    const M: Record<string, number> = {}
    let my = top
    for (const [k, h] of [['iv', hIv], ['rb', hRb], ['nr', hNr]] as const) {
      if (h > 0) {
        M[k] = my
        my += h + gap
      }
    }
    const R: Record<string, number> = {}
    let ry = top
    for (const [k, h] of [['off', hOff], ['ra', hRa], ['ip', hIp]] as const) {
      if (h > 0) {
        R[k] = ry
        ry += h + gap
      }
    }

    const bands: (ReactElement | null)[] = []
    let ay = top
    bands.push(band(xA + nw, ay, hIv, xM, M.iv ?? 0, hIv, C.iv, 'b-iv'))
    ay += hIv
    bands.push(band(xA + nw, ay, hRb, xM, M.rb ?? 0, hRb, C.rej, 'b-rb'))
    ay += hRb
    bands.push(band(xA + nw, ay, hNr, xM, M.nr ?? 0, hNr, C.nr, 'b-nr'))
    if (hIv > 0) {
      let iy = M.iv ?? 0
      bands.push(band(xM + nw, iy, hOff, xR, R.off ?? 0, hOff, C.off, 'b-off'))
      iy += hOff
      bands.push(band(xM + nw, iy, hRa, xR, R.ra ?? 0, hRa, C.rej, 'b-ra'))
      iy += hRa
      bands.push(band(xM + nw, iy, hIp, xR, R.ip ?? 0, hIp, C.acc, 'b-ip'))
    }

    const nodes = [
      node(xA, top, nw, aH, C.acc, 'n-a'),
      node(xM, M.iv ?? 0, nw, hIv, C.iv, 'n-iv'),
      node(xM, M.rb ?? 0, nw, hRb, C.rej, 'n-rb'),
      node(xM, M.nr ?? 0, nw, hNr, C.nr, 'n-nr'),
      node(xR, R.off ?? 0, nw, hOff, C.off, 'n-off'),
      node(xR, R.ra ?? 0, nw, hRa, C.rej, 'n-ra'),
      node(xR, R.ip ?? 0, nw, hIp, C.acc, 'n-ip'),
    ]

    const labels = [
      label(xA - 9, top + aH / 2, 'end', `Applied ${p.submitted}`, 'l-a'),
      hIv > 0 ? label(xM + nw / 2, (M.iv ?? 0) - 9, 'middle', `Interview ${p.reachedIv}`, 'l-iv') : null,
      hRb > 0 ? label(xM + nw / 2, (M.rb ?? 0) - 9, 'middle', `Rejected ${p.rejBefore}`, 'l-rb') : null,
      hNr > 0 ? label(xM + nw / 2, (M.nr ?? 0) - 9, 'middle', `No response ${p.noResp}`, 'l-nr') : null,
      hOff > 0 ? label(xR + nw + 9, (R.off ?? 0) + hOff / 2, 'start', `Offer ${p.offers}`, 'l-off') : null,
      hRa > 0 ? label(xR + nw + 9, (R.ra ?? 0) + hRa / 2, 'start', `Rejected ${p.rejAfter}`, 'l-ra') : null,
      hIp > 0 ? label(xR + nw + 9, (R.ip ?? 0) + hIp / 2, 'start', `In process ${p.inProc}`, 'l-ip') : null,
    ]

    return { W, H, content: [...bands, ...nodes, ...labels] }
  }, [apps])

  if (!els) return null

  return (
    <motion.svg
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      viewBox={`0 0 ${els.W} ${els.H}`}
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="Application pipeline flow — how far each application progressed"
      className="mx-auto block h-auto w-full max-w-[820px]"
    >
      {els.content}
    </motion.svg>
  )
}
