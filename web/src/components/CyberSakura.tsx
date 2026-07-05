import type { CSSProperties } from 'react'

const leaves = [
  { x: '70%', y: '12%', delay: '0s', dur: '8.8s', drift: '34px', scale: 0.82 },
  { x: '82%', y: '18%', delay: '1.4s', dur: '10.2s', drift: '-42px', scale: 0.66 },
  { x: '59%', y: '23%', delay: '2.2s', dur: '9.4s', drift: '54px', scale: 0.74 },
  { x: '76%', y: '31%', delay: '3.8s', dur: '11.4s', drift: '-30px', scale: 0.9 },
  { x: '64%', y: '39%', delay: '5.6s', dur: '9.8s', drift: '46px', scale: 0.7 },
  { x: '87%', y: '44%', delay: '6.7s', dur: '12s', drift: '-58px', scale: 0.78 },
  { x: '52%', y: '16%', delay: '7.9s', dur: '10.8s', drift: '62px', scale: 0.58 },
  { x: '72%', y: '50%', delay: '9.1s', dur: '9.6s', drift: '-36px', scale: 0.72 },
]

export function CyberSakura() {
  return (
    <div className="js-cyber-tree" aria-hidden="true">
      <svg className="js-cyber-tree-svg" viewBox="0 0 280 420" focusable="false">
        <defs>
          <linearGradient id="treeTrunk" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--neon-cyan)" />
            <stop offset="0.52" stopColor="var(--neon-blue)" />
            <stop offset="1" stopColor="var(--neon-violet)" />
          </linearGradient>
          <linearGradient id="treeLeaf" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#ffe5ff" />
            <stop offset="0.48" stopColor="#f7a8ff" />
            <stop offset="1" stopColor="var(--neon-cyan)" />
          </linearGradient>
          <filter id="treeGlow" x="-40%" y="-40%" width="180%" height="180%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <path className="js-tree-halo" d="M124 391C170 328 206 229 209 92" />
        <path className="js-tree-trunk" d="M126 395C154 313 171 222 166 112" />
        <path className="js-tree-branch" d="M161 202C117 178 82 149 52 105" />
        <path className="js-tree-branch" d="M169 164C206 143 232 113 248 72" />
        <path className="js-tree-branch" d="M160 246C211 233 244 206 264 166" />
        <path className="js-tree-branch" d="M147 286C111 276 80 252 55 215" />
        <g className="js-tree-canopy" filter="url(#treeGlow)">
          <circle cx="52" cy="105" r="5" />
          <circle cx="84" cy="140" r="4" />
          <circle cx="248" cy="72" r="5" />
          <circle cx="226" cy="114" r="4" />
          <circle cx="263" cy="166" r="5" />
          <circle cx="236" cy="207" r="4" />
          <circle cx="55" cy="215" r="5" />
          <circle cx="91" cy="256" r="4" />
        </g>
        <g className="js-tree-rings">
          <ellipse cx="144" cy="391" rx="54" ry="12" />
          <ellipse cx="144" cy="391" rx="86" ry="21" />
        </g>
      </svg>
      <div className="js-sakura-leaves">
        {leaves.map((leaf, index) => (
          <span
            key={`${leaf.x}-${leaf.delay}`}
            className="js-sakura-leaf"
            style={{
              '--leaf-x': leaf.x,
              '--leaf-y': leaf.y,
              '--leaf-delay': leaf.delay,
              '--leaf-duration': leaf.dur,
              '--leaf-drift': leaf.drift,
              '--leaf-scale': leaf.scale,
            } as CSSProperties}
          >
            <svg viewBox="0 0 32 32" focusable="false">
              <path d={index % 2 ? 'M15 2C27 9 29 22 15 30C3 21 5 9 15 2Z' : 'M16 2C27 8 30 19 17 30C5 24 4 10 16 2Z'} />
            </svg>
          </span>
        ))}
      </div>
    </div>
  )
}