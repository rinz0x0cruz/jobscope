import { useEffect, useRef } from 'react'

export type HeroVariant = 'constellation' | 'flowfield' | 'dotgrid' | 'aurora'
export const HERO_VARIANTS: HeroVariant[] = ['constellation', 'flowfield', 'dotgrid', 'aurora']

/**
 * Swappable generative hero backdrop (all local canvas/CSS → offline-safe, and
 * honours reduced-motion). Pick via `?hero=<variant>` on the URL. Colours come
 * from the theme vars, so every variant follows the palette + light/dark toggle.
 *
 *  - constellation : drifting particle network (a live "job network")
 *  - flowfield     : particles advected by a noise field (flowing streams)
 *  - dotgrid       : a dot matrix rippling from a roaming pulse (terminal/console)
 *  - aurora        : slow blurred gradient blobs (calm / premium)
 */
export function HeroBackdrop({ variant = 'constellation' }: { variant?: HeroVariant }) {
  const ref = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    if (variant === 'aurora') return
    const canvas = ref.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const dpr = Math.min(window.devicePixelRatio || 1, 2)
    let w = 0
    let h = 0
    let raf = 0
    let t = 0

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
    const seed = () => {
      const density = variant === 'flowfield' ? 9000 : 14500
      const cap = variant === 'flowfield' ? 240 : 108
      const n = Math.round(Math.min(cap, Math.max(30, (w * h) / density)))
      pts = Array.from({ length: n }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        c: Math.random() < 0.13 ? hot : Math.random() < 0.5 ? cool : signal,
      }))
    }
    let lastW = 0
    let lastH = 0
    let resizeTimer = 0
    const applySize = () => {
      // Freeze rebuilds during a pinch-zoom: the browser scales this fixed canvas
      // with the page, so re-rasterising mid-gesture is exactly what glitches on
      // mobile. While zoomed in (visual viewport scale > 1) we leave it be.
      const vv = window.visualViewport
      if (vv && vv.scale > 1.01) return
      const r = canvas.getBoundingClientRect()
      const nw = Math.round(r.width)
      const nh = Math.round(r.height)
      const firstRun = lastW === 0
      // Ignore height-only nudges (the mobile URL bar showing/hiding on scroll) so
      // the field never reseeds while scrolling; only a real width change rebuilds.
      if (!firstRun && Math.abs(nw - lastW) < 2) return
      const sx = firstRun || lastW === 0 ? 1 : nw / lastW
      const sy = firstRun || lastH === 0 ? 1 : nh / lastH
      lastW = nw
      lastH = nh
      w = nw
      h = nh
      canvas.width = Math.round(w * dpr)
      canvas.height = Math.round(h * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      if (firstRun) seed()
      // Keep the existing field and just rescale it into the new width, so a
      // rotate/resize slides rather than snapping to a fresh random layout.
      else for (const p of pts) { p.x *= sx; p.y *= sy }
    }
    const onResize = () => {
      window.clearTimeout(resizeTimer)
      resizeTimer = window.setTimeout(applySize, 160)
    }

    const constellation = () => {
      ctx.clearRect(0, 0, w, h)
      const LINK = 122
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
          const d = Math.hypot(a.x - b.x, a.y - b.y)
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

    const flowfield = () => {
      // fade prior frame without occluding the page gradient (erase, don't paint bg)
      ctx.globalCompositeOperation = 'destination-out'
      ctx.fillStyle = 'rgba(0,0,0,0.10)'
      ctx.fillRect(0, 0, w, h)
      ctx.globalCompositeOperation = 'source-over'
      t += 0.0025
      ctx.globalAlpha = 0.55
      for (const p of pts) {
        const ang = (Math.sin(p.x * 0.006 + t) + Math.cos(p.y * 0.0065 - t * 0.8)) * Math.PI
        p.x += Math.cos(ang) * 0.9
        p.y += Math.sin(ang) * 0.9
        if (p.x < 0 || p.x > w || p.y < 0 || p.y > h) {
          p.x = Math.random() * w
          p.y = Math.random() * h
        }
        ctx.fillStyle = p.c
        ctx.fillRect(p.x, p.y, 1.5, 1.5)
      }
      ctx.globalAlpha = 1
    }

    const dotgrid = () => {
      ctx.clearRect(0, 0, w, h)
      t += 0.02
      const gap = 26
      const cx = w * 0.5 + Math.cos(t * 0.4) * w * 0.26
      const cy = h * 0.45 + Math.sin(t * 0.5) * h * 0.22
      for (let y = gap / 2; y < h; y += gap) {
        for (let x = gap / 2; x < w; x += gap) {
          const d = Math.hypot(x - cx, y - cy)
          const pulse = 0.5 + 0.5 * Math.sin(d * 0.03 - t * 2)
          ctx.globalAlpha = 0.1 + pulse * 0.5
          ctx.fillStyle = pulse > 0.82 ? hot : pulse > 0.5 ? signal : cool
          ctx.beginPath()
          ctx.arc(x, y, 1.3 + pulse * 0.9, 0, Math.PI * 2)
          ctx.fill()
        }
      }
      ctx.globalAlpha = 1
    }

    const draw =
      variant === 'flowfield'
        ? flowfield
        : variant === 'dotgrid'
          ? dotgrid
          : constellation
    const loop = () => {
      draw()
      raf = requestAnimationFrame(loop)
    }
    applySize()
    window.addEventListener('resize', onResize)
    window.visualViewport?.addEventListener('resize', onResize)
    const obs = new MutationObserver(() => readColors())
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })

    if (reduce) draw()
    else loop()

    return () => {
      cancelAnimationFrame(raf)
      window.clearTimeout(resizeTimer)
      window.removeEventListener('resize', onResize)
      window.visualViewport?.removeEventListener('resize', onResize)
      obs.disconnect()
    }
  }, [variant])

  if (variant === 'aurora') {
    return (
      <div className="js-hero-aurora" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
    )
  }
  return <canvas ref={ref} className="js-signal-field" aria-hidden="true" />
}
