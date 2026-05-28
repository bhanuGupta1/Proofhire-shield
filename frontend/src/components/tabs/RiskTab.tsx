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

export function RiskTab({ result }: Props) {
  return (
    <div className="space-y-6">
      <TrafficLight level={result.risk_level} score={result.risk_score} />

      <p className="text-sm text-gray-700">{result.summary}</p>

      {/* Injection findings */}
      {result.prompt_injection_findings.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-red-700">
            Hidden instructions found ({result.prompt_injection_findings.length})
          </h3>
          <ul className="space-y-2">
            {result.prompt_injection_findings.map((f, i) => (
              <li key={i} className="rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="text-xs font-medium text-red-500 mb-1">[{f.pattern_id}]</p>
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
      {result.pii_findings.length > 0 && (
        <section>
          <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-yellow-700">
            Personal data flagged ({result.pii_findings.length})
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
