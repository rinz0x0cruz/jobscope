import type { BarItem } from '@/lib/overview'

const POINTS = [
  [318, 42],
  [456, 80],
  [508, 164],
  [398, 222],
  [236, 222],
  [128, 166],
  [178, 80],
  [318, 132],
] as const

export function SkillConstellation({ items }: { items: BarItem[] }) {
  const top = items.slice(0, 8)
  if (top.length === 0) return null

  const max = Math.max(1, ...top.map((item) => item.value))
  const center = { x: 318, y: 132 }

  return (
    <div className="js-skill-graph" role="img" aria-label="Skill gaps plotted by demand across matched roles">
      <svg viewBox="0 0 636 264" preserveAspectRatio="xMidYMid meet">
        <defs>
          <radialGradient id="skillNodeGlow" cx="50%" cy="45%" r="62%">
            <stop offset="0" stopColor="white" stopOpacity="0.95" />
            <stop offset="0.34" stopColor="var(--neon-cyan)" stopOpacity="0.88" />
            <stop offset="1" stopColor="var(--neon-violet)" stopOpacity="0.62" />
          </radialGradient>
        </defs>
        <circle className="js-skill-orbit" cx={center.x} cy={center.y} r="94" />
        <circle className="js-skill-orbit js-skill-orbit-wide" cx={center.x} cy={center.y} r="154" />
        {top.map((item, index) => {
          const [x, y] = POINTS[index]
          const radius = 9 + (item.value / max) * 17
          const labelY = y < center.y ? y - radius - 12 : y + radius + 18
          const anchor = x < center.x - 40 ? 'end' : x > center.x + 40 ? 'start' : 'middle'
          return (
            <g key={item.label}>
              <line className="js-skill-link" x1={center.x} y1={center.y} x2={x} y2={y} />
              <circle className="js-skill-node-halo" cx={x} cy={y} r={radius + 8} />
              <circle className="js-skill-node" cx={x} cy={y} r={radius} />
              <text className="js-skill-value" x={x} y={y + 4} textAnchor="middle">
                {item.value}
              </text>
              <text className="js-skill-label" x={x} y={labelY} textAnchor={anchor}>
                {item.label}
              </text>
            </g>
          )
        })}
        <circle className="js-skill-core" cx={center.x} cy={center.y} r="18" />
        <text className="js-skill-core-label" x={center.x} y={center.y + 4} textAnchor="middle">
          gaps
        </text>
      </svg>
    </div>
  )
}
