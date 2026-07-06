import { useEffect, useRef } from 'react'

/**
 * Generative "signal constellation" backdrop — a drifting particle network whose
 * nodes link when near, reading as a live job *network*. Replaces the sakura tree.
 * Pure local canvas (no deps / no CDN → offline-safe); honours reduced-motion by
 * drawing a single static frame. Colours are pulled from the theme CSS vars so it
 * follows the palette + light/dark toggle.
 */
export function SignalField() {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    let raf = 0

    const css = getComputedStyle(document.documentElement)
    let cool = '#22d3ee'
    let signal = '#38bdf8'
    let hot = '#f59e0b'
    const readColors = () => {
      cool = css.getPropertyValue('--cool').trim() || cool
      signal = css.getPropertyValue('--signal').trim() || signal
      hot = css.getPropertyValue('--accent').trim() || hot
    }
    readColors()

    type P = { x: number; y: number; vx: number; vy: number; c: string }
    let pts: P[] = []
    const LINK = 122

    const seed = () => {
      const n = Math.round(Math.min(108, Math.max(30, (w * h) / 14500)))
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        c: Math.random() < 0.13 ? hot : Math.random() < 0.5 ? cool : signal,
      }))
    }

    const resize = () => {
      const r = canvas.getBoundingClientRect()
      w = r.width
      h = r.height
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      seed()
    }

    const draw = () => {
      ctx.clearRect(0, 0, w, h)
      for (const p of pts) {
        p.x += p.vx
        p.y += p.vy
        if (p.x < 0 || p.x > w) p.vx *= -1
        if (p.y < 0 || p.y > h) p.vy *= -1
      }
      ctx.strokeStyle = signal
      ctx.lineWidth = 1
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const a = pts[i]
          const b = pts[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d = Math.hypot(dx, dy)
          if (d < LINK) {
            ctx.globalAlpha = (1 - d / LINK) * 0.6
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }
      ctx.globalAlpha = 0.92
      for (const p of pts) {
        ctx.fillStyle = p.c
        ctx.beginPath()
        ctx.arc(p.x, p.y, 2, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.globalAlpha = 1
    }

    const loop = () => {
      draw()
      raf = requestAnimationFrame(loop)
    }

    resize()
    window.addEventListener('resize', resize)
    // Re-read palette when the light/dark class flips.
    const obs = new MutationObserver(() => {
      readColors()
      for (const p of pts) p.c = Math.random() < 0.13 ? hot : Math.random() < 0.5 ? cool : signal
    })
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

    if (reduce) draw()
    else loop()

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      obs.disconnect()
    }
  }, [])

  return <canvas ref={ref} className="js-signal-field" aria-hidden="true" />
}
