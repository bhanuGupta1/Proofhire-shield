import type { RiskLevel } from '../lib/types'

const CONFIG: Record<RiskLevel, { bg: string; label: string; desc: string }> = {
  GREEN: {
    bg: 'bg-green-100 border-green-500 text-green-800',
    label: 'Low Risk',
    desc: 'Safe to use in AI workflow',
  },
  ORANGE: {
    bg: 'bg-orange-100 border-orange-500 text-orange-800',
    label: 'Elevated Risk',
    desc: 'Review flagged items before use',
  },
  RED: {
    bg: 'bg-red-100 border-red-600 text-red-800',
    label: 'High Risk',
    desc: 'Do not use in AI workflow',
  },
}

const DOT: Record<RiskLevel, string> = {
  GREEN: 'bg-green-500',
  ORANGE: 'bg-orange-500',
  RED: 'bg-red-600',
}

interface Props {
  level: RiskLevel
  score: number
}

export function TrafficLight({ level, score }: Props) {
  const c = CONFIG[level]
  return (
    <div className={`flex items-center gap-3 rounded-lg border-2 px-4 py-3 ${c.bg}`}>
      <span className={`h-4 w-4 rounded-full shrink-0 ${DOT[level]}`} />
      <div>
        <p className="font-semibold">{c.label} — {score}/100</p>
        <p className="text-sm">{c.desc}</p>
      </div>
    </div>
  )
}
