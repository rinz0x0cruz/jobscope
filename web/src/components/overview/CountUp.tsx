import { useEffect, useRef, useState } from 'react'

/** Number that eases from its previous value to `value` via a dependency-free rAF
 *  loop. Honors reduced-motion, and a safety timeout guarantees the final value
 *  even when rAF is throttled (e.g. a background tab). */
export function CountUp({ value }: { value: number }) {
  const [display, setDisplay] = useState(0)
  const fromRef = useRef(0)

  useEffect(() => {
    const reduce =
      typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduce) {
      fromRef.current = value
      setDisplay(value)
      return
    }
    const from = fromRef.current
    const start = performance.now()
    const duration = 900
    let raf = 0
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - t, 3)
      const current = from + (value - from) * eased
      fromRef.current = current
      setDisplay(current)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    const safety = window.setTimeout(() => {
      fromRef.current = value
      setDisplay(value)
    }, duration + 250)
    return () => {
      cancelAnimationFrame(raf)
      clearTimeout(safety)
    }
  }, [value])

  return <span>{Math.round(display).toLocaleString()}</span>
}
