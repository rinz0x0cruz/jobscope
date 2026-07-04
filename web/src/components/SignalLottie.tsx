import { useLottie } from 'lottie-react'
import { useReducedMotion } from 'motion/react'

const signalAnimation = {
  v: '5.7.4',
  fr: 30,
  ip: 0,
  op: 90,
  w: 160,
  h: 160,
  nm: 'jobscope signal',
  ddd: 0,
  assets: [],
  layers: [
    {
      ddd: 0,
      ind: 1,
      ty: 4,
      nm: 'pulse outer',
      sr: 1,
      ks: {
        o: { a: 1, k: [{ t: 0, s: [0], e: [54] }, { t: 18, s: [54], e: [0] }, { t: 70, s: [0] }] },
        r: { a: 0, k: 0 },
        p: { a: 0, k: [80, 80, 0] },
        a: { a: 0, k: [0, 0, 0] },
        s: { a: 1, k: [{ t: 0, s: [42, 42, 100], e: [104, 104, 100] }, { t: 70, s: [104, 104, 100] }] },
      },
      ao: 0,
      shapes: [
        {
          ty: 'gr',
          nm: 'ring',
          it: [
            { ty: 'el', nm: 'ellipse', p: { a: 0, k: [0, 0] }, s: { a: 0, k: [86, 86] } },
            { ty: 'st', nm: 'stroke', c: { a: 0, k: [0.93, 0.93, 0.98, 1] }, o: { a: 0, k: 100 }, w: { a: 0, k: 3 }, lc: 1, lj: 1, ml: 4 },
            { ty: 'tr', p: { a: 0, k: [0, 0] }, a: { a: 0, k: [0, 0] }, s: { a: 0, k: [100, 100] }, r: { a: 0, k: 0 }, o: { a: 0, k: 100 } },
          ],
        },
      ],
    },
    {
      ddd: 0,
      ind: 2,
      ty: 4,
      nm: 'orbit',
      sr: 1,
      ks: {
        o: { a: 0, k: 100 },
        r: { a: 1, k: [{ t: 0, s: [0], e: [360] }, { t: 90, s: [360] }] },
        p: { a: 0, k: [80, 80, 0] },
        a: { a: 0, k: [0, 0, 0] },
        s: { a: 0, k: [100, 100, 100] },
      },
      ao: 0,
      shapes: [
        {
          ty: 'gr',
          nm: 'dot',
          it: [
            { ty: 'el', nm: 'ellipse', p: { a: 0, k: [46, 0] }, s: { a: 0, k: [16, 16] } },
            { ty: 'fl', nm: 'fill', c: { a: 0, k: [0.86, 1, 0.55, 1] }, o: { a: 0, k: 100 }, r: 1 },
            { ty: 'tr', p: { a: 0, k: [0, 0] }, a: { a: 0, k: [0, 0] }, s: { a: 0, k: [100, 100] }, r: { a: 0, k: 0 }, o: { a: 0, k: 100 } },
          ],
        },
      ],
    },
    {
      ddd: 0,
      ind: 3,
      ty: 4,
      nm: 'center',
      sr: 1,
      ks: {
        o: { a: 0, k: 100 },
        r: { a: 0, k: 0 },
        p: { a: 0, k: [80, 80, 0] },
        a: { a: 0, k: [0, 0, 0] },
        s: { a: 1, k: [{ t: 0, s: [88, 88, 100], e: [108, 108, 100] }, { t: 45, s: [108, 108, 100], e: [88, 88, 100] }, { t: 90, s: [88, 88, 100] }] },
      },
      ao: 0,
      shapes: [
        {
          ty: 'gr',
          nm: 'core',
          it: [
            { ty: 'el', nm: 'ellipse', p: { a: 0, k: [0, 0] }, s: { a: 0, k: [38, 38] } },
            { ty: 'fl', nm: 'fill', c: { a: 0, k: [0.98, 0.98, 1, 1] }, o: { a: 0, k: 100 }, r: 1 },
            { ty: 'tr', p: { a: 0, k: [0, 0] }, a: { a: 0, k: [0, 0] }, s: { a: 0, k: [100, 100] }, r: { a: 0, k: 0 }, o: { a: 0, k: 100 } },
          ],
        },
      ],
    },
  ],
}

export function SignalLottie({ className = '', size = 28 }: { className?: string; size?: number }) {
  const reduce = useReducedMotion()
  const { View } = useLottie(
    {
      animationData: signalAnimation,
      autoplay: !reduce,
      loop: !reduce,
    },
    { width: size, height: size, pointerEvents: 'none' },
  )

  return (
    <div aria-hidden="true" className={`js-signal-lottie ${className}`} style={{ width: size, height: size }}>
      <div className="js-signal-motion">{View}</div>
      <svg className="js-signal-glyph" viewBox="0 0 160 160" focusable="false">
        <path
          d="M58 54v-9c0-8 6-14 14-14h16c8 0 14 6 14 14v9"
          fill="none"
          stroke="currentColor"
          strokeWidth="11"
          strokeLinecap="round"
        />
        <rect x="34" y="56" width="92" height="70" rx="16" fill="currentColor" opacity="0.16" />
        <rect
          x="34"
          y="56"
          width="92"
          height="70"
          rx="16"
          fill="none"
          stroke="currentColor"
          strokeWidth="11"
        />
        <path d="M39 82h82" stroke="currentColor" strokeWidth="9" strokeLinecap="round" opacity="0.88" />
        <circle cx="80" cy="92" r="18" fill="var(--neon-blue)" opacity="0.88" />
        <circle cx="80" cy="92" r="8" fill="white" />
        <path
          d="M80 67v12M80 105v12M55 92h12M93 92h12"
          stroke="white"
          strokeWidth="5"
          strokeLinecap="round"
          opacity="0.9"
        />
      </svg>
    </div>
  )
}
