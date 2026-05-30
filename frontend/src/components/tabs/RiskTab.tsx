import type { ScanResult } from '../../lib/types'
import { TrafficLight } from '../TrafficLight'
import { SideBySideViewer } from '../SideBySideViewer'

interface Props {
  result: ScanResult
}

const AI_LABEL: Record<string, string> = {
  LIKELY: 'Likely written by AI',
  POSSIBLE: 'Possibly written by AI',
  UNLIKELY: 'Appears human-written',
}

// Labels are tied to what each pattern in scanner.py ACTUALLY detects — not the
// generic security-taxonomy names. Showing accurate names protects the recruiter.
const PATTERN_LABELS: Record<string, string> = {
  'PR-01-A': 'Instruction Override',
  'PR-01-B': 'Role Reassignment',
  'PR-01-C': 'System Token Injection',
  'PR-01-D': 'Rating Manipulation',
  'PR-01-E': 'New Directive Injection',
  'PR-01-F': 'Unconditional Approval Command',
  'PR-01-G': 'Mode Declaration',
  'PR-01-H': 'Loose Override Pattern',
}

function patternLabel(id: string): string {
  return PATTERN_LABELS[id] ?? id
}

export function RiskTab({ result }: Props) {
  const sortedInjections = [...result.prompt_injection_findings].sort(
    (a, b) => b.matched_text.length - a.matched_text.length,
  )
  const injCount = sortedInjections.length
  const piiCount = result.pii_findings.length
  const allClear =
    result.risk_level === 'GREEN' &&
    injCount === 0 &&
    piiCount === 0 &&
    result.ai_text_likelihood === 'UNLIKELY'

  return (
    <div className="space-y-6">
      <TrafficLight level={result.risk_level} score={result.risk_score} />

      <p className="text-sm text-gray-700">{result.summary}</p>

      {/* All-clear banner — only when nothing was flagged at all */}
      {allClear && (
        <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
          <strong className="font-semibold">All clear.</strong> No injection patterns, PII, or AI-text signals found in this CV.
        </div>
      )}

      {/* Severity breakdown pills */}
      <div className="flex flex-wrap gap-2 text-xs">
        <span
          className={`rounded-full px-3 py-1 font-medium ${
            injCount > 0 ? 'bg-red-100 text-red-700' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {injCount} injection pattern{injCount === 1 ? '' : 's'}
        </span>
        <span
          className={`rounded-full px-3 py-1 font-medium ${
            piiCount > 0 ? 'bg-amber-100 text-amber-700' : 'bg-gray-100 text-gray-600'
          }`}
        >
          {piiCount} PII item{piiCount === 1 ? '' : 's'}
        </span>
        <span className="rounded-full bg-gray-100 px-3 py-1 font-medium text-gray-600">
          AI likelihood: {result.ai_text_likelihood}
        </span>
      </div>

      {/* Injection findings (sorted by matched-text length, most suspicious first) */}
      {injCount > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-red-700">
            Hidden instructions found ({injCount})
          </h3>
          <ul className="space-y-2">
            {sortedInjections.map((f, i) => (
              <li key={i} className="rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="text-xs font-medium text-red-500 mb-1">[{patternLabel(f.pattern_id)}]</p>
                <blockquote className="font-mono text-sm text-red-800 break-words">
                  &ldquo;{f.matched_text}&rdquo;
                </blockquote>
                <p className="mt-1 text-xs text-gray-500 italic">{f.context}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* PII findings */}
      {piiCount > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-yellow-700">
            Personal data flagged ({piiCount})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-gray-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Value</th>
                </tr>
              </thead>
              <tbody>
                {result.pii_findings.map((f, i) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                    <td className="px-3 py-1.5 font-medium text-gray-700 capitalize">
                      {f.pii_type.replace(/_/g, ' ')}
                    </td>
                    <td className="px-3 py-1.5 font-mono text-gray-600 break-all">{f.matched_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* AI text */}
      <section>
        <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-500">AI-generated text</h3>
        <p className="text-sm text-gray-700">
          {AI_LABEL[result.ai_text_likelihood]}{' '}
          <span className="text-gray-400">(score: {result.ai_text_score.toFixed(2)})</span>
        </p>
      </section>

      {/* Side-by-side viewer */}
      <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Original vs. Safe copy
        </h3>
        <SideBySideViewer original={result.original_text} safeCopy={result.safe_copy_text} />
      </section>
    </div>
  )
}
