import { num } from '../lib/format'

export interface Point {
  label: string
  matched: number
  total: number
  built: boolean
  tokens?: number
}

/** Records-identical-to-COBOL per attempt: the story of a migration converging on the oracle. */
export default function Convergence({ points }: { points: Point[] }) {
  if (!points.length) return <p className="p-6 text-center text-sm text-slate-500">No attempts yet.</p>
  const total = Math.max(...points.map((p) => p.total), 1)
  const W = 560, H = 190, padL = 44, padB = 34, padT = 14, padR = 16
  const step = (W - padL - padR) / points.length
  const y = (v: number) => padT + (1 - v / total) * (H - padT - padB)

  return (
    <div className="p-4">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="records matching the COBOL per attempt">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(total * t)} y2={y(total * t)} style={{ stroke: "rgb(var(--ink-600))" }} strokeDasharray="3 4" />
            <text x={padL - 6} y={y(total * t) + 3} textAnchor="end" fontSize="9" style={{ fill: "rgb(var(--s500))" }}>{num(Math.round(total * t))}</text>
          </g>
        ))}
        {points.map((p, i) => {
          const x = padL + i * step + step * 0.2
          const w = step * 0.6
          const full = p.built && p.matched === p.total
          return (
            <g key={p.label + i}>
              <rect x={x} y={y(total)} width={w} height={H - padB - y(total)} rx="4" style={{ fill: "rgb(var(--ink-800))" }} />
              {p.built ? (
                <rect x={x} y={y(p.matched)} width={w} height={Math.max(2, H - padB - y(p.matched))} rx="4" style={{ fill: full ? 'rgb(var(--ok))' : 'rgb(var(--brand))' }} />
              ) : (
                <text x={x + w / 2} y={H - padB - 8} textAnchor="middle" fontSize="9" style={{ fill: "rgb(var(--bad))" }}>no build</text>
              )}
              <text x={x + w / 2} y={H - 18} textAnchor="middle" fontSize="10" style={{ fill: "rgb(var(--s400))" }}>{p.label}</text>
              {p.built && <text x={x + w / 2} y={H - 6} textAnchor="middle" fontSize="9" style={{ fill: full ? 'rgb(var(--ok))' : 'rgb(var(--s500))' }}>{num(p.matched)}/{num(p.total)}</text>}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
