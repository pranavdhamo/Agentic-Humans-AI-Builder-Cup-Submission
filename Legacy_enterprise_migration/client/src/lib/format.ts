export const pct = (a: number, b: number): string => (b > 0 ? `${((a / b) * 100).toFixed(a === b ? 0 : 1)}%` : '-')

export const num = (n: number | null | undefined): string => (n == null ? '-' : n.toLocaleString('en-US'))

export function duration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '-'
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const m = Math.floor(seconds / 60)
  return `${m}m ${Math.round(seconds - m * 60)}s`
}

export function ago(iso: string | null): string {
  if (!iso) return '-'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

/** "runs:2026..." -> ["runs", "2026..."] */
export function splitRunId(id: string): [string, string] {
  const i = id.indexOf(':')
  return [id.slice(0, i), id.slice(i + 1)]
}
